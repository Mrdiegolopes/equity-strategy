"""Citation tracking determinístico: verifica se cada citação existe na transcrição."""
from __future__ import annotations
import re
from difflib import SequenceMatcher
from typing import Iterable
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from schemas import (AnaliseQualitativa, ComparacaoTemporal, ResultadoCitacao,
                     StatusCitacao, TrechoCitado)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _normalizar(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    return s.strip()


def _janelas(texto: str, tamanho: int) -> Iterable[str]:
    norm = _normalizar(texto)
    tamanho = max(40, min(tamanho + 40, 600))
    step = max(20, tamanho // 3)
    for i in range(0, max(1, len(norm) - tamanho + 1), step):
        yield norm[i:i+tamanho]


def verificar_citacao(citacao: str, texto_fonte: str, onde: str) -> ResultadoCitacao:
    c = _normalizar(citacao)
    fonte = _normalizar(texto_fonte)
    if not c:
        return ResultadoCitacao(onde=onde, citacao=citacao, status=StatusCitacao.nao_encontrada, similaridade=0.0)
    if c in fonte:
        return ResultadoCitacao(onde=onde, citacao=citacao, status=StatusCitacao.encontrada,
                                similaridade=1.0, trecho_encontrado=citacao)
    melhor = (0.0, None)
    for janela in _janelas(texto_fonte, len(c)):
        score = SequenceMatcher(None, c, janela).ratio()
        if score > melhor[0]:
            melhor = (score, janela)
    status = StatusCitacao.aproximada if melhor[0] >= config.CITACAO_SIMILARIDADE_MINIMA else StatusCitacao.nao_encontrada
    return ResultadoCitacao(onde=onde, citacao=citacao, status=status,
                            similaridade=round(float(melhor[0]), 3), trecho_encontrado=melhor[1])


def _trechos_analise(a: AnaliseQualitativa) -> list[tuple[str, TrechoCitado]]:
    itens = []
    for i, t in enumerate(a.tom.evidencias, 1):
        itens.append((f"tom.evidencias[{i}]", t))
    for i, p in enumerate(a.perguntas_criticas, 1):
        itens.append((f"pergunta_critica[{i}].pergunta", p.trecho_pergunta))
        itens.append((f"pergunta_critica[{i}].resposta", p.trecho_resposta))
    for i, r in enumerate(a.red_flags, 1):
        itens.append((f"red_flags[{i}]", r.trecho))
    for i, t in enumerate(a.surprise.evidencias, 1):
        itens.append((f"surprise.evidencias[{i}]", t))
    return itens


def auditar_analise(a: AnaliseQualitativa, texto_atual: str):
    resultados = [verificar_citacao(t.citacao, texto_atual, onde) for onde, t in _trechos_analise(a)]
    avisos = [f"Citação não encontrada: {r.onde} — {r.citacao[:90]}" for r in resultados if r.status == StatusCitacao.nao_encontrada]
    return resultados, avisos


def auditar_comparacao(c: ComparacaoTemporal, texto_atual: str, texto_anterior: str):
    resultados = []
    for i, m in enumerate(c.mudancas, 1):
        resultados.append(verificar_citacao(m.evidencia_atual.citacao, texto_atual, f"comparacao[{i}].atual"))
        if m.evidencia_anterior:
            resultados.append(verificar_citacao(m.evidencia_anterior.citacao, texto_anterior, f"comparacao[{i}].anterior"))
    avisos = [f"Citação não encontrada: {r.onde} — {r.citacao[:90]}" for r in resultados if r.status == StatusCitacao.nao_encontrada]
    return resultados, avisos


def taxa_grounding(resultados: list[ResultadoCitacao]) -> float:
    if not resultados:
        return 0.0
    ok = sum(1 for r in resultados if r.status in (StatusCitacao.encontrada, StatusCitacao.aproximada))
    return ok / len(resultados)
