"""
Extensoes valorizadas que saem quase de graca do motor de fatores:

  1. analise_sensibilidade: varia a magnitude de um fator e mostra como o
     ranking setorial se move. So re-roda projetar_impacto com choques
     diferentes — nenhum custo de LLM.

  2. backtest: aplica o motor a cenarios macro REAIS do passado e compara o
     ranking previsto com os retornos setoriais efetivamente observados
     naquele periodo. Valida (ou expoe) o poder preditivo do motor.

comparar_modelos: roda o MESMO cenario nos dois provedores de LLM
     (Anthropic e Gemini) e compara onde os outputs convergem e divergem.
     Setores que ambos os modelos concordam tem mais robustez qualitativa;
     divergencia sinaliza incerteza genuina sobre a narrativa (o ranking
     numerico em si NUNCA diverge, porque vem do motor de fatores -- so a
     etapa de narracao/selecao de tickers usa o LLM).
"""
from __future__ import annotations
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import factor_model as fm


def analise_sensibilidade(betas: dict, choque_base: dict,
                          fator: str, grade: list[float]) -> pd.DataFrame:
    """Varia 'fator' ao longo de 'grade', mantendo o resto do choque fixo.
    Retorna DataFrame (linhas=setores, colunas=valores do fator) com o
    impacto estimado em cada celula."""
    linhas = {}
    for valor in grade:
        choque = dict(choque_base)
        choque[fator] = valor
        rank = fm.projetar_impacto(betas, choque)
        linhas[valor] = {r["setor"]: r["impacto_estimado"] for r in rank}
    df = pd.DataFrame(linhas)
    df.index.name = "setor"
    df.columns.name = fator
    return df.sort_values(df.columns[-1], ascending=False)


def _choque_realizado(painel: pd.DataFrame, janela: tuple[str, str]) -> dict:
    """Calcula o choque macro EFETIVAMENTE ocorrido numa janela historica,
    para alimentar o motor no backtest."""
    fatores = fm.preparar_fatores(painel)
    win = fatores.loc[janela[0]:janela[1]]
    return {
        "d_selic": float(win["d_selic"].sum()) if "d_selic" in win else 0.0,
        "d_cambio": float((1 + win["d_cambio"]).prod() - 1) if "d_cambio" in win else 0.0,
        "ret_commodity": float((1 + win["ret_commodity"]).prod() - 1) if "ret_commodity" in win else 0.0,
        "ret_mercado": float((1 + win["ret_mercado"]).prod() - 1) if "ret_mercado" in win else 0.0,
    }


def backtest(painel: pd.DataFrame, betas: dict, janela: tuple[str, str],
            out_of_sample: bool = True, winsorizar: bool = True) -> pd.DataFrame:
    """Compara ranking PREVISTO pelo motor (usando o choque realizado na janela)
    com o retorno setorial REALIZADO na mesma janela.

    out_of_sample (padrao True): se True, RE-ESTIMA os betas usando apenas
    dados ANTERIORES ao inicio da janela testada -- backtest genuinamente
    out-of-sample, sem vazamento de informacao. O parametro 'betas' passado
    pela chamada e ignorado nesse modo (mantido na assinatura por
    compatibilidade e para permitir comparacao explicita com o modo
    full-sample). Se False, usa os betas fornecidos como estao (modo antigo,
    full-sample -- mantido apenas para fins de COMPARACAO pedagogica entre
    os dois metodos, nunca como avaliacao principal do motor).

    Metricas reportadas: correlacao de Spearman entre previsto e realizado, e
    a tabela setor a setor. attrs['out_of_sample'] indica qual modo foi usado."""
    inicio_janela = janela[0]

    if out_of_sample:
        # Re-estima os betas usando SOMENTE observacoes anteriores ao inicio
        # da janela testada -- o modelo nunca "ve" o periodo que esta sendo
        # avaliado. Isso e o que torna a correlacao resultante uma medida
        # honesta de poder preditivo, nao de ajuste retrospectivo.
        betas_uso = fm.estimar_betas(painel, winsorizar=winsorizar,
                                     ate_periodo=inicio_janela)
        n_obs_exemplo = next(
            (r["n_obs"] for r in betas_uso.values() if "erro" not in r), 0)
        if n_obs_exemplo < config.MIN_OBS:
            raise ValueError(
                f"Dados insuficientes ANTES de {inicio_janela} para estimar "
                f"betas out-of-sample ({n_obs_exemplo} obs, minimo "
                f"{config.MIN_OBS}). Escolha uma janela de teste mais "
                f"tardia ou amplie o periodo de coleta de dados.")
    else:
        betas_uso = betas

    choque = _choque_realizado(painel, janela)
    previsto = {r["setor"]: r["impacto_estimado"]
               for r in fm.projetar_impacto(betas_uso, choque)}

    setores = [s for s in config.SETORES if s in painel.columns]
    realizado = {}
    for s in setores:
        serie = painel[s].loc[janela[0]:janela[1]]
        realizado[s] = float((1 + serie).prod() - 1)

    df = pd.DataFrame({
        "previsto": pd.Series(previsto),
        "realizado": pd.Series(realizado),
    }).dropna()
    df["rank_previsto"] = df["previsto"].rank(ascending=False)
    df["rank_realizado"] = df["realizado"].rank(ascending=False)
    spearman = df["rank_previsto"].corr(df["rank_realizado"], method="spearman")
    df.attrs["spearman"] = spearman
    df.attrs["janela"] = janela
    df.attrs["choque"] = choque
    df.attrs["out_of_sample"] = out_of_sample
    if out_of_sample:
        df.attrs["n_obs_estimacao"] = n_obs_exemplo
    return df.sort_values("realizado", ascending=False)


