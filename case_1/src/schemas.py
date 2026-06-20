"""Schemas Pydantic do output estruturado do Earnings Call Intelligence."""
from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, conint, confloat

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Tom(str, Enum):
    muito_positivo = "muito_positivo"
    positivo = "positivo"
    neutro = "neutro"
    cauteloso = "cauteloso"
    negativo = "negativo"

class DirecaoMudanca(str, Enum):
    elevado = "elevado"
    reiterado = "reiterado"
    reduzido = "reduzido"
    novo = "novo"
    removido = "removido"

class QualidadeResposta(str, Enum):
    direta = "direta"
    parcial = "parcial"
    evasiva = "evasiva"

class TipoRedFlag(str, Enum):
    hesitacao = "hesitacao"
    mudanca_de_assunto = "mudanca_de_assunto"
    evasao = "evasao"
    contradicao = "contradicao"
    contradicao_acento = "contradição"
    cautela_excessiva = "cautela_excessiva"

class StatusCitacao(str, Enum):
    encontrada = "encontrada"
    aproximada = "aproximada"
    nao_encontrada = "nao_encontrada"

class TrechoCitado(StrictModel):
    citacao: str = Field(..., description="Citação literal curta, copiada da transcrição.")
    speaker: Optional[str] = Field(None, description="Quem falou, se identificável.")
    secao: Optional[str] = Field(None, description="Slide, prepared remarks ou Q&A.")

class AnaliseTom(StrictModel):
    tom: Tom
    resumo: str
    evidencias: List[TrechoCitado] = Field(..., min_length=2, max_length=5)

class MudancaTema(StrictModel):
    tema: str
    direcao: DirecaoMudanca
    descricao: str
    evidencia_atual: TrechoCitado
    evidencia_anterior: Optional[TrechoCitado] = None

class ComparacaoTemporal(StrictModel):
    sintese: str
    mudancas: List[MudancaTema] = Field(..., min_length=1, max_length=8)

class PerguntaCritica(StrictModel):
    analista: str
    pergunta_resumo: str
    por_que_critica: str
    resposta_resumo: str
    qualidade_resposta: QualidadeResposta
    avaliacao_resposta: str
    trecho_pergunta: TrechoCitado
    trecho_resposta: TrechoCitado

class RedFlag(StrictModel):
    tipo: TipoRedFlag
    descricao: str
    severidade: conint(ge=1, le=5)
    trecho: TrechoCitado

class SurpriseScore(StrictModel):
    score: conint(ge=0, le=10)
    resumo: str
    justificativa: str
    evidencias: List[TrechoCitado] = Field(..., min_length=1, max_length=5)

class AnaliseQualitativa(StrictModel):
    tom: AnaliseTom
    perguntas_criticas: List[PerguntaCritica] = Field(..., min_length=1, max_length=5)
    red_flags: List[RedFlag] = Field(default_factory=list, max_length=8)
    surprise: SurpriseScore

class ResultadoCitacao(StrictModel):
    onde: str
    citacao: str
    status: StatusCitacao
    similaridade: confloat(ge=0, le=1)
    trecho_encontrado: Optional[str] = None

class ValidacaoFinBERT(StrictModel):
    trecho: str
    rotulo_finbert: str
    score_finbert: float
    tom_llm: Tom
    concorda_com_llm: bool

class RelatorioInteligencia(StrictModel):
    empresa: str
    ticker: str
    call_atual: str
    call_anterior: str
    tom: AnaliseTom
    comparacao_temporal: ComparacaoTemporal
    perguntas_criticas: List[PerguntaCritica]
    red_flags: List[RedFlag]
    surprise: SurpriseScore
    auditoria_citacoes: List[ResultadoCitacao] = Field(default_factory=list)
    validacao_finbert: List[ValidacaoFinBERT] = Field(default_factory=list)
    avisos_validacao: List[str] = Field(default_factory=list)
