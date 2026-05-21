from __future__ import annotations

import json
import os
import re
import time

from json_repair import repair_json

from provider import BaseProvider

from progress_utils import console, make_progress, make_spinner

MAX_TOKENS = 512

VALID_TAGS = {
    "foundation-model", "inference", "open-source", "agent", "rag",
    "fine-tuning", "infra", "dados", "segurança", "robotica",
    "multimodal", "pesquisa", "produto", "hardware", "regulacao", "open-weight",
}

SYSTEM_PROMPT = """\
Você é um assistente técnico analisando publicações de empresas de AI.
Sua tarefa é gerar um resumo estruturado em JSON, sem texto adicional.
Seja denso e técnico, no estilo Karpathy: foque em implicações reais, não em marketing.

Tags válidas: foundation-model, inference, open-source, agent, rag, fine-tuning, infra, \
dados, segurança, robotica, multimodal, pesquisa, produto, hardware, regulacao, open-weight\
"""

# Preços por 1M tokens (input, output) — valores oficiais maio/2026
_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-3-5-haiku-latest":   (1.00, 5.00),
    "claude-3-7-sonnet-latest":  (3.00, 15.00),
    "claude-sonnet-4-6":         (3.00, 15.00),
    "claude-opus-4-7":           (5.00, 25.00),
}

_GOOGLE_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10,  0.40),
    "gemini-2.5-flash":      (0.30,  2.50),
    "gemini-2.5-pro":        (1.25, 10.00),
    "gemini-3.1-flash-lite": (0.25,  1.50),
    "gemini-3-flash-preview":(0.50,  3.00),
}


def get_model(provider: BaseProvider) -> str:
    if provider.name == "google":
        return os.getenv("GOOGLE_MODEL", "gemini-2.5-flash-lite")
    return os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def _parse_json_response(text: str) -> dict:
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = json.loads(repair_json(raw))
    if isinstance(result, list):
        if len(result) > 1:
            console.print(f"  [WARN] _parse_json_response: lista com {len(result)} elementos, usando apenas o primeiro")
        result = result[0] if result else {}
    if not isinstance(result, dict):
        raise ValueError(f"resposta não é um objeto JSON. Recebido: {raw[:120]!r}")
    return result


def _fallback(item: dict) -> dict:
    return {
        **item,
        "tldr": (item.get("content") or item.get("title", ""))[:200],
        "por_que_importa": "",
        "tags": [],
        "tokens_input": 0,
        "tokens_output": 0,
        "tokens_cache_read": 0,
    }


def _build_user_message(item: dict) -> str:
    return (
        f"Empresa: {item['source_name']}\n"
        f"Título: {item['title']}\n"
        f"Conteúdo: {item['content']}\n\n"
        'Responda APENAS com um JSON:\n'
        '{\n'
        '  "tldr": "Uma frase: o que foi publicado/anunciado.",\n'
        '  "por_que_importa": "1-2 frases: implicação técnica ou estratégica real.",\n'
        '  "tags": ["tag1", "tag2", "tag3"]\n'
        '}'
    )


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    is_async: bool = False,
    provider_name: str = "anthropic",
    model: str = "",
) -> float:
    if provider_name == "google":
        price_input, price_output = _GOOGLE_PRICING.get(model, (0.30, 2.50))
        return (
            (input_tokens / 1_000_000) * price_input
            + (output_tokens / 1_000_000) * price_output
        )

    price_input, price_output = _ANTHROPIC_PRICING.get(model, (1.00, 5.00))
    # cache reads custo = 10% do input
    price_cache_read = price_input * 0.10
    discount = 0.5 if is_async else 1.0

    return (
        (input_tokens / 1_000_000) * (price_input * discount)
        + (output_tokens / 1_000_000) * (price_output * discount)
        + (cache_read_tokens / 1_000_000) * price_cache_read
    )


def process_item_sync(item: dict, provider: BaseProvider) -> dict:
    user_message = _build_user_message(item)
    model = get_model(provider)

    try:
        result = provider.generate(
            model=model,
            system=SYSTEM_PROMPT,
            user=user_message,
            max_tokens=MAX_TOKENS,
        )
        parsed = _parse_json_response(result.text)
        tags = [t for t in parsed.get("tags", []) if t in VALID_TAGS]

        return {
            **item,
            "tldr": parsed.get("tldr", ""),
            "por_que_importa": parsed.get("por_que_importa", ""),
            "tags": tags,
            "tokens_input": result.input_tokens,
            "tokens_output": result.output_tokens,
            "tokens_cache_read": result.cached_tokens,
        }

    except Exception as exc:
        console.print(f"  [LLM ERROR] {item['source_name']} — {item['title'][:60]}: {exc}")
        return _fallback(item)


