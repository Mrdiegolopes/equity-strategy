"""
Render do resultado final: JSON estruturado + relatorio markdown <=500 palavras.
"""
from __future__ import annotations
import json
from schemas import ResultadoFinal

LIMITE_PALAVRAS_CORPO = 500  # exclui cabecalho tecnico (titulo, cenario, choque)


def to_json(res: ResultadoFinal) -> str:
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


def _contar_palavras(texto: str) -> int:
    return len(texto.split())


def _truncar_palavras(texto: str, max_palavras: int) -> str:
    """Corta um texto para no maximo N palavras, terminando com reticencias
    se houve corte. Usado para fazer o relatorio caber no limite duro sem
    depender so do prompt -- o LLM pode nao respeitar o orcamento de
    palavras pedido, entao isso e a garantia determinística."""
    palavras = texto.split()
    if len(palavras) <= max_palavras:
        return texto
    return " ".join(palavras[:max_palavras]) + "…"


def _montar_corpo(res: ResultadoFinal) -> list[str]:
    """Monta as secoes do relatorio (sem cabecalho) como lista de blocos.
    Separado de to_markdown para podermos medir e truncar antes de juntar."""
    blocos = []

    blocos.append("## Setores beneficiados\n")
    for s in res.setores_beneficiados:
        blocos.append(f"- **{s.setor}** (impacto {s.impacto_estimado:+.2%}, "
                      f"confianca {s.confianca}) — {s.mecanismo or ''}")
    blocos.append("\n## Setores prejudicados\n")
    for s in res.setores_prejudicados:
        blocos.append(f"- **{s.setor}** (impacto {s.impacto_estimado:+.2%}, "
                      f"confianca {s.confianca}) — {s.mecanismo or ''}")

    blocos.append("\n## Acoes — exposicao positiva\n")
    for t in res.tickers_positivos:
        blocos.append(f"- **{t.ticker}** ({t.setor}): {t.justificativa}")
    blocos.append("\n## Acoes — exposicao negativa\n")
    for t in res.tickers_negativos:
        blocos.append(f"- **{t.ticker}** ({t.setor}): {t.justificativa}")

    blocos.append("\n## Riscos da tese\n")
    for r in res.riscos:
        blocos.append(f"- **{r.risco}**: {r.impacto}")

    return blocos


def _aplicar_limite_duro(blocos: list[str], limite: int) -> tuple[list[str], bool]:
    """Se o corpo passar do limite de palavras, trunca os textos mais longos
    (mecanismos e justificativas) PROPORCIONALMENTE, preservando a estrutura
    inteira do relatorio (todos os setores/tickers/riscos continuam
    aparecendo, so com texto mais curto) em vez de cortar o final do
    documento, o que faria os Riscos da tese sumirem por completo --
    o pior cenario possivel, pois e um requisito explicito do case.

    Retorna (blocos_ajustados, foi_truncado)."""
    texto_completo = "\n".join(blocos)
    total = _contar_palavras(texto_completo)
    if total <= limite:
        return blocos, False

    # Truncamento proporcional: reduz cada linha de conteudo (que comeca com
    # "- **") para uma fracao do seu tamanho original, na mesma proporcao
    # que o excesso total representa.
    fator = limite / total
    novos = []
    for linha in blocos:
        if linha.startswith("- **") and _contar_palavras(linha) > 8:
            max_palavras_linha = max(8, int(_contar_palavras(linha) * fator))
            novos.append(_truncar_palavras(linha, max_palavras_linha))
        else:
            novos.append(linha)  # cabecalhos de secao (##) nao sao cortados
    return novos, True


def to_markdown(res: ResultadoFinal) -> str:
    c = res.choque
    cabecalho = []
    cabecalho.append("# Macro Scenario Engine — Recomendacao Setorial\n")
    cabecalho.append(f"**Cenario:** {res.cenario_input}\n")
    cabecalho.append(
        f"**Choque lido:** Selic {c.d_selic:+.1f}pp · USD/BRL {c.d_cambio:+.0%} · "
        f"Commodities {c.ret_commodity:+.0%} · Mercado {c.ret_mercado:+.0%} · "
        f"horizonte {c.horizonte_meses}m · confianca da leitura: {c.confianca_extracao}\n")
    if c.premissas:
        cabecalho.append("> Premissas assumidas: " + "; ".join(c.premissas) + "\n")

    # Monta o rodape ANTES de truncar, para descontar seu tamanho do
    # orcamento do corpo. Avisos de validacao sao SEMPRE preservados na
    # integra (sao curtos e criticos -- nunca truncados).
    rodape_avisos = []
    if res.avisos_validacao:
        rodape_avisos.append("\n## Avisos de validacao\n")
        for a in res.avisos_validacao:
            rodape_avisos.append(f"- {a}")

    # O limite de 500 palavras vale para o RELATORIO INTEIRO (requisito do
    # case), entao descontamos cabecalho + rodape do orcamento do corpo
    # antes de truncar -- senao o documento final passa do limite mesmo
    # com o corpo "dentro" do seu proprio orcamento isolado.
    texto_fixo = "\n".join(cabecalho + rodape_avisos)
    palavras_fixas = _contar_palavras(texto_fixo)
    margem_aviso_truncamento = 35  # reserva para a propria linha de aviso, se for usada
    limite_corpo = max(100, LIMITE_PALAVRAS_CORPO - palavras_fixas - margem_aviso_truncamento)

    blocos = _montar_corpo(res)
    blocos, truncado = _aplicar_limite_duro(blocos, limite_corpo)

    rodape_truncamento = []
    if truncado:
        rodape_truncamento.append(
            "\n> Texto condensado automaticamente para caber em 500 "
            "palavras (LLM gerou narrativa mais longa que o orcamento do "
            "prompt). Texto completo em outputs/resultado.json.")

    return "\n".join(cabecalho + blocos + rodape_truncamento + rodape_avisos)


