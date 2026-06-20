"""
Schemas Pydantic

"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# ETAPA 1 parser de cenario (LLM -> vetor de choque)
class ChoqueMacro(BaseModel):
    """Vetor de choque extraido do cenario em linguagem natural.
    extra='forbid' rejeita campos inventados pelo modelo."""
    model_config = ConfigDict(extra="forbid")

    d_selic: float = Field(description="Variacao da Selic em pontos percentuais (ex: +2.0)")
    d_cambio: float = Field(description="Variacao % do USD/BRL; positivo = real se deprecia (ex: 0.10)")
    ret_commodity: float = Field(description="Variacao % esperada do indice de commodities (ex: -0.15)")
    ret_mercado: float = Field(description="Variacao % esperada do Ibovespa/mercado (ex: -0.05)")
    horizonte_meses: int = Field(description="Em quantos meses o choque se materializa")
    confianca_extracao: Literal["alta", "media", "baixa"] = Field(
        description="Quao explicito foi o cenario sobre cada fator")
    premissas: list[str] = Field(
        default_factory=list,
        description="Premissas que o modelo assumiu para preencher fatores nao explicitos")


# ETAPA 4: rationale e tickers LLM narra sobre numero
class TickerRecomendado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    setor: str
    justificativa: str = Field(description="Por que ESTA empresa, com base em caracteristicas dela")


class RationaleSetor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    setor: str
    direcao: Literal["beneficiado", "prejudicado"]
    mecanismo: str = Field(description="Canal de transmissao em 1-2 frases, ancorado nos fatores")


class RiscoTese(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risco: str
    impacto: str = Field(description="O que acontece com a recomendacao se este risco se materializar")


class NarrativaLLM(BaseModel):
    """Saida da etapa de narracao: o LLM so escreve texto sobre o ranking
    ja calculado. Nao inventa numeros nem reordena setores."""
    model_config = ConfigDict(extra="forbid")
    rationales: list[RationaleSetor]
    tickers_positivos: list[TickerRecomendado]
    tickers_negativos: list[TickerRecomendado]
    riscos: list[RiscoTese]


# SAIDA FINAL 
class ImpactoSetorial(BaseModel):
    setor: str
    impacto_estimado: float
    confianca: str
    r2: float
    contribuicoes: dict[str, float]
    mecanismo: Optional[str] = None


class ResultadoFinal(BaseModel):
    cenario_input: str
    choque: ChoqueMacro
    setores_beneficiados: list[ImpactoSetorial]
    setores_prejudicados: list[ImpactoSetorial]
    tickers_positivos: list[TickerRecomendado]
    tickers_negativos: list[TickerRecomendado]
    riscos: list[RiscoTese]
    avisos_validacao: list[str] = Field(default_factory=list)