def comparar_full_sample_vs_oos(painel: pd.DataFrame, betas_full: dict,
                                janela: tuple[str, str]) -> dict:
    """Roda o MESMO backtest nos dois modos (full-sample 'otimista' vs.
    out-of-sample 'honesto') e retorna os dois Spearmans lado a lado.
    Util para DEMONSTRAR concretamente o quanto a metrica full-sample
    estava inflada -- em vez de so afirmar isso no README, mostra o
    numero antes/depois."""
    bt_full = backtest(painel, betas_full, janela, out_of_sample=False)
    bt_oos = backtest(painel, betas_full, janela, out_of_sample=True)
    return {
        "spearman_full_sample": round(bt_full.attrs["spearman"], 3),
        "spearman_out_of_sample": round(bt_oos.attrs["spearman"], 3),
        "n_obs_estimacao_oos": bt_oos.attrs["n_obs_estimacao"],
        "diferenca": round(
            bt_full.attrs["spearman"] - bt_oos.attrs["spearman"], 3),
        "tabela_full_sample": bt_full,
        "tabela_out_of_sample": bt_oos,
    }


# Cenarios historicos uteis para backtest
CENARIOS_HISTORICOS = {
    "aperto_2021_2022": ("2021-03", "2022-08"),   # ciclo de alta da Selic
    "choque_covid_2020": ("2020-02", "2020-04"),  # crash inicial da pandemia
    "recuperacao_2020H2": ("2020-05", "2020-12"),
}


def comparar_modelos(cenario: str, betas: dict, top_n: int = 5) -> dict:
    """Roda o pipeline completo (parser + narracao) nos dois provedores de
    LLM disponiveis e compara as saidas.

    Requer AMBAS as chaves configuradas (ANTHROPIC_API_KEY e GEMINI_API_KEY)
    -- e a unica funcao do projeto que de fato usa os dois provedores na
    mesma execucao; em todo o resto do pipeline, apenas um e usado por vez.

    O QUE PODE DIVERGIR: a leitura do choque (parse_cenario) e a narrativa/
    selecao de tickers (gerar_narrativa). O ranking setorial NUMERICO nao
    diverge entre modelos porque vem do motor de fatores (regressao), nao
    do LLM -- a unica forma de o ranking mudar e o vetor de choque lido
    pelos dois parsers ser diferente.

    Retorna um dict com as duas saidas completas e um resumo de divergencia:
    overlap de tickers escolhidos e diferenca no vetor de choque extraido.
    """
    import llm_client

    if not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("GEMINI_API_KEY")):
        raise RuntimeError(
            "comparar_modelos requer ANTHROPIC_API_KEY E GEMINI_API_KEY "
            "configuradas simultaneamente -- e a unica extensao que usa "
            "os dois provedores na mesma chamada.")

    resultados = {}
    for prov in ("anthropic", "gemini"):
        choque = llm_client.parse_cenario(cenario, provedor=prov)
        choque_dict = {
            "d_selic": choque.d_selic, "d_cambio": choque.d_cambio,
            "ret_commodity": choque.ret_commodity, "ret_mercado": choque.ret_mercado,
        }
        ranking = fm.projetar_impacto(betas, choque_dict)
        beneficiados = ranking[:top_n]
        prejudicados = ranking[-top_n:][::-1]
        narrativa = llm_client.gerar_narrativa(
            cenario, choque, ranking_top=beneficiados,
            ranking_bottom=prejudicados, provedor=prov)
        resultados[prov] = {
            "choque": choque.model_dump(),
            "setores_beneficiados": [s["setor"] for s in beneficiados],
            "setores_prejudicados": [s["setor"] for s in prejudicados],
            "tickers_positivos": [t.ticker for t in narrativa.tickers_positivos],
            "tickers_negativos": [t.ticker for t in narrativa.tickers_negativos],
        }

    # Resumo de convergencia/divergencia
    a, g = resultados["anthropic"], resultados["gemini"]
    overlap_pos = set(a["tickers_positivos"]) & set(g["tickers_positivos"])
    overlap_neg = set(a["tickers_negativos"]) & set(g["tickers_negativos"])
    overlap_setores_benef = set(a["setores_beneficiados"]) & set(g["setores_beneficiados"])
    overlap_setores_prej = set(a["setores_prejudicados"]) & set(g["setores_prejudicados"])

    diff_choque = {
        f: round(abs(a["choque"][f] - g["choque"][f]), 4)
        for f in ("d_selic", "d_cambio", "ret_commodity", "ret_mercado")
    }

    resultados["comparacao"] = {
        "overlap_tickers_positivos": sorted(overlap_pos),
        "overlap_tickers_negativos": sorted(overlap_neg),
        "overlap_setores_beneficiados": sorted(overlap_setores_benef),
        "overlap_setores_prejudicados": sorted(overlap_setores_prej),
        "diferenca_absoluta_choque": diff_choque,
        "concordancia_setores_pct": round(
            100 * (len(overlap_setores_benef) + len(overlap_setores_prej))
            / (2 * top_n), 1),
    }
    return resultados