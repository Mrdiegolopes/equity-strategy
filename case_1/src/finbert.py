"""Validação cruzada opcional com FinBERT-PT-BR via Hugging Face Inference API."""
from __future__ import annotations
import os
import requests
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from schemas import AnaliseTom, Tom, ValidacaoFinBERT
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_POS = {Tom.muito_positivo, Tom.positivo}
_NEG = {Tom.negativo, Tom.cauteloso}


def _mapear_label(label: str) -> str:
    l = label.lower()
    if "pos" in l: return "positivo"
    if "neg" in l: return "negativo"
    return "neutro"


def _concorda(tom_llm: Tom, label_finbert: str) -> bool:
    lf = _mapear_label(label_finbert)
    if tom_llm in _POS: return lf == "positivo"
    if tom_llm in _NEG: return lf in {"negativo", "neutro"}
    return lf == "neutro"


def _chamar_hf(texto: str) -> tuple[str, float] | None:
    token = os.getenv("HF_API_TOKEN")
    if not token:
        return None
    url = f"https://api-inference.huggingface.co/models/{config.FINBERT_MODEL}"
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json={"inputs": texto}, timeout=30)
        r.raise_for_status()
        data = r.json()
        # HF pode retornar [[{label, score}, ...]] ou [{...}]
        preds = data[0] if isinstance(data, list) and data and isinstance(data[0], list) else data
        best = max(preds, key=lambda x: x.get("score", 0))
        return str(best.get("label")), float(best.get("score", 0))
    except Exception:
        return None


def validar_tom(tom: AnaliseTom) -> list[ValidacaoFinBERT]:
    saida = []
    for ev in tom.evidencias[:5]:
        pred = _chamar_hf(ev.citacao)
        if not pred:
            continue
        label, score = pred
        saida.append(ValidacaoFinBERT(
            trecho=ev.citacao, rotulo_finbert=label, score_finbert=score,
            tom_llm=tom.tom, concorda_com_llm=_concorda(tom.tom, label)
        ))
    return saida


def resumo_concordancia(validacoes: list[ValidacaoFinBERT]) -> str:
    if not validacoes:
        return ""
    ok = sum(1 for v in validacoes if v.concorda_com_llm)
    return f"Validação FinBERT-PT-BR: concordância direcional em {ok}/{len(validacoes)} evidências de tom."