def process_all_async(
    items: list[dict], provider: BaseProvider
) -> tuple[list[dict], int, int, int]:
    """Anthropic Batch API — 50% discount. Only available when provider.supports_batch."""
    if not provider.supports_batch:
        console.print("  [AVISO] Batch API não disponível para este provider. Usando modo síncrono.")
        return process_all_sync(items, provider)

    if not items:
        return [], 0, 0, 0

    client = provider.client
    model = get_model(provider)

    requests = []
    for i, item in enumerate(items):
        requests.append({
            "custom_id": str(i),
            "params": {
                "model": model,
                "max_tokens": MAX_TOKENS,
                "system": [{"type": "text", "text": SYSTEM_PROMPT}],
                "messages": [{"role": "user", "content": _build_user_message(item)}],
            }
        })

    batch = client.messages.batches.create(requests=requests)

    wait_time = 10
    max_wait_time = 60

    with make_spinner() as progress:
        task = progress.add_task(f"Batch API — aguardando ({len(requests)} itens)")
        progress.console.print(f"  Batch criado: [dim]{batch.id}[/dim]")
        while True:
            status = client.messages.batches.retrieve(batch.id)
            if status.processing_status == "ended":
                break
            elif status.processing_status in ["canceled", "canceling", "expired"]:
                progress.console.print(f"  [ERRO] Batch cancelado ou expirado. Status: {status.processing_status}")
                return [_fallback(item) for item in items], 0, 0, 0

            progress.update(task, description=f"Batch API — aguardando {wait_time}s ({len(requests)} itens)")
            time.sleep(wait_time)

            if wait_time < max_wait_time:
                wait_time += 10
    results = list(client.messages.batches.results(batch.id))

    enriched: list[dict] = []
    total_input = total_output = total_cache = 0

    results_map = {res.custom_id: res for res in results}

    for i, item in enumerate(items):
        res = results_map.get(str(i))

        if res and res.result.type == "succeeded":
            msg = res.result.message
            try:
                parsed = _parse_json_response(msg.content[0].text)
                tags = [t for t in parsed.get("tags", []) if t in VALID_TAGS]

                usage = msg.usage
                total_input += usage.input_tokens
                total_output += usage.output_tokens

                enriched.append({
                    **item,
                    "tldr": parsed.get("tldr", ""),
                    "por_que_importa": parsed.get("por_que_importa", ""),
                    "tags": tags,
                    "tokens_input": usage.input_tokens,
                    "tokens_output": usage.output_tokens,
                    "tokens_cache_read": 0,
                })
            except Exception as exc:
                console.print(f"  [LLM ERROR] {item['source_name']} — Erro no parsing: {exc}")
                enriched.append(_fallback(item))
        else:
            console.print(f"  [LLM ERROR] {item['source_name']} — Falha na API: {getattr(res, 'result', 'Desconhecido')}")
            enriched.append(_fallback(item))

    return enriched, total_input, total_output, total_cache


def process_all_sync(
    items: list[dict], provider: BaseProvider
) -> tuple[list[dict], int, int, int]:
    enriched: list[dict] = []
    total_input = total_output = total_cache = 0

    with make_progress() as progress:
        task = progress.add_task("Processando com LLM", total=len(items))
        for item in items:
            result = process_item_sync(item, provider)
            enriched.append(result)
            total_input += result["tokens_input"]
            total_output += result["tokens_output"]
            total_cache += result["tokens_cache_read"]
            progress.advance(task)

    return enriched, total_input, total_output, total_cache


def process_all(
    items: list[dict], provider: BaseProvider
) -> tuple[list[dict], int, int, int, bool]:
    mode = os.getenv("PROCESS_MODE", "sync")

    if mode == "async":
        enriched, inp, out, cache = process_all_async(items, provider)
        return enriched, inp, out, cache, provider.supports_batch
    else:
        enriched, inp, out, cache = process_all_sync(items, provider)
        return enriched, inp, out, cache, False