def comparacao_to_markdown(resultado: dict) -> str:
    """Renderiza a saida de extensions.comparar_modelos() de forma legivel
    para um gestor -- nao como dois JSONs paralelos, mas como UMA leitura
    com uma secao curta de convergencia/divergencia entre os modelos.

    Principio editorial: o gestor nao quer ver "modelo A disse X, modelo B
    disse Y" lado a lado sem sintese -- ele quer saber ONDE confiar mais e
    ONDE ha incerteza real que merece cautela antes de agir."""
    a = resultado["anthropic"]
    g = resultado["gemini"]
    comp = resultado["comparacao"]

    L = []
    L.append("# Comparacao Multi-Modelo \n")
    L.append(
        f"O mesmo cenario foi processado por dois modelos de linguagem "
        f"independentes (Claude e Gemini) para checar a robustez da leitura. "
        f"**Concordancia entre os modelos: {comp['concordancia_setores_pct']}%** "
        f"do ranking setorial (top/bottom 5).\n")

    # Interpretacao automatica do nivel de concordancia -- traduz o numero
    # em uma recomendacao de postura, nao deixa o gestor adivinhar.
    pct = comp["concordancia_setores_pct"]
    if pct >= 80:
        leitura = ("**Alta concordancia.** Os dois modelos leram o cenario de "
                   "forma muito similar. A tese setorial e robusta a qual "
                   "modelo de linguagem foi usado -- o resultado vem "
                   "predominantemente do motor de fatores (dados), nao de "
                   "uma escolha de modelo.")
    elif pct >= 50:
        leitura = ("**Concordancia parcial.** Ha convergencia no nucleo da "
                   "tese, mas parte do ranking diverge entre os modelos. "
                   "Vale revisar manualmente os setores que NAO aparecem "
                   "no overlap antes de agir sobre eles.")
    else:
        leitura = ("**Baixa concordancia — sinal de alerta.** Os modelos "
                   "divergiram significativamente. Isso geralmente indica "
                   "que o cenario de entrada era ambiguo ou incompleto, "
                   "fazendo cada modelo preencher lacunas de forma "
                   "diferente (ver 'premissas' de cada leitura abaixo). "
                   "Recomenda-se cautela antes de agir sobre este cenario.")
    L.append(leitura + "\n")

    L.append("## Onde os modelos concordam\n")
    L.append(f"**Setores beneficiados (ambos):** "
             f"{', '.join(comp['overlap_setores_beneficiados']) or 'nenhum em comum'}")
    L.append(f"**Setores prejudicados (ambos):** "
             f"{', '.join(comp['overlap_setores_prejudicados']) or 'nenhum em comum'}")
    L.append(f"**Tickers positivos (ambos):** "
             f"{', '.join(comp['overlap_tickers_positivos']) or 'nenhum em comum'}")
    L.append(f"**Tickers negativos (ambos):** "
             f"{', '.join(comp['overlap_tickers_negativos']) or 'nenhum em comum'}\n")

    dc = comp["diferenca_absoluta_choque"]
    L.append("## Divergencia na leitura do cenario\n")
    L.append(
        f"Diferenca absoluta entre os vetores de choque extraidos por cada "
        f"modelo: Selic {dc['d_selic']}pp · Cambio {dc['d_cambio']:.0%} · "
        f"Commodity {dc['ret_commodity']:.0%} · Mercado {dc['ret_mercado']:.0%}. "
        f"Diferencas grandes aqui (>0.5pp em Selic, >5% nos demais) indicam "
        f"que o cenario original tinha espaco para interpretacao -- vale "
        f"reescreve-lo de forma mais quantitativa.\n")

    L.append("## Leitura individual de cada modelo\n")
    L.append(f"**Claude (Anthropic):** setores beneficiados — "
             f"{', '.join(a['setores_beneficiados'])}")
    L.append(f"**Gemini:** setores beneficiados — "
             f"{', '.join(g['setores_beneficiados'])}\n")

    return "\n".join(L)