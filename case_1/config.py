"""Confi do Case 1 — Earnings Call Intelligence Tracker."""
from __future__ import annotations
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIR_TRANSCRICOES = ROOT_DIR / "transcricoes"
DIR_OUTPUTS = ROOT_DIR / "outputs"

EMPRESA = "Banco Bradesco"
TICKER = "BBDC4"
INDICE = "Ibovespa"

CALL_ATUAL = {
    "rotulo": "1T26",
    "arquivo": str(DIR_TRANSCRICOES / "bradesco_1t26.txt"),
    "data": "2026-05-07",
}
CALL_ANTERIOR = {
    "rotulo": "4T25",
    "arquivo": str(DIR_TRANSCRICOES / "bradesco_4t25.txt"),
    "data": "2026-02-06",
}

TOP_N_PERGUNTAS = 3
LIMITE_PALAVRAS_RELATORIO = 500

# Citation tracking: match exato primeiro; se falhar, fuzzy matching.
CITACAO_SIMILARIDADE_MINIMA = 0.88

# FinBERT-PT-BR via Hugging Face 
FINBERT_MODEL = "lucas-leme/FinBERT-PT-BR"
