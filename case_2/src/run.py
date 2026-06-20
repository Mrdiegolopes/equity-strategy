"""
Orquestrador do Macro Scenario Engine.

Conecta as 5 etapas:
  1. parse_cenario (LLM)      -> vetor de choque
  2. projetar_impacto (motor) -> ranking setorial + confianca
  3. validacao deterministica
  4. gerar_narrativa (LLM)    -> mecanismos + tickers + riscos
  5. render JSON + markdown

Uso:
    python src/run.py "Selic sobe 2pp, real deprecia 10%, commodities caem 15%"
"""
from __future__ import annotations
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import factor_model as fm
import llm_client
import validation
import report
from schemas import (ResultadoFinal, ImpactoSetorial, ChoqueMacro)


def rodar(cenario: str, betas_path="data/betas.json", top_n=5) -> ResultadoFinal:
    # ETAPA 1 — cenario -> choque
    choque: ChoqueMacro = llm_client.parse_cenario(cenario)
    avisos = validation.validar_choque(choque)

    # ETAPA 2 — motor quantitativo projeta e ranqueia
    betas = fm.carregar_betas(betas_path)
    choque_dict = {
        "d_selic": choque.d_selic, "d_cambio": choque.d_cambio,
        "ret_commodity": choque.ret_commodity, "ret_mercado": choque.ret_mercado,
    }
    ranking = fm.projetar_impacto(betas, choque_dict)
    beneficiados = ranking[:top_n]
    prejudicados = ranking[-top_n:][::-1]

    # ETAPA 4 — LLM narra o ranking ja calculado
    narrativa = llm_client.gerar_narrativa(
        cenario, choque,
        ranking_top=beneficiados, ranking_bottom=prejudicados)

    # ETAPA 3/validacao — checa tickers do LLM
    set_benef = {s["setor"] for s in beneficiados}
    set_prej = {s["setor"] for s in prejudicados}
    avisos += validation.validar_tickers(narrativa.tickers_positivos, set_benef)
    avisos += validation.validar_tickers(narrativa.tickers_negativos, set_prej)

    # mapeia mecanismo (do LLM) de volta para cada setor do ranking
    mec = {r.setor: r.mecanismo for r in narrativa.rationales}

    def _imp(lst):
        return [ImpactoSetorial(
            setor=s["setor"], impacto_estimado=s["impacto_estimado"],
            confianca=s["confianca"], r2=s["r2"],
            contribuicoes=s["contribuicoes"], mecanismo=mec.get(s["setor"]))
            for s in lst]

    return ResultadoFinal(
        cenario_input=cenario, choque=choque,
        setores_beneficiados=_imp(beneficiados),
        setores_prejudicados=_imp(prejudicados),
        tickers_positivos=narrativa.tickers_positivos,
        tickers_negativos=narrativa.tickers_negativos,
        riscos=narrativa.riscos, avisos_validacao=avisos)


if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0] == "--comparar-modelos":
        # Extensao: roda o mesmo cenario nos dois provedores de LLM e
        # compara onde convergem/divergem. Requer ANTHROPIC_API_KEY e
        # GEMINI_API_KEY configuradas simultaneamente.
        # Uso: python src/run.py --comparar-modelos "cenario aqui"
        import extensions as ext
        cenario = " ".join(args[1:]) or \
            "Selic sobe 2 pontos, real deprecia 10%, commodities caem 15%, bolsa recua 5%"
        betas = fm.carregar_betas("data/betas.json")
        resultado = ext.comparar_modelos(cenario, betas)
        os.makedirs("outputs", exist_ok=True)

        with open("outputs/comparacao_modelos.json", "w", encoding="utf-8") as f:
            import json
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        md_comp = report.comparacao_to_markdown(resultado)
        with open("outputs/comparacao_modelos.md", "w", encoding="utf-8") as f:
            f.write(md_comp)

        print(md_comp)
        print("\n[JSON completo salvo em outputs/comparacao_modelos.json]")
    else:
        if not args:
            cenario = input("Digite o cenario macro: ")
        else:
            cenario = " ".join(args)
        res = rodar(cenario)
        os.makedirs("outputs", exist_ok=True)
        with open("outputs/resultado.json", "w", encoding="utf-8") as f:
            f.write(report.to_json(res))
        md = report.to_markdown(res)
        with open("outputs/relatorio.md", "w", encoding="utf-8") as f:
            f.write(md)
        print(md)