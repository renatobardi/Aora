from __future__ import annotations

import json
import os
import re
import time

import anthropic

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
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
    # Definindo preços base (USD por 1M tokens) dependendo do modelo selecionado
    if "sonnet" in MODEL:
        # Claude 3.7 Sonnet pricing
        price_input = 3.00
        price_output = 15.00
        price_cache_read = 0.30
    elif "haiku-latest" in MODEL or "haiku-3-5" in MODEL:
        # Claude 3.5 Haiku pricing
        price_input = 0.80
        price_output = 4.00
        price_cache_read = 0.08
    else:
        # Fallback (geralmente Haiku 4.5 ou similar)
        price_input = 0.80
        price_output = 4.00
        price_cache_read = 0.08

    # BATCH API tem 50% de desconto no input e output
    cost = (
        (input_tokens / 1_000_000) * (price_input * 0.5)
        + (output_tokens / 1_000_000) * (price_output * 0.5)
        + (cache_read_tokens / 1_000_000) * price_cache_read
    )
    return cost


def process_all(
    items: list[dict], client: anthropic.Anthropic
) -> tuple[list[dict], int, int, int]:
    if not items:
        return [], 0, 0, 0

    print("  Preparando Batch API para 50% de desconto...")
    requests = []
    
    # Criar as requisições em lote
    for i, item in enumerate(items):
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
        
        requests.append({
            "custom_id": str(i),
            "params": {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "system": [
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                    }
                ],
                "messages": [{"role": "user", "content": user_message}],
            }
        })

    # Enviar Batch
    print(f"  Enviando batch com {len(requests)} itens para a Anthropic...")
    batch = client.messages.batches.create(requests=requests)
    
    print(f"  Lote criado (ID: {batch.id}). Aguardando processamento...")
    
    # Polling - esperar terminar
    while True:
        status = client.messages.batches.retrieve(batch.id)
        if status.processing_status == "ended":
            break
        elif status.processing_status in ["canceled", "canceling", "expired"]:
            print(f"  [ERRO] Batch cancelado ou expirado. Status: {status.processing_status}")
            return [_fallback(item) for item in items], 0, 0, 0
        
        # A API de Batch pode demorar, mas geralmente pequenos lotes terminam em segundos/minutos.
        print("  Processando... (aguardando 10s)")
        time.sleep(10)

    # Processar resultados
    print("  Batch concluído! Baixando resultados...")
    results = list(client.messages.batches.results(batch.id))
    
    enriched: list[dict] = []
    total_input = total_output = total_cache = 0

    # Organizar resultados na mesma ordem dos items
    # (A API de batch não garante a ordem dos resultados, por isso mapeamos pelo custom_id)
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
                # API de Batch não usa cache_read_tokens, pois o desconto de batch é fixo.
                
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
                print(f"  [LLM ERROR] {item['source_name']} — Erro no parsing: {exc}")
                enriched.append(_fallback(item))
        else:
            print(f"  [LLM ERROR] {item['source_name']} — Falha na API: {getattr(res, 'result', 'Desconhecido')}")
            enriched.append(_fallback(item))

    return enriched, total_input, total_output, total_cache
