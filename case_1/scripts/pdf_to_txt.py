"""Converte PDFs de transcrição em .txt usando pypdf.

Uso:
  python scripts/pdf_to_txt.py caminho.pdf transcricoes/saida.txt
"""
from __future__ import annotations
import sys
from pathlib import Path
from pypdf import PdfReader

if len(sys.argv) != 3:
    raise SystemExit("Uso: python scripts/pdf_to_txt.py entrada.pdf saida.txt")
entrada = Path(sys.argv[1])
saida = Path(sys.argv[2])
reader = PdfReader(str(entrada))
texto = "\n".join(page.extract_text() or "" for page in reader.pages)
saida.parent.mkdir(parents=True, exist_ok=True)
saida.write_text(texto, encoding="utf-8")
print(f"OK: {entrada} -> {saida} ({len(texto):,} caracteres)")
