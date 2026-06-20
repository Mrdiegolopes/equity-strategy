"""
Camada de LLM: parser de cenario e gerador de rationale

dois provedores: ANTHOPIC E GENAI

O LLM traduzir cenario, vetor de choque (entrada), narrar o ranking ja calculado (saida)
NUnca calcula o impacto setorial nem reordena setores.
"""
from __future__ import annotations
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from schemas import ChoqueMacro, NarrativaLLM

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

 # Detecta truncamento por limite de tokens antes que o JSON incompleto
    # quebre a validação do Pydantic com erros genéricos (ex: "Field required")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Resposta da Anthropic foi truncada por max_tokens "
            f"({MAX_OUTPUT_TOKENS}). Aumente MAX_OUTPUT_TOKENS em "
            f"llm_client.py ou reduza o numero de setores no ranking "
            f"(top_n em run.py).")

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


# GEMINI FLASH — response_schema nativo (SDK google-genai)

def _resolver_refs_schema(schema: dict) -> dict:
 # Resolve referências internas e limpa incompatibilidades do Pydantic para a API do Gemini
   '''
    dois bugs conhecidos do SDK oficial (googleapis/python-genai):
     $defs/$ref injeta schemas aninhados inline para evitar falhas do transformer 
       do SDK com referências indiretas 
    
     additionalProperties: Remove o campo recursivamente, pois a API do Gemini 
       estoura erro 400 ao recebe.  validação final do payload via 
       `model_validate` garante o bloqueio a campos extras no output.
'''
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

    # Schema resolvido manualmente (sem $ref) para suportar os modelos
    # Pydantic aninhados do projeto -- ver _resolver_refs_schema acima.
    schema_resolvido = _resolver_refs_schema(schema_model.model_json_schema())

    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0,
        response_mime_type="application/json",
        response_schema=schema_resolvido,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    modelo_nome = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=modelo_nome, contents=user, config=config)

            # Deteccao explicita de truncamento -- espelha o tratamento da
            # Anthropic. Checar finish_reason ANTES de acessar .text evita
            # excecoes confusas quando a resposta foi cortada
            candidato = resp.candidates[0] if resp.candidates else None
            finish_reason = getattr(candidato, "finish_reason", None)
            if finish_reason is not None and "MAX_TOKENS" in str(finish_reason):
                thoughts = getattr(getattr(resp, "usage_metadata", None),
                                   "thoughts_token_count", None)
                raise RuntimeError(
                    f"Resposta do Gemini foi truncada por max_output_tokens "
                    f"({MAX_OUTPUT_TOKENS}). thinking_config ja esta com "
                    f"thinking_budget=0, mas tokens de raciocinio interno "
                    f"({thoughts if thoughts else 'quantidade desconhecida'}) "
                    f"podem ainda estar consumindo parte do orcamento -- bug "
                    f"conhecido em alguns modelos Gemini 2.5 (thinking_budget=0 "
                    f"as vezes e ignorado). Tente aumentar MAX_OUTPUT_TOKENS "
                    f"em llm_client.py, ou trocar GEMINI_MODEL para "
                    f"'gemini-2.0-flash' (sem thinking).")

            dados = json.loads(resp.text)
            return schema_model.model_validate(dados)
        except RuntimeError:
            raise  # truncamento 
        except Exception as e:
            if attempt == 2:
                texto_resp = None
                try:
                    texto_resp = resp.text[:300]
                except Exception:
                    pass
                raise RuntimeError(
                    f"Gemini falhou apos 3 tentativas usando modelo "
                    f"'{modelo_nome}': {e}\n"
                    f"Resposta: {texto_resp or 'indisponivel'}\n"
                    f"Se o erro for 'model not found', confira nomes "
                    f"validos em https://ai.google.dev/gemini-api/docs/models "
                    f"e ajuste a variavel de ambiente GEMINI_MODEL.")
            import time
            time.sleep(2)


# DISPATCHER

def _chamar(system: str, user: str, schema_model, provedor: str | None = None):
    prov = _provedor(provedor)
    if prov == "anthropic":
        return _call_anthropic(system, user, schema_model)
    return _call_gemini(system, user, schema_model)

# INTERFACE

def parse_cenario(cenario: str, provedor: str | None = None) -> ChoqueMacro:
    """ETAPA 1: cenario em linguagem natural vetor de choque estruturado"""
    system = _ler_prompt("parser_cenario.txt")
    return _chamar(system, f"Cenario macro:\n{cenario}", ChoqueMacro, provedor)


def gerar_narrativa(cenario: str, choque: ChoqueMacro,
                    ranking_top: list[dict],
                    ranking_bottom: list[dict],
                    provedor: str | None = None) -> NarrativaLLM:
    """ETAPA 4: narra o ranking JA CALCULADO pelo motor quantitativo.
    O LLM recebe o ranking pronto."""
    system = _ler_prompt("gerar_rationale.txt")
    payload = {
        "cenario_original": cenario,
        "choque": choque.model_dump(),
        "setores_beneficiados_ranking": ranking_top,
        "setores_prejudicados_ranking": ranking_bottom,
        "tickers_por_setor": _tickers_por_setor(),
    }
    user = ("Aqui esta o resultado do modelo quantitativo. "
            "Narre conforme as regras.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2))
    return _chamar(system, user, NarrativaLLM, provedor)


def _tickers_por_setor() -> dict:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config
    return config.SETORES