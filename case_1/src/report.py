"""
Render do resultado: JSON estruturado + relatorio executivo markdown <=400 palavras.

REAPROVEITA do Case 2 a estrategia de limite duro de palavras via truncamento
proporcional determinístico: o prompt PEDE concisao, mas a garantia de caber
no limite e feita em codigo, preservando a estrutura inteira do relatorio
(todas as secoes aparecem) em vez de cortar o final -- aqui o pior caso seria
perder o surprise score ou os red flags, que sao centrais.

O relatorio e desenhado para ser lido em 2 minutos por um analista ocupado:
abre com o veredito (tom + surprise), depois o que mudou, as perguntas que
importam, e os red flags. Cada item carrega sua evidencia.
"""
from __future__ import annotations
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from schemas import RelatorioInteligencia

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

LIMITE = config.LIMITE_PALAVRAS_RELATORIO  # 400


def to_json(rel: RelatorioInteligencia) -> str:
    return json.dumps(rel.model_dump(), ensure_ascii=False, indent=2)


def _contar(texto: str) -> int:
    return len(texto.split())


def _truncar(texto: str, maxp: int) -> str:
    p = texto.split()
    if len(p) <= maxp:
        return texto
    return " ".join(p[:maxp]) + "…"


# Mapas de exibicao para os enums (formato legivel ao gestor)
_TOM_LABEL = {
    "muito_positivo": "Muito positivo", "positivo": "Positivo",
    "neutro": "Neutro", "cauteloso": "Cauteloso", "negativo": "Negativo",
}
_QUALIDADE_LABEL = {
    "direta": "resposta direta", "parcial": "resposta parcial",
    "evasiva": "resposta EVASIVA",
}
_DIRECAO_LABEL = {
    "elevado": "↑ elevado", "reiterado": "= reiterado", "reduzido": "↓ reduzido",
    "novo": "✦ novo", "removido": "✕ removido",
}


def _montar_corpo(rel: RelatorioInteligencia) -> list[str]:
    b = []

    # 1. Veredito
    b.append("## Veredito\n")
    b.append(f"**Tom geral:** {_TOM_LABEL.get(rel.tom.tom.value, rel.tom.tom.value)}. "
             f"{rel.tom.resumo}")
    b.append(f"**Surprise score:** {rel.surprise.score}/10 (inferencia). "
             f"{rel.surprise.justificativa}")

    # 2. Mudancas vs. trimestre anterior
    b.append(f"\n## Mudancas vs. {rel.call_anterior}\n")
    b.append(rel.comparacao_temporal.sintese)
    for m in rel.comparacao_temporal.mudancas:
        b.append(f"- **{m.tema}** ({_DIRECAO_LABEL.get(m.direcao.value, m.direcao.value)}): "
                 f"{m.descricao}")

    # 3. Perguntas criticas
    b.append("\n## Perguntas mais criticas dos analistas\n")
    for p in rel.perguntas_criticas:
        b.append(f"- **{p.analista}** — {p.pergunta_resumo} "
                 f"_({_QUALIDADE_LABEL.get(p.qualidade_resposta.value, p.qualidade_resposta.value)})_: "
                 f"{p.avaliacao_resposta}")

    # 4. Red flags
    if rel.red_flags:
        b.append("\n## Red flags linguisticos\n")
        for rf in rel.red_flags:
            b.append(f"- **{rf.tipo.value}**: {rf.descricao} "
                     f"→ \"{_truncar(rf.trecho.citacao, 25)}\"")
    else:
        b.append("\n## Red flags linguisticos\n")
        b.append("- Nenhum red flag linguistico relevante identificado.")

    return b


def _aplicar_limite(blocos: list[str], limite: int) -> tuple[list[str], bool]:
    texto = "\n".join(blocos)
    total = _contar(texto)
    if total <= limite:
        return blocos, False
    fator = limite / total
    novos = []
    for linha in blocos:
        if linha.startswith("- ") and _contar(linha) > 8:
            novos.append(_truncar(linha, max(8, int(_contar(linha) * fator))))
        else:
            novos.append(linha)
    return novos, True


def to_markdown(rel: RelatorioInteligencia) -> str:
    cab = []
    cab.append(f"# {rel.empresa} ({rel.ticker}) — Earnings Call Intelligence\n")
    cab.append(f"**Call analisada:** {rel.call_atual}  ·  "
               f"**Comparada com:** {rel.call_anterior}\n")

    # Rodape de validacao (sempre preservado: e curto e critico)
    rodape = []
    if rel.validacao_finbert:
        from finbert import resumo_concordancia
        msg = resumo_concordancia(rel.validacao_finbert)
        if msg:
            rodape.append(f"\n>  {msg}")
    if rel.avisos_validacao:
        rodape.append("\n## Auditoria de citacoes\n")
        for a in rel.avisos_validacao:
            rodape.append(f"-  {a}")

    texto_fixo = "\n".join(cab + rodape)
    limite_corpo = max(120, LIMITE - _contar(texto_fixo) - 30)

    blocos = _montar_corpo(rel)
    blocos, truncado = _aplicar_limite(blocos, limite_corpo)

    rod_trunc = []
    if truncado:
        rod_trunc.append(
            "\n> Relatorio condensado automaticamente para caber em "
            "400 palavras. Versao integral em outputs/resultado.json.")

    final = "\n".join(cab + blocos + rod_trunc + rodape)

    # Garantia dura: o requisito do case pede no máximo 400 palavras.
    # Se avisos de auditoria ou itens longos estourarem o limite, reduzimos
    # proporcionalmente o corpo e, no pior caso, truncamos linhas de bullets.
    if _contar(final) > LIMITE:
        excesso = _contar(final) - LIMITE
        blocos2 = []
        for linha in blocos:
            if linha.startswith("- ") and _contar(linha) > 6:
                blocos2.append(_truncar(linha, max(6, _contar(linha) - excesso // max(1, len(blocos)) - 2)))
            else:
                blocos2.append(linha)
        final = "\n".join(cab + blocos2 + rod_trunc + rodape)
    if _contar(final) > LIMITE:
        palavras = final.split()[:LIMITE]
        final = " ".join(palavras[:-1]) + "…"
    return final