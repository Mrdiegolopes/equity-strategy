"""
Pipeline principal do Earnings Call Intelligence Tracker.

Coordena as etapas em sequencia, sem conter logica de negocio propria -- cada
etapa vive no seu modulo. Fluxo:

  [1] Ingestao      segmenta as duas calls (apresentacao / Q&A / slides)
  [2] Analise LLM   tom, perguntas criticas, red flags, surprise (call atual)
  [3] Comparacao    mudancas de guidance/temas vs. trimestre anterior
  [4] Citation track verifica TODA citacao literal contra o texto-fonte
  [5] FinBERT (ext)  valida o tom com classificador independente
  [6] Render         JSON + relatorio markdown <=400 palavras


  python src/run.py                      # roda a empresa/calls do config
  python src/run.py --comparar-modelos   # compara Anthropic e Gemini 
"""
from __future__ import annotations
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import ingestao
import llm_client
import validation
import finbert
import report
from schemas import RelatorioInteligencia


def _log(msg: str):
    print(f"  {msg}", flush=True)


def executar(provedor: str | None = None, rodar_finbert: bool = True) -> RelatorioInteligencia:
    """Executa o pipeline completo e retorna o relatorio agregado."""

    # INGESTAO
    _log("[1/6] Ingestao e segmentacao das transcricoes...")
    atual = ingestao.ingerir(config.CALL_ATUAL)
    anterior = ingestao.ingerir(config.CALL_ANTERIOR)
    _log(f"      {atual.resumo_estrutural()}")
    _log(f"      {anterior.resumo_estrutural()}")

    # ANALISE QUALITATIVA DA CALL ATUAL
    _log(f"[2/6] Analise qualitativa ({config.CALL_ATUAL['rotulo']}) via LLM...")
    analise = llm_client.analisar_call(
        prepared_remarks=atual.prepared_remarks,
        qa_texto=atual.qa_bruto,
        empresa=config.EMPRESA,
        rotulo=atual.rotulo,
        top_n_perguntas=config.TOP_N_PERGUNTAS,
        provedor=provedor,
    )
    _log(f"      Tom: {analise.tom.tom.value} | "
         f"{len(analise.perguntas_criticas)} perguntas | "
         f"{len(analise.red_flags)} red flags | surprise {analise.surprise.score}/10")

    # COMPARACAO TEMPORAL
    _log(f"[3/6] Comparacao {atual.rotulo} vs. {anterior.rotulo} via LLM...")
    comparacao = llm_client.comparar_trimestres(
        remarks_atual=atual.prepared_remarks,
        remarks_anterior=anterior.prepared_remarks,
        rotulo_atual=atual.rotulo,
        rotulo_anterior=anterior.rotulo,
        provedor=provedor,
    )
    _log(f"      {len(comparacao.mudancas)} mudancas identificadas")

    # CITATION TRACKING
    _log("[4/6] Citation tracking (verificando citacoes contra o texto-fonte)...")
    cit_analise, avisos_a = validation.auditar_analise(analise, atual.texto_integral)
    cit_comp, avisos_c = validation.auditar_comparacao(
        comparacao, atual.texto_integral, anterior.texto_integral)
    todas_citacoes = cit_analise + cit_comp
    todos_avisos = avisos_a + avisos_c
    taxa = validation.taxa_grounding(todas_citacoes)
    _log(f"      {len(todas_citacoes)} citacoes verificadas | "
         f"taxa de grounding: {taxa:.0%} | {len(todos_avisos)} aviso(s)")

    # FINBERT 
    validacoes_finbert = []
    if rodar_finbert:
        _log("[5/6] Validacao cruzada de tom com FinBERT-PT-BR...")
        validacoes_finbert = finbert.validar_tom(analise.tom)
        if validacoes_finbert:
            concordam = sum(1 for v in validacoes_finbert if v.concorda_com_llm)
            _log(f"      FinBERT concorda com o LLM em "
                 f"{concordam}/{len(validacoes_finbert)} trechos")
        else:
            _log("      FinBERT nao executado (sem HF_API_TOKEN ou API indisponivel) "
                 "— pipeline segue normalmente")
    else:
        _log("[5/6] FinBERT desativado para esta execucao")

    # AGREGACAO + RENDER
    _log("[6/6] Render do relatorio (JSON + markdown <=400 palavras)...")
    relatorio = RelatorioInteligencia(
        empresa=config.EMPRESA,
        ticker=config.TICKER,
        call_atual=atual.rotulo,
        call_anterior=anterior.rotulo,
        tom=analise.tom,
        comparacao_temporal=comparacao,
        perguntas_criticas=analise.perguntas_criticas,
        red_flags=analise.red_flags,
        surprise=analise.surprise,
        auditoria_citacoes=todas_citacoes,
        validacao_finbert=validacoes_finbert,
        avisos_validacao=todos_avisos,
    )
    return relatorio


def _salvar(relatorio: RelatorioInteligencia):
    os.makedirs(config.DIR_OUTPUTS, exist_ok=True)
    md = report.to_markdown(relatorio)
    js = report.to_json(relatorio)

    caminho_md = os.path.join(config.DIR_OUTPUTS, "relatorio.md")
    caminho_js = os.path.join(config.DIR_OUTPUTS, "resultado.json")
    with open(caminho_md, "w", encoding="utf-8") as f:
        f.write(md)
    with open(caminho_js, "w", encoding="utf-8") as f:
        f.write(js)

    palavras = len(md.split())
    print()
    print("=" * 60)
    print(md)
    print("=" * 60)
    print(f"\nRelatorio: {palavras} palavras")
    print(f"Salvo em: {caminho_md}")
    print(f"          {caminho_js}")


def main():
    if "--exemplo" in sys.argv:
        from example_result import build
        from schemas import AnaliseQualitativa
        relatorio = build()
        atual = ingestao.ingerir(config.CALL_ATUAL)
        anterior = ingestao.ingerir(config.CALL_ANTERIOR)
        analise = AnaliseQualitativa(
            tom=relatorio.tom,
            perguntas_criticas=relatorio.perguntas_criticas,
            red_flags=relatorio.red_flags,
            surprise=relatorio.surprise,
        )
        cit_a, av_a = validation.auditar_analise(analise, atual.texto_integral)
        cit_c, av_c = validation.auditar_comparacao(
            relatorio.comparacao_temporal, atual.texto_integral, anterior.texto_integral)
        relatorio.auditoria_citacoes = cit_a + cit_c
        relatorio.avisos_validacao = av_a + av_c
        _salvar(relatorio)
        return

    if "--comparar-modelos" in sys.argv:
        import extensions
        extensions.comparar_modelos_cli()
        return

    print(f"\nEarnings Call Intelligence Tracker — {config.EMPRESA} ({config.TICKER})")
    print(f"Analisando {config.CALL_ATUAL['rotulo']} vs. {config.CALL_ANTERIOR['rotulo']}\n")
    relatorio = executar(rodar_finbert="--sem-finbert" not in sys.argv)
    _salvar(relatorio)


if __name__ == "__main__":
    main()