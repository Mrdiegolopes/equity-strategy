""" FinBERT-PT-BR via Hugging Face Inference Providers. """
from __future__ import annotations
import os
import sys
import time

import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from schemas import AnaliseTom, Tom, ValidacaoFinBERT
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_POS = {Tom.muito_positivo, Tom.positivo}
_NEG = {Tom.negativo, Tom.cauteloso}


_URL_ATUAL = "https://router.huggingface.co/hf-inference/models/{modelo}"

_URL_LEGADA = "https://api-inference.huggingface.co/models/{modelo}"


def _mapear_label(label: str) -> str:
    l = label.lower()
    if "pos" in l:
        return "positivo"
    if "neg" in l:
        return "negativo"
    return "neutro"


def _concorda(tom_llm: Tom, label_finbert: str) -> bool:
    lf = _mapear_label(label_finbert)
    if tom_llm in _POS:
        return lf == "positivo"
    if tom_llm in _NEG:
        return lf in {"negativo", "neutro"}
    return lf == "neutro"


def _post(url: str, token: str, texto: str, timeout: int = 30) -> requests.Response:
    return requests.post(
        url, headers={"Authorization": f"Bearer {token}"},
        json={"inputs": texto}, timeout=timeout)


def _chamar_hf(texto: str) -> tuple[str, float] | None:
    """Chama a API do FinBERT-PT-BR. Tenta o endpoint atual primeiro; se
    falhar por erro de rede/DNS."""
    token = os.getenv("HF_API_TOKEN")
    if not token:
        print("  [FinBERT] HF_API_TOKEN nao definido -- extensao pulada.")
        return None

    modelo = getattr(config, "FINBERT_MODEL", "lucas-leme/FinBERT-PT-BR")
    urls = [_URL_ATUAL.format(modelo=modelo), _URL_LEGADA.format(modelo=modelo)]

    ultimo_erro = None
    for url in urls:
        for tentativa in range(2):  # 1 tentativa + 1 retry para cold start
            try:
                r = _post(url, token, texto)
            except requests.exceptions.ConnectionError as e:
                ultimo_erro = f"falha de conexao/DNS em {url}: {e}"
                break  # nao adianta repetir o mesmo host que nao resolve -- tenta o outro
            except requests.exceptions.Timeout:
                ultimo_erro = f"timeout em {url}"
                continue

            if r.status_code == 200:
                try:
                    data = r.json()
                    preds = (data[0] if isinstance(data, list) and data
                            and isinstance(data[0], list) else data)
                    best = max(preds, key=lambda x: x.get("score", 0))
                    return str(best.get("label")), float(best.get("score", 0))
                except Exception as e:
                    ultimo_erro = f"resposta 200 mas formato inesperado de {url}: {e} | body={r.text[:200]}"
                    break

            if r.status_code == 503:
                # Cold start: modelo carregando no provider. Espera e tenta de novo.
                ultimo_erro = f"503 (cold start) em {url}, aguardando e tentando de novo..."
                time.sleep(8)
                continue

            # 401, 404, etc nao adianta repetir, mas vale tentar o outro host.
            ultimo_erro = f"status {r.status_code} em {url}: {r.text[:200]}"
            break

    print(f"  [FinBERT] Falha ao chamar a API apos tentativas: {ultimo_erro}")
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