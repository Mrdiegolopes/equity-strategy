"""
Render do resultado: JSON estruturado + relatorio executivo markdown <=500 palavras.

Formato espelha o relatorio do Case 2 (Macro Scenario Engine): cabecalho com
o essencial, secoes com bullets densos, e um rodape de avisos sempre
preservado na integra.

"""
from __future__ import annotations
import json
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from schemas import RelatorioInteligencia

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

LIMITE = getattr(config, "LIMITE_PALAVRAS_RELATORIO", 500)


N_PERGUNTAS_CORE = 3


PESO_VEREDITO = 0.22
PESO_MUDANCAS = 0.38
PESO_PERGUNTAS = 0.25
PESO_RED_FLAGS = 0.15


# SANITIZACAO DE MARKDOWN

_MD_BACKSLASH = re.compile(r'([*_~])')
_CIFRAO_MOEDA = re.compile(r'R\$\s*')


def _escapar_md(texto: str) -> str:
    """Neutraliza caracteres que o renderizador (Markdown + MathJax do
    Streamlit) interpreta como sintaxe."""
    if not texto:
        return texto
    texto = _CIFRAO_MOEDA.sub('R$', texto)
    texto = texto.replace('$', '')
    return _MD_BACKSLASH.sub(r'\\\1', texto)


def to_json(rel: RelatorioInteligencia) -> str:
    return json.dumps(rel.model_dump(), ensure_ascii=False, indent=2)


def _contar(texto: str) -> int:
    return len(texto.split())


def _truncar_frase(texto: str, max_palavras: int) -> str:
    """Trunca preservando a ULTIMA FRASE COMPLETA que cabe no orcamento, em
    vez de cortar no meio de uma palavra/frase."""
    palavras = texto.split()
    if len(palavras) <= max_palavras:
        return texto
    cortado = " ".join(palavras[:max_palavras])
    for sep in (". ", "! ", "? "):
        idx = cortado.rfind(sep)
        if idx > max_palavras * 0.4:
            return cortado[: idx + 1]
    return cortado + "…"


_TOM_LABEL = {
    "muito_positivo": "Muito positivo", "positivo": "Positivo",
    "neutro": "Neutro", "cauteloso": "Cauteloso", "negativo": "Negativo",
}
_QUALIDADE_LABEL = {
    "direta": "resposta direta", "parcial": "resposta parcial",
    "evasiva": "resposta EVASIVA",
}
_DIRECAO_LABEL = {
    "elevado": "elevado", "reiterado": "= reiterado", "reduzido": " reduzido",
    "novo": " novo", "removido": "removido",
}


def _bullet_mudanca(m, max_palavras_desc: int) -> str:
    desc = _escapar_md(_truncar_frase(m.descricao, max_palavras_desc))
    tema = _escapar_md(m.tema)
    return f"- **{tema}** ({_DIRECAO_LABEL.get(m.direcao.value, m.direcao.value)}): {desc}"


def _bullet_pergunta(p, max_palavras_aval: int) -> str:
    aval = _escapar_md(_truncar_frase(p.avaliacao_resposta, max_palavras_aval))
    pergunta = _escapar_md(p.pergunta_resumo)
    analista = _escapar_md(p.analista)
    qual = _QUALIDADE_LABEL.get(p.qualidade_resposta.value, p.qualidade_resposta.value)
    return f"- **{analista}** — {pergunta} _({qual})_: {aval}"


def _bullet_red_flag(rf, max_palavras_desc: int) -> str:
    desc = _escapar_md(_truncar_frase(rf.descricao, max_palavras_desc))
    citacao = rf.trecho.citacao
    if len(citacao.split()) > 18:
        citacao = " ".join(citacao.split()[:18]) + "…"
    citacao = _escapar_md(citacao)
    sev = getattr(rf, "severidade", None)
    sev_str = f" (severidade {sev}/5)" if sev else ""
    return f"- **{rf.tipo.value}**{sev_str}: {desc}\n  > _\"{citacao}\"_"


def _preencher_por_orcamento(itens: list, montar_bullet, orcamento_palavras: int,
                             rotulo_plural: str,
                             tentativas_palavras_por_item=(40, 28, 18, 12)) -> tuple[list[str], str | None]:

    if not itens:
        return [], None

    melhor_resultado: list[str] = []
    melhor_n_mostrados = 0

    for palavras_por_item in tentativas_palavras_por_item:
        bullets: list[str] = []
        total = 0
        for item in itens:
            b = montar_bullet(item, palavras_por_item)
            custo = _contar(b)
            if total + custo > orcamento_palavras and bullets:
                break
            bullets.append(b)
            total += custo
        if len(bullets) > melhor_n_mostrados:
            melhor_resultado = bullets
            melhor_n_mostrados = len(bullets)
        if melhor_n_mostrados == len(itens):
            break

    omitidos = len(itens) - melhor_n_mostrados
    nota = (f"_(+{omitidos} {rotulo_plural} adicionais no JSON integral)_"
           if omitidos > 0 else None)
    return melhor_resultado, nota


