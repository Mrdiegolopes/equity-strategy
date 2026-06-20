"""
Streamlit para o Macro Scenario Engine
comando pra rodar no terminal:: streamlit run src/app.py
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import factor_model as fm
import extensions as ext

st.set_page_config(page_title="Macro Scenario Engine", layout="wide")
st.title("Macro Scenario Engine — Bovespa")
st.caption("Cenario macro em linguagem natural: recomendacao setorial ancorada em regressao de fatores.")

# Caminhos absolutos relativos a raiz do projeto evita quebrar se o app for iniciado de outro diretorio de trabalho.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETAS = os.path.join(RAIZ, "data", "betas.json")
PAINEL = os.path.join(RAIZ, "data", "painel.csv")

if not os.path.exists(BETAS):
    st.error("Rode antes: python src/data_collection.py e python src/factor_model.py para gerar data/betas.json")
    st.stop()

cenario = st.text_area(
    "Descreva o cenario macroeconomico:",
    "A Selic sobe 2 pontos percentuais, o real se deprecia 10%, "
    "os precos de commodities caem 15% e a bolsa recua 5%.")

if st.button("Analisar cenario", type="primary"):
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY")):
        st.warning("Defina ANTHROPIC_API_KEY ou GEMINI_API_KEY para a analise via LLM.")
    else:
        import run, report
        with st.spinner("Lendo cenario, projetando impacto e gerando narrativa..."):
            res = run.rodar(cenario)
        st.success("Analise concluida.")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Beneficiados")
            st.dataframe(pd.DataFrame([{
                "Setor": s.setor, "Impacto": f"{s.impacto_estimado:+.2%}",
                "Confianca": s.confianca, "R2": round(s.r2, 2)} for s in res.setores_beneficiados]))
        with c2:
            st.subheader("Prejudicados")
            st.dataframe(pd.DataFrame([{
                "Setor": s.setor, "Impacto": f"{s.impacto_estimado:+.2%}",
                "Confianca": s.confianca, "R2": round(s.r2, 2)} for s in res.setores_prejudicados]))
        st.markdown(report.to_markdown(res))
        if res.avisos_validacao:
            st.warning("Avisos de validacao:\n\n" + "\n".join(f"- {a}" for a in res.avisos_validacao))

st.divider()
st.subheader("Analise de sensibilidade")
fator = st.selectbox("Fator a variar", ["d_selic", "d_cambio", "ret_commodity", "ret_mercado"])
if st.button("Rodar sensibilidade"):
    betas = fm.carregar_betas(BETAS)
    base = {"d_selic": 0, "d_cambio": 0.05, "ret_commodity": -0.10, "ret_mercado": 0}
    grade = [-0.2, -0.1, 0, 0.1, 0.2] if fator != "d_selic" else [0, 1, 2, 3, 4]
    df = ext.analise_sensibilidade(betas, base, fator, grade)
    st.dataframe(df.round(3))

st.divider()
st.subheader("Backtest histórico")
st.caption(
    "Aplica o motor a um choque macro REAL do passado e compara o ranking "
    "previsto com o retorno setorial efetivamente observado na mesma "
    "janela. Spearman alto = o motor teria ordenado os setores na direcao "
    "certa naquele periodo histórico.")

if not os.path.exists(PAINEL):
    st.info("Rode python src/data_collection.py para habilitar o backtest "
            "(precisa do painel historico completo, nao so dos betas).")
else:
    cenario_hist = st.selectbox(
        "Período histórico", list(ext.CENARIOS_HISTORICOS.keys()),
        format_func=lambda k: {
            "aperto_2021_2022": "Aperto monetário 2021–2022 (ciclo de alta da Selic)",
            "choque_covid_2020": "Choque COVID 2020 (crash inicial da pandemia)",
            "recuperacao_2020H2": "Recuperação 2020 H2 (pós-crash)",
        }.get(k, k))

    if st.button("Rodar backtest"):
        betas = fm.carregar_betas(BETAS)
        painel = pd.read_csv(PAINEL, index_col=0)
        painel.index = pd.PeriodIndex(painel.index, freq="M")
        janela = ext.CENARIOS_HISTORICOS[cenario_hist]

        with st.spinner(f"Estimando betas out-of-sample e rodando backtest "
                        f"para {janela[0]} a {janela[1]}..."):
            try:
                comp = ext.comparar_full_sample_vs_oos(painel, betas, janela)
            except ValueError as e:
                st.error(str(e))
                st.stop()

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Spearman — Out-of-sample (honesto)",
                     f"{comp['spearman_out_of_sample']:.2f}",
                     help="Betas re-estimados usando SOMENTE dados anteriores "
                          "ao inicio da janela testada. O motor nunca viu o "
                          "periodo que esta sendo avaliado.")
        with c2:
            st.metric("Spearman — Full-sample (otimista)",
                     f"{comp['spearman_full_sample']:.2f}",
                     delta=f"{-comp['diferenca']:+.2f} vs. out-of-sample",
                     delta_color="inverse",
                     help="Betas estimados sobre TODO o painel, incluindo o "
                          "periodo testado -- ha vazamento de informacao, "
                          "tende a superestimar o poder preditivo real.")

        spearman_oos = comp["spearman_out_of_sample"]
        if spearman_oos >= 0.5:
            st.success("Concordância forte mesmo out-of-sample: evidência "
                      "real de poder preditivo do motor neste período.")
        elif spearman_oos >= 0.2:
            st.warning("Concordância fraca a moderada out-of-sample: use "
                      "com cautela neste período.")
        else:
            st.error("Pouca ou nenhuma concordância out-of-sample: o motor "
                     "não captura bem este regime quando testado de forma "
                     "honesta (sem ter visto o período).")

        st.caption(
            f"Betas out-of-sample estimados com {comp['n_obs_estimacao_oos']} "
            f"observações (apenas dados anteriores a {janela[0]}). Menos "
            f"dados → maior incerteza nos coeficientes → diferença entre as "
            f"duas métricas acima mede o quanto o número full-sample estava "
            f"inflado por ver o próprio período testado.")

        st.subheader("Previsto vs. realizado (out-of-sample)")
        df_plot = comp["tabela_out_of_sample"][["previsto", "realizado"]].sort_values(
            "realizado", ascending=True)
        st.bar_chart(df_plot, horizontal=True)

        with st.expander("Ver tabela completa (out-of-sample)"):
            st.dataframe(comp["tabela_out_of_sample"][
                ["previsto", "realizado", "rank_previsto", "rank_realizado"]].round(3))
        with st.expander("Ver tabela completa (full-sample, para comparação)"):
            st.dataframe(comp["tabela_full_sample"][
                ["previsto", "realizado", "rank_previsto", "rank_realizado"]].round(3))