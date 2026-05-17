from __future__ import annotations

import json
import re

import anthropic

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300

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


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


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


def process_item(item: dict, client: anthropic.Anthropic) -> dict:
    user_message = (
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

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        parsed = _parse_json_response(response.content[0].text)

        # sanitize tags to only valid ones
        tags = [t for t in parsed.get("tags", []) if t in VALID_TAGS]

        usage = response.usage
        return {
            **item,
            "tldr": parsed.get("tldr", ""),
            "por_que_importa": parsed.get("por_que_importa", ""),
            "tags": tags,
            "tokens_input": usage.input_tokens,
            "tokens_output": usage.output_tokens,
            "tokens_cache_read": getattr(usage, "cache_read_input_tokens", 0),
        }

    except Exception as exc:
        print(f"  [LLM ERROR] {item['source_name']} — {item['title'][:60]}: {exc}")
        return _fallback(item)


def estimate_cost(input_tokens: int, output_tokens: int, cache_read_tokens: int) -> float:
    # Haiku 4.5 pricing (USD per 1M tokens)
    cost = (
        (input_tokens / 1_000_000) * 0.80
        + (output_tokens / 1_000_000) * 4.00
        + (cache_read_tokens / 1_000_000) * 0.08
    )
    return cost


def process_all(
    items: list[dict], client: anthropic.Anthropic
) -> tuple[list[dict], int, int, int]:
    enriched: list[dict] = []
    total_input = total_output = total_cache = 0

    for i, item in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] {item['source_name']}: {item['title'][:60]}")
        result = process_item(item, client)
        enriched.append(result)
        total_input += result["tokens_input"]
        total_output += result["tokens_output"]
        total_cache += result["tokens_cache_read"]

    return enriched, total_input, total_output, total_cache
