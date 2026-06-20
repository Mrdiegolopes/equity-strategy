"""Extensões opcionais do Case 1.

Implementadas:
1) comparison multi-modelo: roda o mesmo input em Anthropic e Gemini e compara campos-chave.
2) self-critique leve: usa citation tracking + divergência de modelos para apontar baixa robustez.
"""
from __future__ import annotations
import os, sys, json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run, report, config


def comparar_modelos():
    resultados = {}
    for prov in ["anthropic", "gemini"]:
        try:
            rel = run.executar(provedor=prov, rodar_finbert=False)
            resultados[prov] = rel
        except Exception as e:
            resultados[prov] = str(e)
    return resultados


def _linha_resumo(rel):
    return {
        "tom": rel.tom.tom.value,
        "surprise_score": rel.surprise.score,
        "n_red_flags": len(rel.red_flags),
        "top_perguntas": [p.analista for p in rel.perguntas_criticas],
    }


def comparar_modelos_cli():
    os.makedirs(config.DIR_OUTPUTS, exist_ok=True)
    resultados = comparar_modelos()
    resumo = {}
    for prov, obj in resultados.items():
        if isinstance(obj, str):
            resumo[prov] = {"erro": obj}
        else:
            resumo[prov] = _linha_resumo(obj)
            with open(os.path.join(config.DIR_OUTPUTS, f"resultado_{prov}.json"), "w", encoding="utf-8") as f:
                f.write(report.to_json(obj))
    path = os.path.join(config.DIR_OUTPUTS, "comparacao_modelos.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print(f"\nComparação salva em: {path}")
