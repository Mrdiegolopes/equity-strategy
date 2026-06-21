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
 
# Padrao de reticencias: "...", "…", ou variantes com espacos ao redor.
# Usado para detectar citacoes compostas (concatenacao de trechos distantes).
_RE_RETICENCIAS = re.compile(r"\s*(?:\.{3,}|…)\s*")
 
 
def _normalizar(s: str) -> str:
    """Normalizacao reforcada (2a correcao no mesmo arquivo -- a 1a tratou
    citacoes compostas com reticencias; esta trata diferencas residuais de
    PONTUACAO/CARACTERES que, mesmo apos a 1a correcao, ainda derrubavam o
    score para perto-mas-abaixo do limiar de 0.85 em ~23% das citacoes reais
    observadas em execucao). Faz: aspas curvas/retas unificadas e REMOVIDAS
    (citacoes raramente preservam aspas internas do mesmo jeito que o
    texto-fonte as tem, e elas nao mudam o conteudo factual da citacao);
    remove inserções editoriais entre colchetes (ex: "[conforme Relatorio
    de Analise..., pagina 42]"), que o LLM as vezes anexa dentro da propria
    citacao como nota -- isso nao existe no texto-fonte por definicao e
    derrubava o score de citacoes que, sem a nota, batiam perfeitamente;
    colapsa espacos ao redor de pontuacao (", " vs " ,"); remove acentos
    tipograficos remanescentes de travessao/reticencias."""
    s = s.lower()
    # Remove inserções editoriais entre colchetes (notas do LLM, não fazem
    # parte do texto-fonte original).
    s = re.sub(r"\[[^\]]*\]", "", s)
    # Unifica e remove aspas (curvas, retas, simples, duplas) -- diferenças
    # de aspas não mudam o conteúdo da citação, só sua forma tipográfica.
    s = re.sub(r"[\"'\u2018\u2019\u201c\u201d]", "", s)
    s = s.replace("–", "-").replace("—", "-").replace("…", "...")
    # Colapsa espaço antes de pontuação (resíduo comum de "R$ 500 milhões ,"
    # vs "R$ 500 milhões,").
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()
 
 
def _janelas(texto: str, tamanho_citacao: int) -> Iterable[str]:
    """Gera janelas do texto-fonte para comparar contra uma citacao de
    `tamanho_citacao` caracteres. SEM TETO FIXO: a janela cresce com o
    tamanho da propria citacao ."""
    norm = _normalizar(texto)
    tamanho = max(40, tamanho_citacao + 40)
    step = max(20, tamanho // 3)
    for i in range(0, max(1, len(norm) - tamanho + 1), step):
        yield norm[i:i + tamanho]
    # Garante que a ultima posicao do texto tambem seja coberta (o loop
    # acima pode parar antes do final dependendo do passo).
    if len(norm) > tamanho:
        yield norm[-tamanho:]
 
 
def _melhor_similaridade(citacao_norm: str, texto_fonte: str) -> tuple[float, str | None]:
    """Busca a melhor janela do texto-fonte para UM trecho contiguo
    (sem reticencias). Retorna (score, janela_encontrada)."""
    if not citacao_norm:
        return 0.0, None
    fonte_norm = _normalizar(texto_fonte)
    if citacao_norm in fonte_norm:
        return 1.0, citacao_norm
    # Tenta sem pontuacao de fechamento (".", ",", ";", ":") no final
    # cobre o caso de citacao parcial fechada com pontuacao que a fonte,
    # naquele ponto exato, nao tem.
    sem_pontuacao_final = citacao_norm.rstrip(".,;: ")
    if sem_pontuacao_final and sem_pontuacao_final != citacao_norm and sem_pontuacao_final in fonte_norm:
        return 1.0, sem_pontuacao_final
    melhor = (0.0, None)
    for janela in _janelas(texto_fonte, len(citacao_norm)):
        score = SequenceMatcher(None, citacao_norm, janela).ratio()
        if score > melhor[0]:
            melhor = (score, janela)
            if melhor[0] >= 0.999:
                break
    return melhor
 
 
def verificar_citacao(citacao: str, texto_fonte: str, onde: str) -> ResultadoCitacao:
    """Verifica uma citacao contra o texto-fonte. Se a citacao contem
    reticencias (concatenacao de trechos distantes), cada SEGMENTO e
    verificado separadamente """
    c = _normalizar(citacao)
    if not c:
        return ResultadoCitacao(onde=onde, citacao=citacao,
                                status=StatusCitacao.nao_encontrada, similaridade=0.0)
 
    segmentos = [s.strip() for s in _RE_RETICENCIAS.split(citacao) if s.strip()]
 
    if len(segmentos) <= 1:
        # Citacao simples, sem reticencias -- verificacao direta de sempre.
        score, janela = _melhor_similaridade(c, texto_fonte)
    else:

        resultados_segmentos = []
        for seg in segmentos:
            seg_norm = _normalizar(seg)
            if len(seg_norm.split()) < 2:
                # Segmento residual irrelevante (ex: pontuacao solta apos o
                # split) -- nao penaliza a citacao por isso.
                continue
            s, j = _melhor_similaridade(seg_norm, texto_fonte)
            resultados_segmentos.append((s, j))
        if not resultados_segmentos:
            score, janela = _melhor_similaridade(c, texto_fonte)
        else:
            score, janela = min(resultados_segmentos, key=lambda x: x[0])
 
    if score >= 0.999:
        status = StatusCitacao.encontrada
    elif score >= config.CITACAO_SIMILARIDADE_MINIMA:
        status = StatusCitacao.aproximada
    else:
        status = StatusCitacao.nao_encontrada
 
    return ResultadoCitacao(onde=onde, citacao=citacao, status=status,
                            similaridade=round(float(score), 3), trecho_encontrado=janela)
 
 
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