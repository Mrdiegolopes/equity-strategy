"""
Modelo de fatores.

Estima, para cada setor, a sensibilidade (beta) a cada fator macro via
regressao linear:

    ret_setor = alpha + b1*d_selic + b2*d_cambio + b3*ret_commodity + b4*ret_mercado + erro

estatistica:
  - Winsorizacao (1%/99%) dos retornos antes da regressao, para que um
    unico mes extremo (crash, rali) nao distorca o beta de setores com
    poucos tickers.
  - Erros-padrao HAC (Newey-West), que corrigem tanto heterocedasticidade
    quanto autocorrelacao serial dos residuos -- relevante em series
    financeiras mensais, onde momentum/persistencia de regime e comum.
    HC1 (usado antes) so corrige heterocedasticidade; se houver
    autocorrelacao os p-valores ficam artificialmente baixos, inflando
    o confidence score sem justificativa real.
  - Diagnosticos reportados: R2 ajustado, RMSE dos residuos,
    e Durbin-Watson (mede autocorrelacao residual; ~2.0 = ausencia de
    autocorrelacao, <1.5 ou >2.5 merece atencao).

"""
from __future__ import annotations
import json
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.stattools import durbin_watson

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

HAC_MAXLAGS = 3        # defasagens consideradas na correcao de autocorrelacao
WINSOR_LIMITES = (0.01, 0.99)  # percentis de corte


def preparar_fatores(painel: pd.DataFrame) -> pd.DataFrame:
    """transforma niveis macro em variacoes (choques) e alinha os fatores.
    - d_selic: variacao em pp da Selic meta no mes
    - d_cambio: retorno % do cambio USD BRL
    - ret_commodity, ret_mercado
    """
    df = painel.copy()
    fatores = pd.DataFrame(index=df.index)
    if "selic_meta" in df:
        fatores["d_selic"] = df["selic_meta"].diff()
    if "cambio_usdbrl" in df:
        fatores["d_cambio"] = df["cambio_usdbrl"].pct_change()
    if "ret_commodity" in df:
        fatores["ret_commodity"] = df["ret_commodity"]
    if "ret_mercado" in df:
        fatores["ret_mercado"] = df["ret_mercado"]
    return fatores


def _winsorizar(serie: pd.Series, limites=WINSOR_LIMITES) -> pd.Series:
    """Limita valores extremos aos percentis informados. Reduz a influencia
    desproporcional de um unico mes de crash/rali no beta estimado. risco maior em setores com poucos tickers na cesta."""
    lo, hi = serie.quantile(limites[0]), serie.quantile(limites[1])
    return serie.clip(lo, hi)


def estimar_betas(painel: pd.DataFrame, winsorizar: bool = True,
                  ate_periodo: str | None = None) -> dict:
    """Roda a regressao para cada setor e devolve um dicionario estruturado
    com coeficientes e diagnosticos estatisticos.

"""
    painel_uso = painel
    if ate_periodo is not None:
        corte = pd.Period(ate_periodo, freq="M")
        painel_uso = painel[painel.index < corte]

    fatores = preparar_fatores(painel_uso)
    cols_fatores = [c for c in config.FATORES if c in fatores.columns]

    resultados = {}
    for setor in config.SETORES.keys():
        if setor not in painel_uso.columns:
            continue
        y_bruto = painel_uso[setor]
        y_bruto = _winsorizar(y_bruto) if winsorizar else y_bruto
        dados = pd.concat([y_bruto.rename("y"), fatores[cols_fatores]], axis=1).dropna()
        if len(dados) < config.MIN_OBS:
            resultados[setor] = {"erro": f"observacoes insuficientes ({len(dados)})"}
            continue

        X = sm.add_constant(dados[cols_fatores])
        y = dados["y"]
        # HAC (Newey-West): corrige heterocedasticidade E autocorrelacao serial.
        # maxlags=3 cobre persistencia de ate 1 trimestre em dados mensais.
        modelo = sm.OLS(y, X).fit(
            cov_type="HAC", cov_kwds={"maxlags": HAC_MAXLAGS})

        betas = {f: float(modelo.params[f]) for f in cols_fatores}
        pvalues = {f: float(modelo.pvalues[f]) for f in cols_fatores}
        rmse = float(np.sqrt(np.mean(modelo.resid ** 2)))
        dw = float(durbin_watson(modelo.resid))

        resultados[setor] = {
            "alpha": float(modelo.params["const"]),
            "betas": betas,
            "pvalues": pvalues,
            "r2": float(modelo.rsquared),
            "r2_adj": float(modelo.rsquared_adj),
            "rmse": rmse,
            "durbin_watson": dw,
            "n_obs": int(len(dados)),
            "fatores": cols_fatores,
            "winsorizado": winsorizar,
            "ate_periodo": ate_periodo,
        }
    return resultados


def salvar_betas(resultados: dict, caminho="data/betas.json"):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)


def carregar_betas(caminho="data/betas.json") -> dict:
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def projetar_impacto(betas: dict, choque: dict) -> list[dict]:
    """Dado o dicionario de betas e um vetor de choque macro, projeta o
    impacto esperado em cada setor e ranqueia.
    impacto_setor = sum_f (beta_setor_f * choque_f)
    Retorna lista ordenada (maior impacto -> menor) com score de confianca.
    """

    out = []
    for setor, res in betas.items():
        if "erro" in res:
            continue
        impacto = 0.0
        contribuicoes = {}
        for f, b in res["betas"].items():
            c = choque.get(f, 0.0)
            contribuicoes[f] = b * c
            impacto += b * c
        out.append({
            "setor": setor,
            "impacto_estimado": impacto,
            "contribuicoes": contribuicoes,
            "r2": res["r2"],
            "r2_adj": res.get("r2_adj", res["r2"]),
            "n_obs": res["n_obs"],
            "confianca": _score_confianca(res, choque),
        })
    out.sort(key=lambda d: d["impacto_estimado"], reverse=True)
    return out


def _score_confianca(res: dict, choque: dict) -> str:
    """Confianca derivada de estatistica real
    R2 alto + fatores acionados significativos -> alta
    R2 medio ou significancia parcial -> media
    R2 baixo -> baixa  """
    
    r2 = res["r2"]
    acionados = [f for f in res["betas"] if abs(choque.get(f, 0)) > 1e-9]
    signif = [f for f in acionados if res["pvalues"].get(f, 1) < 0.10]
    frac_signif = (len(signif) / len(acionados)) if acionados else 0

    dw = res.get("durbin_watson")
    dw_problematico = dw is not None and not (1.5 <= dw <= 2.5)

    if r2 >= 0.35 and frac_signif >= 0.5 and not dw_problematico:
        return "alta"
    if r2 >= 0.15 or frac_signif >= 0.5:
        return "media" if not dw_problematico else "baixa"
    return "baixa"


if __name__ == "__main__":
    painel = pd.read_csv("data/painel.csv", index_col=0)
    painel.index = pd.PeriodIndex(painel.index, freq="M")
    betas = estimar_betas(painel)
    salvar_betas(betas)
    print(f"{'Setor':28s} {'R2':>6s} {'R2adj':>6s} {'RMSE':>7s} {'DW':>5s} {'n':>4s}")
    print("-" * 60)
    for setor, res in betas.items():
        if "erro" in res:
            print(f"{setor:28s} {res['erro']}")
        else:
            print(f"{setor:28s} {res['r2']:6.2f} {res['r2_adj']:6.2f} "
                  f"{res['rmse']:7.4f} {res['durbin_watson']:5.2f} {res['n_obs']:4d}")