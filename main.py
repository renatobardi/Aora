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
from version import VERSION
from wiki_manager import run_ingest, run_lint, run_query
from source_manager import list_sources, add_source, remove_source

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


_HelpFmt = argparse.RawDescriptionHelpFormatter

_ENV_ALL = """\
variáveis de ambiente:
  ANTHROPIC_API_KEY       obrigatória
  ANTHROPIC_MODEL         modelo LLM      (padrão: claude-haiku-4-5-20251001)
  PROCESS_MODE            sync | async    (padrão: sync — async usa Batch API, 50% mais barato)
  OUTPUT_DIR              saída / vault   (padrão: ./output)
  LOOKBACK_HOURS          janela horas    (padrão: 72, máx: 240)
  MAX_ITEMS_PER_SOURCE    cap por fonte   (padrão: 5, máx: 99)

fontes configuradas em sources.json (RSS) e scraped_sources.json (web)
use 'aora source list' para listar, 'aora source add <url>' para adicionar"""

_ENV_SOURCE_ADD = """\
variáveis relevantes:
  ANTHROPIC_API_KEY    obrigatória
  ANTHROPIC_MODEL      modelo usado para sugerir a configuração (padrão: claude-haiku-4-5-20251001)"""

_ENV_CLIPPING = """\
variáveis relevantes:
  LOOKBACK_HOURS          janela de busca em horas  (padrão: 72, máx: 240)
  MAX_ITEMS_PER_SOURCE    cap de itens por fonte    (padrão: 5, máx: 99)
  PROCESS_MODE            sync | async              (padrão: sync)
  OUTPUT_DIR              diretório de saída        (padrão: ./output)"""

