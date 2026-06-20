"""
Coleta de dados para o motor de fatores.

yfinance: precos de acoes BR, Ibovespa e commodities (brent/minerio)
BCB/SGS:  Selic, cambio PTAX, IPCA 
"""


from __future__ import annotations
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def _yf_monthly_close(tickers: list[str], start: str, end: Optional[str]) -> pd.DataFrame:
    """Baixa fechamento mensal ajustado de uma lista de tickers via yfinance.
    Retorna DataFrame (index=mes, colunas=tickers). Tickers que falham sao pulados."""
    
    import yfinance as yf
    end = end or datetime.today().strftime("%Y-%m-%d")
    out = {}
    extintos = []
    for tk in tickers:
        for attempt in range(3):  # retry simples 
            try:
                df = yf.download(tk, start=start, end=end, interval="1mo",
                                 progress=False, auto_adjust=True)
                if df.empty:
                    raise ValueError("retorno vazio")
                close = df["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                out[tk] = close
                break
            except Exception as e:
                msg = str(e).lower()
                indica_extincao = "delisted" in msg or "not found" in msg or "404" in msg
                if indica_extincao:
                    extintos.append(tk)
                    log.warning(f"  [EXTINTO/RETICKETADO] {tk}: provavel evento corporativo "
                               f"(fusao, deslistagem, troca de ticker). Verificar e corrigir "
                               f"em config.py -- nao e instabilidade passageira.")

                if attempt == 2:
                    log.warning(f"  [pulado] {tk}: {e}")
                else:
                    time.sleep(1.5)
    if not out:
        raise RuntimeError("Nenhum ticker baixado com sucesso.")
    return pd.DataFrame(out)


def coletar_setores(start=None, end=None) -> pd.DataFrame:
    """Retorno mensal de cada SETOR = media dos retornos dos seus tickers."""
    start = start or config.START_DATE
    setor_rets = {}
    for setor, tickers in config.SETORES.items():
        log.info(f"Coletando {setor} ({len(tickers)} tickers)...")
        precos = _yf_monthly_close(tickers, start, end)
        rets = precos.pct_change().dropna(how="all")
        setor_rets[setor] = rets.mean(axis=1)  # media transversal = retorno do setor
    df = pd.DataFrame(setor_rets)
    df.index = pd.to_datetime(df.index).to_period("M")
    return df


def coletar_fatores_mercado(start=None, end=None) -> pd.DataFrame:
    """Retorno de mercado (Ibovespa) e fator commodity (Brent + minerio)."""
    start = start or config.START_DATE
    mkt = _yf_monthly_close([config.MARKET_INDEX], start, end)
    ret_mkt = mkt.pct_change().iloc[:, 0].rename("ret_mercado")

    comm_tickers = list(config.COMMODITY_TICKERS.values())
    try:
        comm = _yf_monthly_close(comm_tickers, start, end)
        ret_comm = comm.pct_change().mean(axis=1).rename("ret_commodity")
    except Exception:
        log.warning("Futuros de commodity falharam; usando fallback ETF.")
        comm = _yf_monthly_close([config.COMMODITY_FALLBACK], start, end)
        ret_comm = comm.pct_change().iloc[:, 0].rename("ret_commodity")

    df = pd.concat([ret_mkt, ret_comm], axis=1)
    df.index = pd.to_datetime(df.index).to_period("M")
    return df


def _baixar_serie_bcb(codigo: int, nome: str, start_br: str, end_br: str) -> pd.Series | None:
    """Baixa uma serie do BCB com retry e timeout progressivo"""

    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           f"?formato=json&dataInicial={start_br}&dataFinal={end_br}")
    timeouts = [60, 90, 120]  # da mais tempo a cada tentativa
    for attempt, timeout in enumerate(timeouts):
        try:
            log.info(f"  BCB serie {codigo} ({nome}), tentativa {attempt+1}/3 "
                     f"(timeout={timeout}s)...")
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            s = pd.DataFrame(r.json())
            s["data"] = pd.to_datetime(s["data"], format="%d/%m/%Y")
            s["valor"] = pd.to_numeric(s["valor"], errors="coerce")
            s = s.set_index("data")["valor"].resample("ME").last()
            log.info(f"  BCB serie {codigo} ({nome}): OK ({len(s)} obs)")
            return s
        except KeyboardInterrupt:
            raise
        except Exception as e:
            if attempt < 2:
                espera = (attempt + 1) * 5
                log.warning(f"  BCB serie {codigo} falhou: {e}. "
                            f"Aguardando {espera}s antes de tentar de novo...")
                time.sleep(espera)
            else:
                log.warning(f"  [pulado] BCB serie {codigo} ({nome}) apos 3 "
                            f"tentativas. IMPACTO: fator '{nome}' ausente da "
                            f"regressao. Tente rodar novamente mais tarde.")
    return None


def coletar_macro_bcb(start=None, end=None) -> pd.DataFrame:
    """Series macro do BCB/SGS. Se uma serie falhar, o pipeline continua """
    start = start or config.START_DATE
    start_br = pd.to_datetime(start).strftime("%d/%m/%Y")
    end_br = (pd.to_datetime(end) if end else datetime.today()).strftime("%d/%m/%Y")
    series = {}
    for cod, nome in config.BCB_SERIES.items():
        resultado = _baixar_serie_bcb(cod, nome, start_br, end_br)
        if resultado is not None:
            series[nome] = resultado
        # se None: segue sem esse fator, com aviso ja logado
    if not series:
        log.warning("ATENCAO: nenhuma serie do BCB foi coletada. "
                    "O motor rodara apenas com fatores de mercado e commodity.")
    df = pd.DataFrame(series)
    if not df.empty:
        df.index = pd.to_datetime(df.index).to_period("M")
    return df


def montar_dataset(start=None, end=None) -> pd.DataFrame:
    """Junta tudo num unico painel mensal alinhado por data."""
    setores = coletar_setores(start, end)
    mercado = coletar_fatores_mercado(start, end)
    macro = coletar_macro_bcb(start, end)
    painel = setores.join(mercado, how="inner").join(macro, how="inner")
    painel = painel.dropna(how="all")
    log.info(f"Painel final: {painel.shape[0]} meses x {painel.shape[1]} colunas")
    return painel


if __name__ == "__main__":
    df = montar_dataset()
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/painel.csv")
    print(df.tail())
