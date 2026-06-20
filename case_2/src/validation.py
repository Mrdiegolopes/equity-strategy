"""
Validacao deterministica "anti-alucinacao"

antes aceitar a narrativa do LLM 
  -todo ticker recomendado existe na nossa base setorial
  - o setor que o LLM atribuiu ao ticker bate com a base
  - tickers positivos vem de setores beneficiados; negativos, de prejudicados

"""
from __future__ import annotations
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _mapa_ticker_setor() -> dict:
    mapa = {}
    for setor, tickers in config.SETORES.items():
        for tk in tickers:
            mapa[tk.upper()] = setor
    return mapa


def validar_tickers(tickers: list, setores_esperados: set[str]) -> list[str]:
    """Retorna lista de avisos. Lista vazia = tudo certo."""
    avisos = []
    mapa = _mapa_ticker_setor()
    for t in tickers:
        tk = t.ticker.upper().strip()
        if tk not in mapa:
            avisos.append(f"Ticker '{tk}' nao existe na base setorial (possivel alucinacao).")
            continue
        setor_real = mapa[tk]
        if t.setor != setor_real:
            avisos.append(
                f"Ticker '{tk}' foi atribuido a '{t.setor}' mas pertence a '{setor_real}'.")
        if setor_real not in setores_esperados:
            avisos.append(
                f"Ticker '{tk}' ({setor_real}) nao esta entre os setores esperados desta direcao.")
    return avisos


def validar_choque(choque) -> list[str]:
    """Sanidade do vetor de choque (faixas plausiveis)."""
    avisos = []
    if abs(choque.d_selic) > 10:
        avisos.append(f"d_selic={choque.d_selic}pp parece extremo; verifique a leitura do cenario.")
    if abs(choque.d_cambio) > 0.6:
        avisos.append(f"d_cambio={choque.d_cambio:.0%} parece extremo.")
    if abs(choque.ret_commodity) > 0.7:
        avisos.append(f"ret_commodity={choque.ret_commodity:.0%} parece extremo.")
    return avisos
