"""Ingestao e segmentacao de transcricoes de earnings calls."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SlideSection:
    titulo: str
    texto: str

@dataclass
class QATurn:
    analista: str
    pergunta: str
    resposta: str

@dataclass
class TranscricaoPreparada:
    rotulo: str
    caminho: str
    texto_integral: str
    prepared_remarks: str
    qa_bruto: str
    slides: list[SlideSection]
    turnos_qa: list[QATurn]

    def resumo_estrutural(self) -> str:
        return (f"{self.rotulo}: {len(self.texto_integral):,} caracteres, "
                f"{len(self.slides)} secoes, {len(self.turnos_qa)} rodadas Q&A")

_SPEAKER = re.compile(r"(?m)^([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç .()&/'-]{2,100})\s+[–-]\s+")
_SLIDE = re.compile(r"(?im)^\s*Slide\s+\d+\s+[–-]\s+.*$")
_QA_MARKER = re.compile(r"Sess[aã]o de perguntas e respostas", re.I)


def _limpar(texto: str) -> str:
    texto = texto.replace("\r", "\n")
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    # Remove cabeçalhos repetidos extraídos do PDF sem remover conteúdo de slides.
    texto = re.sub(r"\n\s*Transcri[cç][aã]o da\s+Videoconfer[eê]ncia\s*\n\s*Resultados do [^\n]+\n\s*\d{2} de [^\n]+ de \d{4}\s*\n", "\n", texto, flags=re.I)
    texto = re.sub(r"\n\s*\d+\s*\n", "\n", texto)
    return texto.strip()


def _separar_prepared_qa(texto: str) -> tuple[str, str]:
    m = _QA_MARKER.search(texto)
    if not m:
        return texto, ""
    return texto[:m.start()].strip(), texto[m.start():].strip()


def _segmentar_slides(prepared: str) -> list[SlideSection]:
    matches = list(_SLIDE.finditer(prepared))
    if not matches:
        return [SlideSection("Prepared remarks", prepared)]
    secoes: list[SlideSection] = []
    for i, m in enumerate(matches):
        inicio = m.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(prepared)
        bloco = prepared[inicio:fim].strip()
        titulo = bloco.splitlines()[0].strip()
        secoes.append(SlideSection(titulo=titulo, texto=bloco))
    return secoes


def _segmentar_qa(qa: str) -> list[QATurn]:
    """Heurística conservadora: identifica pergunta do analista e junta respostas seguintes até o próximo analista.

    Não tenta substituir o LLM; serve para auditoria, sidebar e inspeção rápida.
    """
    if not qa:
        return []
    partes = []
    matches = list(_SPEAKER.finditer(qa))
    for i, m in enumerate(matches):
        speaker = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(qa)
        fala = qa[start:end].strip()
        partes.append((speaker, fala))

    turnos: list[QATurn] = []
    i = 0
    while i < len(partes):
        speaker, fala = partes[i]
        speaker_l = speaker.lower()
        # Pula RI / management como introdutor.
        if any(x in speaker_l for x in ["andré", "marcelo", "cassiano", "ney", "marinelli", "carlos"]):
            i += 1
            continue
        pergunta = fala
        respostas = []
        j = i + 1
        while j < len(partes):
            sp, fl = partes[j]
            spl = sp.lower()
            if not any(x in spl for x in ["andré", "marcelo", "cassiano", "ney", "marinelli", "carlos"]):
                break
            if "andré" not in spl:  # André muitas vezes só transiciona perguntas.
                respostas.append(f"{sp} - {fl}")
            j += 1
        turnos.append(QATurn(analista=speaker, pergunta=pergunta, resposta="\n".join(respostas)))
        i = j
    return turnos


def ingerir(call_cfg: dict) -> TranscricaoPreparada:
    caminho = Path(call_cfg["arquivo"])
    if not caminho.exists():
        raise FileNotFoundError(f"Transcricao nao encontrada: {caminho}")
    texto = _limpar(caminho.read_text(encoding="utf-8"))
    prepared, qa = _separar_prepared_qa(texto)
    return TranscricaoPreparada(
        rotulo=call_cfg["rotulo"],
        caminho=str(caminho),
        texto_integral=texto,
        prepared_remarks=prepared,
        qa_bruto=qa,
        slides=_segmentar_slides(prepared),
        turnos_qa=_segmentar_qa(qa),
    )