_ENV_WIKI = """\
variáveis relevantes:
  OUTPUT_DIR    raiz do vault Obsidian (padrão: ./output)
                se terminar em /raw, a raiz é o diretório pai"""


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aora",
        description=(
            "Aora — AI Clipping & Wiki Manager\n\n"
            "Busca conteúdo de ~50 fontes de IA, resume com Claude Haiku\n"
            "e gera um arquivo Markdown diário para Obsidian."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_ALL,
    )
    parser.add_argument("-v", "--version", action="version", version=f"Aora v{VERSION}", help="mostra a versão e sai")

    subparsers = parser.add_subparsers(dest="command", metavar="comando")

    # --- Clipping ---
    subparsers.add_parser(
        "all",
        help="pipeline completo: RSS + web scraping + LLM (padrão)",
        description=(
            "Executa o pipeline completo: coleta RSS, web scraping e enriquecimento LLM.\n"
            "Equivalente a rodar aora sem nenhum argumento."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_CLIPPING,
    )
    subparsers.add_parser(
        "rss",
        help="busca apenas feeds RSS",
        description=(
            "Coleta apenas os feeds RSS configurados em sources.json.\n"
            "Não executa web scraping."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_CLIPPING,
    )
    subparsers.add_parser(
        "web",
        help="executa apenas o web scraping",
        description=(
            "Executa apenas o web scraping das fontes em scraped_sources.json.\n"
            "Não coleta feeds RSS."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_CLIPPING,
    )
    subparsers.add_parser(
        "config",
        help="assistente interativo de configuração (.env)",
        description=(
            "Abre o wizard interativo para criar ou atualizar o arquivo .env.\n"
            "Configure ANTHROPIC_API_KEY, OUTPUT_DIR, LOOKBACK_HOURS e outros parâmetros."
        ),
        formatter_class=_HelpFmt,
    )

    # --- Wiki Manager ---
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="ingere arquivo(s) raw na wiki via Claude",
        description=(
            "Ingere arquivos raw não processados na wiki via claude -p.\n"
            "Sem argumento: processa todos os raw/*.md ainda não registrados em wiki/log.md."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_WIKI,
    )
    ingest_parser.add_argument(
        "file",
        nargs="?",
        metavar="arquivo",
        help="arquivo raw específico para ingerir (relativo a <vault>/raw/; opcional)",
    )

    subparsers.add_parser(
        "lint",
        help="auditoria de saúde da wiki",
        description=(
            "Examina o vault em busca de contradições, páginas órfãs, claims\n"
            "desatualizados e cross-references faltando.\n"
            "Corrige automaticamente os issues de severidade HIGH."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_WIKI,
    )

    query_parser = subparsers.add_parser(
        "query",
        help="consulta a wiki como base de conhecimento",
        description=(
            "Responde uma pergunta sintetizando informações da wiki com citações.\n"
            "Respostas não-triviais são salvas automaticamente em wiki/analyses/."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_WIKI,
    )
    query_parser.add_argument(
        "question",
        nargs="+",
        metavar="pergunta",
        help="pergunta a responder (use aspas para frases longas)",
    )

    # --- Source Manager ---
    source_parser = subparsers.add_parser(
        "source",
        help="gerenciar fontes (listar, adicionar, remover)",
        description=(
            "Gerencia as fontes de notícias do Aora.\n\n"
            "As fontes ficam em sources.json (RSS) e scraped_sources.json (web).\n"
            "Edite os arquivos diretamente ou use os subcomandos abaixo."
        ),
        formatter_class=_HelpFmt,
    )
    source_sub = source_parser.add_subparsers(dest="source_cmd", metavar="ação")

    source_sub.add_parser(
        "list",
        help="lista todas as fontes configuradas",
        description=(
            "Lista todas as fontes RSS e web scraping configuradas,\n"
            "agrupadas por categoria e ordenadas por prioridade editorial."
        ),
        formatter_class=_HelpFmt,
    )

    source_add_parser = source_sub.add_parser(
        "add",
        help="adiciona nova fonte via URL (usa Claude para auto-detectar configuração)",
        description=(
            "Busca a URL fornecida, detecta feeds RSS e sitemaps disponíveis,\n"
            "e consulta Claude para sugerir a configuração ideal:\n"
            "RSS, sitemap, HTML estático ou Playwright (JS-heavy).\n\n"
            "A sugestão é exibida para revisão antes de ser salva.\n"
            "URLs sem esquema recebem https:// automaticamente."
        ),
        formatter_class=_HelpFmt,
        epilog=_ENV_SOURCE_ADD,
    )
    source_add_parser.add_argument("url", help="URL da fonte a adicionar")

    source_remove_parser = source_sub.add_parser(
        "remove",
        help="remove uma fonte pelo nome (com dupla confirmação)",
        description=(
            "Busca a fonte pelo nome (insensível a maiúsculas).\n"
            "Exibe a configuração completa e solicita duas confirmações antes de remover.\n"
            "Nomes parciais exibem sugestões sem remover nada."
        ),
        formatter_class=_HelpFmt,
    )
    source_remove_parser.add_argument("name", help="nome da fonte a remover (exato ou parcial para sugestões)")

    args = parser.parse_args()
    
    # Compatibilidade com o formato antigo que não usava subparser
    if args.command is None:
        args.command = "all"

    if args.command == "source":
        if not hasattr(args, "source_cmd") or args.source_cmd is None:
            source_parser.print_help()
            sys.exit(0)
        if args.source_cmd == "list":
            list_sources()
        elif args.source_cmd == "add":
            load_dotenv()
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                print("ERRO: ANTHROPIC_API_KEY não definida. Execute 'aora config' primeiro.")
                sys.exit(1)
            client = anthropic.Anthropic(api_key=api_key)
            add_source(args.url, client)
        elif args.source_cmd == "remove":
            remove_source(args.name)
        sys.exit(0)

    if args.command == "config":
        run_setup()
        sys.exit(0)

    load_dotenv()

    # Wiki commands use claude -p (own auth) — route before API key check
    if args.command in ["ingest", "lint", "query"]:
        print("\n" + "="*50)
        print("  █▀█ █▀█ █▀█ █▀█  :: Wiki Manager")
        print(f"  █▀█ █▄█ █▀▄ █▀█  :: AI Clipping v{VERSION}")
        print("="*50 + "\n")

        if args.command == "ingest":
            run_ingest(args.file)
        elif args.command == "lint":
            run_lint()
        elif args.command == "query":
            run_query(" ".join(args.question))

        sys.exit(0)

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
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "72"))
    max_items = int(os.getenv("MAX_ITEMS_PER_SOURCE", "5"))

    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    cache_path = Path(f".cache_{today.isoformat()}.json")

    # Version: find next v number for today
    existing = sorted(output_dir.glob(f"{today.isoformat()}-v*.md"))
    next_version = len(existing) + 1
    output_path = output_dir / f"{today.isoformat()}-v{next_version}.md"

    print("\n" + "="*50)
    print("  █▀█ █▀█ █▀█ █▀█  :: Hoje: " + today.isoformat())
    print(f"  █▀█ █▄█ █▀▄ █▀█  :: AI Clipping v{VERSION}")
    print("="*50)
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
        print(f"{len(rss_items)} itens RSS novos | {len(rss_errors)} feeds com erro [◈]")
        print()
    else:
        updated_ids = seen_ids.copy()

    # 3. Scrape web sources
    scraped_items, scraped_errors = [], []
    if args.command in ["all", "web"]:
        print("Scraping web...")
        scraped_items, scraped_errors, updated_ids = scrape_all(SCRAPED_SOURCES, updated_ids, lookback_hours, max_items)
        print(f"{len(scraped_items)} itens scraping novos | {len(scraped_errors)} fontes com erro [◈]")
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
    enriched, total_input, total_output, total_cache, is_async = process_all(new_items, client)
    print()

    # 4. Merge with previous items and render full day
    all_today = previous_items + enriched
    content = render_daily(all_today, error_sources, today)
    output_path.write_text(content)
    print(f"Arquivo salvo: {output_path} ({len(all_today)} itens no total) [◈]")

    # 5. Persist state
    save_seen_ids(updated_ids, SEEN_IDS_PATH)
    save_daily_items(all_today, cache_path)
    log_errors(error_sources)

    # 6. Summary
    cost = estimate_cost(total_input, total_output, total_cache, is_async)
    print()
    print("=" * 50)
    print(f"✓ {len(enriched)} novos | {len(all_today)} total no dia")
    print(f"✗ {len(error_sources)} feeds com erro")
    print(f"  Tokens: {total_input} input / {total_output} output / {total_cache} cached")
    print(f"  Custo estimado: ~${cost:.4f} USD")
    print("=" * 50)


if __name__ == "__main__":
    main()
