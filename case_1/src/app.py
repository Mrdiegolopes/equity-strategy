"""
Interface Streamlit para o Earnings Call Intelligence Tracker.
comando ora rodar: streamlit run src/app.py

"""
from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import ingestao


# config visual

st.set_page_config(page_title="Earnings Call Intelligence", layout="wide")

st.markdown(
    """
    <style>
    .block-container h1 {
        font-size: 2.0rem !important;
        line-height: 1.15 !important;
    }

    .block-container h2 {
        font-size: 1.45rem !important;
        line-height: 1.25 !important;
        margin-top: 1.1rem !important;
    }

    .block-container h3 {
        font-size: 1.20rem !important;
        line-height: 1.25 !important;
        margin-top: 0.9rem !important;
    }

    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stMarkdownContainer"] li {
        font-size: 0.98rem;
        line-height: 1.45;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _markdown_compacto(md: str) -> str:
    """
   reduz fonte no streamlit.
    """
    md = md.replace(" ## ", "\n\n## ")
    md = md.replace(" # ", "\n\n# ")

    linhas = []
    for linha in md.splitlines():
        if linha.startswith("# "):
            linhas.append("### " + linha[2:])
        elif linha.startswith("## "):
            linhas.append("#### " + linha[3:])
        else:
            linhas.append(linha)

    return "\n".join(linhas)


st.title(f"Earnings Call Intelligence — {config.EMPRESA} ({config.TICKER})")
st.caption(
    f"Transcrição de teleconferência, inteligência estruturada, com  "
    f"citação literal verificável. Analisando {config.CALL_ATUAL['rotulo']} "
    f"vs. {config.CALL_ANTERIOR['rotulo']}."
)


# Sidebar estrutura ingerida sem custo de API

with st.sidebar:
    st.header("Estrutura das calls")

    try:
        atual = ingestao.ingerir(config.CALL_ATUAL)
        anterior = ingestao.ingerir(config.CALL_ANTERIOR)

        st.metric(f"{atual.rotulo} — seções", len(atual.slides))
        st.metric(f"{atual.rotulo} — rodadas Q&A", len(atual.turnos_qa))
        st.metric(f"{anterior.rotulo} — seções", len(anterior.slides))

        st.divider()
        st.caption("Analistas no Q&A da call atual:")

        for t in atual.turnos_qa:
            st.write(f"• {t.analista}")

    except FileNotFoundError as e:
        st.error(str(e))
        st.stop()


# Análise principal

st.subheader("Análise da call")

tem_chave = os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY")

if not tem_chave:
    st.warning(
        "Defina ANTHROPIC_API_KEY ou GEMINI_API_KEY para rodar a análise via LLM. "
        "A estrutura das calls já está disponível na sidebar sem custo de API."
    )


if st.button("Analisar call", type="primary", disabled=not tem_chave):
    import run
    import report

    with st.spinner("Ingestão → análise → comparação → citation tracking → FinBERT..."):
        rel = run.executar()

    st.success("Análise concluída.")

    # Veredito em destaque

    from validation import taxa_grounding

    taxa = taxa_grounding(rel.auditoria_citacoes)

    c1, c2, c3 = st.columns(3)

    c1.metric("Tom geral", rel.tom.tom.value)
    c2.metric("Surprise score", f"{rel.surprise.score}/10")
    c3.metric(
        "Taxa de grounding",
        f"{taxa:.0%}",
        help=(
            "Fração das citações do LLM que foram encontradas no texto-fonte. "
            "Citações não encontradas indicam possível alucinação ou paráfrase."
        ),
    )

    st.divider()

    
    # Relatório 
    st.subheader("Relatório executivo")

    md_relatorio = _markdown_compacto(report.to_markdown(rel))
    st.markdown(md_relatorio)

    st.divider()

    # Detalhamento em abas

    aba1, aba2, aba3, aba4 = st.tabs(
        ["Perguntas críticas", "Red flags", "Citation tracking", "FinBERT"]
    )

    with aba1:
        for p in rel.perguntas_criticas:
            st.markdown(f"**{p.analista}** — _{p.qualidade_resposta.value}_")
            st.write(f"**Pergunta:** {p.pergunta_resumo}")
            st.write(f"**Por que é crítica:** {p.por_que_critica}")
            st.write(f"**Avaliação da resposta:** {p.avaliacao_resposta}")
            st.caption(f"Trecho da resposta: “{p.trecho_resposta.citacao}”")
            st.divider()

    with aba2:
        if rel.red_flags:
            for rf in rel.red_flags:
                st.markdown(f"**{rf.tipo.value}** — severidade {rf.severidade}/5")
                st.write(rf.descricao)
                st.caption(f"“{rf.trecho.citacao}”")
                st.divider()
        else:
            st.info("Nenhum red flag linguístico relevante identificado.")

    with aba3:
        st.caption(
            "Cada citação literal do LLM é verificada contra o texto-fonte. "
            "Esta é a camada anti-alucinação central do sistema."
        )

        df = pd.DataFrame(
            [
                {
                    "Origem": r.onde,
                    "Status": r.status.value,
                    "Similaridade": r.similaridade,
                    "Citação": r.citacao[:90] + ("..." if len(r.citacao) > 90 else ""),
                }
                for r in rel.auditoria_citacoes
            ]
        )

        def _cor_status(v):
            if v == "nao_encontrada":
                return "background-color: #ffcccc"
            if v == "aproximada":
                return "background-color: #fff3cd"
            return "background-color: #d4edda"

        st.dataframe(
            df.style.map(_cor_status, subset=["Status"]),
            use_container_width=True,
            hide_index=True,
        )

        if rel.avisos_validacao:
            st.warning("\n\n".join(rel.avisos_validacao))

    with aba4:
        if rel.validacao_finbert:
            from finbert import resumo_concordancia

            st.info(resumo_concordancia(rel.validacao_finbert))

            df = pd.DataFrame(
                [
                    {
                        "Trecho": v.trecho[:80] + "...",
                        "FinBERT": v.rotulo_finbert,
                        "Score": round(v.score_finbert, 3),
                        "Concorda com LLM": "✓" if v.concorda_com_llm else "✗",
                    }
                    for v in rel.validacao_finbert
                ]
            )

            st.dataframe(df, use_container_width=True, hide_index=True)

        else:
            st.info(
                "FinBERT não executado. Defina HF_API_TOKEN para habilitar "
                "a validação cruzada de tom. O pipeline funciona sem ele."
            )