def _montar_corpo(rel: RelatorioInteligencia, orcamento_total: int) -> list[str]:
    """Monta o corpo distribuindo `orcamento_total` (em palavras) entre as
    secoes pelos PESO_* definidos no topo do arquivo. Cada secao decide
    sozinha quantos itens cabem no que recebeu."""
    b = []

    orc_veredito = int(orcamento_total * PESO_VEREDITO)
    orc_mudancas = int(orcamento_total * PESO_MUDANCAS)
    orc_perguntas = int(orcamento_total * PESO_PERGUNTAS)
    orc_red_flags = int(orcamento_total * PESO_RED_FLAGS)

    b.append("## Veredito")
    b.append("")
    metade = max(15, orc_veredito // 2)
    resumo_tom = _truncar_frase(rel.tom.resumo, metade)
    b.append(f"**Tom geral:** {_TOM_LABEL.get(rel.tom.tom.value, rel.tom.tom.value)}. {_escapar_md(resumo_tom)}")
    b.append("")
    justificativa = _truncar_frase(rel.surprise.justificativa, metade)
    b.append(f"**Surprise score:** {rel.surprise.score}/10 (inferência). {_escapar_md(justificativa)}")
    b.append("")

    b.append(f"## Mudanças vs. {rel.call_anterior}")
    b.append("")
    sintese_orc = max(15, int(orc_mudancas * 0.15))
    sintese = _truncar_frase(rel.comparacao_temporal.sintese, sintese_orc)
    b.append(_escapar_md(sintese))
    b.append("")
    bullets_mud, nota_mud = _preencher_por_orcamento(
        rel.comparacao_temporal.mudancas, _bullet_mudanca,
        orc_mudancas - sintese_orc, "mudanças")
    b.extend(bullets_mud)
    if nota_mud:
        b.append(nota_mud)
    b.append("")

    b.append("## Perguntas mais críticas dos analistas")
    b.append("")
    perguntas_core = rel.perguntas_criticas[:N_PERGUNTAS_CORE]
    bullets_perg, _ = _preencher_por_orcamento(
        perguntas_core, _bullet_pergunta, orc_perguntas, "perguntas")
    if len(bullets_perg) < len(perguntas_core):
        # As perguntas sao requisito do Core: nunca omitimos uma por
        # orcamento, so reduzimos o texto de avaliacao ao minimo.
        bullets_perg = [_bullet_pergunta(p, 10) for p in perguntas_core]
    b.extend(bullets_perg)
    if len(rel.perguntas_criticas) > N_PERGUNTAS_CORE:
        b.append(f"_(+{len(rel.perguntas_criticas) - N_PERGUNTAS_CORE} "
                 f"perguntas adicionais no JSON integral)_")
    b.append("")

    b.append("## Red flags linguísticos")
    b.append("")
    if rel.red_flags:
        bullets_rf, nota_rf = _preencher_por_orcamento(
            rel.red_flags, _bullet_red_flag, orc_red_flags, "red flags")
        b.extend(bullets_rf)
        if nota_rf:
            b.append(nota_rf)
    else:
        b.append("- Nenhum red flag linguístico relevante identificado.")

    return b


def to_markdown(rel: RelatorioInteligencia) -> str:
    cab = []
    cab.append(f"# {rel.empresa} ({rel.ticker}) — Earnings Call Intelligence")
    cab.append("")
    cab.append(f"**Call analisada:** {rel.call_atual}  ·  "
               f"**Comparada com:** {rel.call_anterior}")
    cab.append("")

    rodape = []
    if rel.validacao_finbert:
        from finbert import resumo_concordancia
        msg = resumo_concordancia(rel.validacao_finbert)
        if msg:
            rodape.append("")
            rodape.append(f"> {_escapar_md(msg)}")
    if rel.avisos_validacao:
        rodape.append("")

    texto_fixo = "\n".join(cab + rodape)
    orcamento_corpo = max(150, LIMITE - _contar(texto_fixo) - 20)

    blocos = _montar_corpo(rel, orcamento_corpo)
    final = "\n".join(cab + blocos + rodape)


    if _contar(final) > LIMITE:
        orcamento_corpo = int(orcamento_corpo * (LIMITE / _contar(final)) * 0.92)
        blocos = _montar_corpo(rel, orcamento_corpo)
        final = "\n".join(cab + blocos + rodape)

    return final