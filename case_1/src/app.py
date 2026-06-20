"""
Interface Streamlit para o Earnings Call Intelligence Tracker.
Rode com:  streamlit run src/app.py

Mostra a analise completa de uma earnings call: tom, mudancas vs. trimestre
anterior, perguntas criticas, red flags, surprise score, e as duas camadas de
validacao (citation tracking + FinBERT).
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import ingestao

st.set_page_config(page_title="Earnings Call Intelligence", layout="wide")
st.title(f"Earnings Call Intelligence — {config.EMPRESA} ({config.TICKER})")
st.caption(
    f"Transcricao de teleconferencia → inteligencia estruturada, ancorada em "
    f"citacao literal verificavel. Analisando {config.CALL_ATUAL['rotulo']} "
    f"vs. {config.CALL_ANTERIOR['rotulo']}.")

# ─────────────────────────────────────────────
# Sidebar: estrutura ingerida (sem custo de API)
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("Estrutura das calls")
    try:
        atual = ingestao.ingerir(config.CALL_ATUAL)
        anterior = ingestao.ingerir(config.CALL_ANTERIOR)
        st.metric(f"{atual.rotulo} — secoes", len(atual.slides))
        st.metric(f"{atual.rotulo} — rodadas Q&A", len(atual.turnos_qa))
        st.metric(f"{anterior.rotulo} — secoes", len(anterior.slides))
        st.divider()
        st.caption("Analistas no Q&A (call atual):")
        for t in atual.turnos_qa:
            st.write(f"• {t.analista}")
    except FileNotFoundError as e:
        st.error(str(e))
        st.stop()

# ─────────────────────────────────────────────
# Analise principal
# ─────────────────────────────────────────────
st.subheader("Analise da call")

tem_chave = os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY")
if not tem_chave:
    st.warning("Defina ANTHROPIC_API_KEY ou GEMINI_API_KEY para rodar a analise via LLM. "
               "A estrutura das calls (sidebar) ja esta disponivel sem chave.")

if st.button("Analisar call", type="primary", disabled=not tem_chave):
    import run
    import report
    from schemas import StatusCitacao

    with st.spinner("Ingestao → analise → comparacao → citation tracking → FinBERT..."):
        rel = run.executar()

    st.success("Analise concluida.")

    # Veredito em destaque
    c1, c2, c3 = st.columns(3)
    c1.metric("Tom geral", rel.tom.tom.value)
    c2.metric("Surprise score", f"{rel.surprise.score}/10")
    from validation import taxa_grounding
    taxa = taxa_grounding(rel.auditoria_citacoes)
    c3.metric("Taxa de grounding", f"{taxa:.0%}",
              help="Fracao das citacoes do LLM que foram encontradas no "
                   "texto-fonte. Citacoes nao encontradas indicam possivel "
                   "alucinacao.")

    # Relatorio executivo
    st.markdown(report.to_markdown(rel))

    st.divider()

    # Detalhamento em abas
    aba1, aba2, aba3, aba4 = st.tabs(
        ["Perguntas criticas", "Red flags", "Citation tracking", "FinBERT"])

    with aba1:
        for p in rel.perguntas_criticas:
            st.markdown(f"**{p.analista}** — _{p.qualidade_resposta.value}_")
            st.write(f"Pergunta: {p.pergunta_resumo}")
            st.write(f"Por que critica: {p.por_que_critica}")
            st.write(f"Avaliacao: {p.avaliacao_resposta}")
            st.caption(f"Trecho da resposta: \"{p.trecho_resposta.citacao}\"")
            st.divider()

    with aba2:
        if rel.red_flags:
            for rf in rel.red_flags:
                st.markdown(f"**{rf.tipo.value}**: {rf.descricao}")
                st.caption(f"\"{rf.trecho.citacao}\"")
                st.divider()
        else:
            st.info("Nenhum red flag linguistico relevante identificado.")

    with aba3:
        st.caption("Cada citacao literal do LLM verificada contra o texto-fonte. "
                   "Esta e a camada anti-alucinacao central do sistema.")
        df = pd.DataFrame([{
            "Origem": r.onde,
            "Status": r.status.value,
            "Similaridade": r.similaridade,
            "Citacao": r.citacao[:70] + ("..." if len(r.citacao) > 70 else ""),
        } for r in rel.auditoria_citacoes])
        # Destaca nao-encontradas
        def _cor(v):
            if v == "nao_encontrada":
                return "background-color: #ffcccc"
            if v == "aproximada":
                return "background-color: #fff3cd"
            return "background-color: #d4edda"
        st.dataframe(df.style.map(_cor, subset=["Status"]), use_container_width=True)
        if rel.avisos_validacao:
            st.warning("\n\n".join(rel.avisos_validacao))

    with aba4:
        if rel.validacao_finbert:
            from finbert import resumo_concordancia
            st.info(resumo_concordancia(rel.validacao_finbert))
            df = pd.DataFrame([{
                "Trecho": v.trecho[:60] + "...",
                "FinBERT": v.rotulo_finbert,
                "Score": v.score_finbert,
                "Concorda com LLM": "✓" if v.concorda_com_llm else "✗",
            } for v in rel.validacao_finbert])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("FinBERT nao executado (defina HF_API_TOKEN para habilitar "
                    "a validacao cruzada de tom). O pipeline funciona sem ele.")