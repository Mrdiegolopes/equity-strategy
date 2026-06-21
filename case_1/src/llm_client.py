"""
Camada de LLM — extracao estruturada de inteligencia de earnings call.

"""
from __future__ import annotations
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from schemas import AnaliseQualitativa, ComparacaoTemporal

PROMPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")

MAX_OUTPUT_TOKENS = 8000


def _ler_prompt(nome: str) -> str:
    with open(os.path.join(PROMPT_DIR, nome), encoding="utf-8") as f:
        return f.read()


def _provedor(forcado: str | None = None) -> str:
    if forcado:
        if forcado not in ("anthropic", "gemini"):
            raise ValueError(f"Provedor invalido: {forcado!r}. Use 'anthropic' ou 'gemini'.")
        return forcado
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    raise RuntimeError(
        "Nenhuma chave de API encontrada.\n"
        "  Anthropic: defina ANTHROPIC_API_KEY (console.anthropic.com)\n"
        "  Gemini:    defina GEMINI_API_KEY    (aistudio.google.com)\n"
        "  PowerShell: $env:ANTHROPIC_API_KEY='sk-ant-...'")


# ANTHROPIC 


def _call_anthropic(system: str, user: str, schema_model):
    import anthropic
    client = anthropic.Anthropic()
    tool = {
        "name": "responder",
        "description": "Retorna a resposta no formato estruturado exigido.",
        "input_schema": schema_model.model_json_schema(),
    }
    resp = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": "responder"},
        messages=[{"role": "user", "content": user}],
    )

    if resp.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Resposta da Anthropic foi truncada por max_tokens "
            f"({MAX_OUTPUT_TOKENS}). Aumente MAX_OUTPUT_TOKENS em llm_client.py.")

    for block in resp.content:
        if block.type == "tool_use":
            try:
                return schema_model.model_validate(block.input)
            except Exception as e:
                raise RuntimeError(
                    f"Resposta da Anthropic nao bateu com o schema "
                    f"{schema_model.__name__}. Campos recebidos: "
                    f"{list(block.input.keys())}. Erro original: {e}")
    raise RuntimeError("Anthropic nao retornou tool_use — verifique o schema.")


# GEMINI FLASH

def _resolver_refs_schema(schema: dict) -> dict:
    """Resolve $ref/$defs e remove `additionalProperties` dois campos que
    o Pydantic gera e que a API do Gemini nao aceita  """
    defs = schema.pop("$defs", {})

    def _resolve(node):
        if isinstance(node, dict):
            node = {k: v for k, v in node.items() if k != "additionalProperties"}
            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                resolved = dict(defs.get(ref_name, {}))
                resolved.pop("title", None)
                resolved.pop("additionalProperties", None)
                return _resolve(resolved)
            return {k: _resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(schema)


def _call_gemini(system: str, user: str, schema_model):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    schema_resolvido = _resolver_refs_schema(schema_model.model_json_schema())

    config_gen = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0,
        response_mime_type="application/json",
        response_schema=schema_resolvido,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        # Gemini 2.5 conta tokens de "thinking" dentro do mesmo orcamento de
        # max_output_tokens, truncando o JSON visivel. 
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    modelo_nome = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=modelo_nome, contents=user, config=config_gen)

            candidato = resp.candidates[0] if resp.candidates else None
            finish_reason = getattr(candidato, "finish_reason", None)
            if finish_reason is not None and "MAX_TOKENS" in str(finish_reason):
                raise RuntimeError(
                    f"Resposta do Gemini truncada por max_output_tokens "
                    f"({MAX_OUTPUT_TOKENS}) apesar de thinking_budget=0. "
                    f"Aumente MAX_OUTPUT_TOKENS ou troque GEMINI_MODEL para "
                    f"'gemini-2.0-flash' (sem thinking).")

            dados = json.loads(resp.text)
            return schema_model.model_validate(dados)
        except RuntimeError:
            raise
        except Exception as e:
            if attempt == 2:
                texto_resp = None
                try:
                    texto_resp = resp.text[:300]
                except Exception:
                    pass
                raise RuntimeError(
                    f"Gemini falhou apos 3 tentativas (modelo '{modelo_nome}'): {e}\n"
                    f"Resposta: {texto_resp or 'indisponivel'}\n"
                    f"Se for 'model not found', ajuste GEMINI_MODEL.")
            import time
            time.sleep(2)


# DISPATCHER

def _chamar(system: str, user: str, schema_model, provedor: str | None = None):
    prov = _provedor(provedor)
    if prov == "anthropic":
        return _call_anthropic(system, user, schema_model)
    return _call_gemini(system, user, schema_model)

# INTERFACE PUBLICA

def analisar_call(prepared_remarks: str, qa_texto: str,
                  empresa: str, rotulo: str,
                  top_n_perguntas: int,
                  provedor: str | None = None) -> AnaliseQualitativa:
    """Extrai tom, perguntas criticas, red flags e surprise score da call atual.

    Recebe a apresentacao e o Q&A ja separados pela ingestao -- o LLM nao
    precisa descobrir onde um termina e o outro comeca, o que reduz erro."""
    system = _ler_prompt("analisar_call.txt").format(
        empresa=empresa, rotulo=rotulo, top_n=top_n_perguntas)
    user = (
        f"=== APRESENTACAO DO MANAGEMENT ({empresa}, {rotulo}) ===\n"
        f"{prepared_remarks}\n\n"
        f"=== SESSAO DE PERGUNTAS E RESPOSTAS ===\n"
        f"{qa_texto}")
    return _chamar(system, user, AnaliseQualitativa, provedor)


def comparar_trimestres(remarks_atual: str, remarks_anterior: str,
                        rotulo_atual: str, rotulo_anterior: str,
                        provedor: str | None = None) -> ComparacaoTemporal:
    """Compara guidance e temas entre a call atual e a anterior
    
    Recebe so as apresentacoes (prepared remarks) das duas calls e ali que
    guidance e temas estrategicos sao declarados, nao no Q&A."""
    system = _ler_prompt("comparar_trimestres.txt").format(
        rotulo_atual=rotulo_atual, rotulo_anterior=rotulo_anterior)
    user = (
        f"=== CALL ANTERIOR ({rotulo_anterior}) ===\n{remarks_anterior}\n\n"
        f"=== CALL ATUAL ({rotulo_atual}) ===\n{remarks_atual}")
    return _chamar(system, user, ComparacaoTemporal, provedor)