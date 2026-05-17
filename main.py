from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from fetcher import fetch_all, load_seen_ids, save_seen_ids
from processor import estimate_cost, process_all
from renderer import render_daily
from scraper import scrape_all
from scraped_sources import SCRAPED_SOURCES
from sources import SOURCES
from config_wizard import run_setup

SEEN_IDS_PATH = "seen_ids.json"
ERRORS_LOG_PATH = "feed_errors.log"


def load_daily_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_daily_items(items: list[dict], path: Path) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def log_errors(error_sources: list[str]) -> None:
    if not error_sources:
        return
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(ERRORS_LOG_PATH, "a") as f:
        f.write(f"\n[{timestamp}]\n")
        for name in error_sources:
            f.write(f"  ERRO: {name}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aora — AI Clipping")
    parser.add_argument("command", nargs="?", default="all", choices=["all", "rss", "web", "config"], help="O comando a ser executado: 'all' (padrão), 'rss', 'web' ou 'config'")
    args = parser.parse_args()

    if args.command == "config":
        run_setup()
        sys.exit(0)

    load_dotenv()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Aora não configurado. Iniciando assistente...")
        run_setup()
        load_dotenv(override=True)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERRO: Configuração cancelada ou ANTHROPIC_API_KEY não definida.")
            sys.exit(1)

    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "48"))
    max_items = int(os.getenv("MAX_ITEMS_PER_SOURCE", "5"))

    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    cache_path = Path(f".cache_{today.isoformat()}.json")

    # Version: find next v number for today
    existing = sorted(output_dir.glob(f"{today.isoformat()}-v*.md"))
    next_version = len(existing) + 1
    output_path = output_dir / f"{today.isoformat()}-v{next_version}.md"

    print(f"AI Clipping — {today.isoformat()}")
    print(f"Janela: {lookback_hours}h | Max por fonte: {max_items}")
    print(f"Saída: {output_path}")
    print()

    # 1. Load deduplication state + today's already-processed items
    seen_ids = load_seen_ids(SEEN_IDS_PATH)
    previous_items = load_daily_items(cache_path)
    print(f"IDs já vistos: {len(seen_ids)} | Itens do dia já processados: {len(previous_items)}")
    print()

    rss_items, rss_errors = [], []
    if args.command in ["all", "rss"]:
        print("Buscando feeds RSS...")
        rss_items, rss_errors, updated_ids = fetch_all(SOURCES, seen_ids, lookback_hours, max_items)
        print(f"\n{len(rss_items)} itens RSS novos | {len(rss_errors)} feeds com erro")
        print()
    else:
        updated_ids = seen_ids.copy()

    # 3. Scrape web sources
    scraped_items, scraped_errors = [], []
    if args.command in ["all", "web"]:
        print("Scraping web...")
        scraped_items, scraped_errors, updated_ids = scrape_all(SCRAPED_SOURCES, updated_ids, lookback_hours, max_items)
        print(f"\n{len(scraped_items)} itens scraping novos | {len(scraped_errors)} fontes com erro")
        print()

    new_items = rss_items + scraped_items
    error_sources = rss_errors + scraped_errors

    if not new_items:
        print("Nenhum item novo. Encerrando.")
        save_seen_ids(updated_ids, SEEN_IDS_PATH)
        log_errors(error_sources)
        if not output_path.exists() and previous_items:
            output_path.write_text(render_daily(previous_items, error_sources, today))
            print(f"Arquivo regenerado: {output_path}")
        return

    # 3. Process new items with LLM
    client = anthropic.Anthropic(api_key=api_key)
    print("Processando com Claude Haiku...")
    enriched, total_input, total_output, total_cache = process_all(new_items, client)
    print()

    # 4. Merge with previous items and render full day
    all_today = previous_items + enriched
    content = render_daily(all_today, error_sources, today)
    output_path.write_text(content)
    print(f"Arquivo salvo: {output_path} ({len(all_today)} itens no total)")

    # 5. Persist state
    save_seen_ids(updated_ids, SEEN_IDS_PATH)
    save_daily_items(all_today, cache_path)
    log_errors(error_sources)

    # 6. Summary
    cost = estimate_cost(total_input, total_output, total_cache)
    print()
    print("=" * 50)
    print(f"✓ {len(enriched)} novos | {len(all_today)} total no dia")
    print(f"✗ {len(error_sources)} feeds com erro")
    print(f"  Tokens: {total_input} input / {total_output} output / {total_cache} cached")
    print(f"  Custo estimado: ~${cost:.4f} USD")
    print("=" * 50)


if __name__ == "__main__":
    main()
