# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Aora** — Fetches content from ~50 AI sources (RSS feeds + scraped websites), summarizes each item with Claude Haiku (structured JSON: TL;DR + why it matters + tags), and generates a daily Markdown file ready for Obsidian Dataview. A Wiki Manager layer (in progress) lets you ingest, lint, and query the Obsidian vault via Claude Code.

## Commands

```bash
# Setup
pip install -r requirements.txt
playwright install chromium     # required for JS-heavy scrapers

python main.py config           # interactive setup wizard (creates/updates .env)

# Run — clipping pipeline
python main.py                  # full pipeline (RSS + web scraping + LLM)
python main.py all              # same as above
python main.py rss              # RSS only
python main.py web              # web scraping only

# Wiki Manager (delegates to claude -p "..." internally)
python main.py ingest <file>    # ingest a raw clipping file into the wiki
python main.py lint             # audit wiki for contradictions and orphan pages
python main.py query <question> # query the wiki as a knowledge base

# Convenience wrapper (runs from any directory)
./aora [subcommand]

# Debug a single RSS feed
python -c "import feedparser; f = feedparser.parse('https://huggingface.co/blog/feed.xml'); print(len(f.entries), 'entries')"

# Debug a single scraped source
python -c "
from scraped_sources import SCRAPED_SOURCES
from scraper import scrape_all
items, errors, _ = scrape_all([SCRAPED_SOURCES[0]], set(), 48, 3)
print(items, errors)
"
```

## Architecture

```
main.py  (subcommand router + clipping orchestrator)
  ├── config_wizard.py  (interactive .env setup)
  ├── wiki_manager.py   (ingest / lint / query — delegates to claude -p)
  ├── fetcher.py        (RSS via sources.py)
  └── scraper.py        (web via scraped_sources.py)
       ├── sitemap_scraper.py
       ├── html_scraper.py
       └── playwright_scraper.py
  └── processor.py      (Claude Haiku LLM enrichment — sync or Batch API)
  └── renderer.py       (Markdown output)
```

- **`sources.py`** — RSS feed list (`SOURCES`) + `CATEGORY_ORDER` / `CATEGORY_LABELS`
- **`scraped_sources.py`** — Web scraping config list (`SCRAPED_SOURCES`); each entry has `method: "sitemap" | "html" | "playwright"` and method-specific keys
- **`fetcher.py`** — RSS fetch via `feedparser`; falls back to `trafilatura` when summary < 200 chars; deduplication via `seen_ids`
- **`scraper.py`** — Dispatcher: routes each `SCRAPED_SOURCE` entry to the right scraper based on `method`
- **`sitemap_scraper.py`** — Fetches XML sitemaps (handles sitemap indexes, `lxml` fallback, `fetch_dates`, `fix_protocol`, `sub_pattern` quirks); extracts content with `trafilatura`
- **`html_scraper.py`** — Fetches static listing pages with `httpx`+`BeautifulSoup`, follows matched links, extracts content with `trafilatura`
- **`playwright_scraper.py`** — Uses headless Chromium for JS-rendered listing pages; same content extraction as the others
- **`processor.py`** — Claude Haiku via sync (`messages.create` with `cache_control: ephemeral`) or async (Batch API, 50% discount, polling loop). Model and mode are read from env vars at call time.
- **`renderer.py`** — Assembles YAML frontmatter + per-item markdown blocks, grouped by `CATEGORY_ORDER`
- **`config_wizard.py`** — Interactive terminal wizard that writes/updates `.env`; called by `main.py config` or auto-triggered when `ANTHROPIC_API_KEY` is missing
- **`wiki_manager.py`** — Skeleton for Wiki Manager commands; `run_ingest` detects unprocessed `raw/*.md` files by diffing against `wiki/log.md`; `ingest`/`lint`/`query` shell out to `claude -p "..."` (work in progress)
- **`main.py`** — Orchestrates all stages; merges today's new items with `.cache_YYYY-MM-DD.json`; writes versioned output (`YYYY-MM-DD-vN.md`)

## Item shape

All scrapers and the RSS fetcher produce dicts with the same keys:
```python
{"id": str, "title": str, "url": str, "published": str, "source_name": str, "category": str, "content": str}
```
`id` is always the URL (used for deduplication in `seen_ids.json`). `content` is truncated to 4000 chars before LLM processing.

## Adding a new scraped source

Add an entry to `SCRAPED_SOURCES` in `scraped_sources.py`. Required keys by method:

| method | Required keys |
|---|---|
| `sitemap` | `sitemap_url`, `url_pattern` |
| `html` | `listing_url`, `link_pattern`, `base_url` |
| `playwright` | `listing_url`, `link_pattern` |

Optional sitemap keys: `parser: "lxml"` (invalid XML), `fetch_dates: True` (no `lastmod`), `fix_protocol: True` (missing `https://`), `sub_pattern` (filter sub-sitemaps by substring).

Optional playwright key: `wait_until` — Playwright load event (`"networkidle"` default; use `"domcontentloaded"` for SPAs that never stop making requests).

## Key behaviors

- **Versioned output**: each run writes a new `YYYY-MM-DD-vN.md`; items from previous runs today are loaded from `.cache_YYYY-MM-DD.json` and merged
- **Idempotent**: `seen_ids.json` tracks processed URLs/entry IDs — re-running skips already-seen items
- **Fault-tolerant**: each source is wrapped in try/except; failures are logged to `feed_errors.log` and do not block the pipeline
- **Sync vs async**: `PROCESS_MODE=sync` (default) uses streaming Haiku with prompt caching; `PROCESS_MODE=async` uses the Batch API (50% cheaper, minutes of latency)
- **Lookback window**: controlled by `LOOKBACK_HOURS` env var (default 72h)

## Runtime files (generated, not committed)

| File | Purpose |
|---|---|
| `seen_ids.json` | Deduplication state |
| `.cache_YYYY-MM-DD.json` | Today's processed items (enables versioned re-runs) |
| `feed_errors.log` | Append-only failure log |
| `output/YYYY-MM-DD-vN.md` | Daily clipping file for Obsidian |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Model used for LLM enrichment |
| `PROCESS_MODE` | `sync` | `sync` (prompt caching) or `async` (Batch API, 50% cheaper) |
| `OUTPUT_DIR` | `./output` | Output directory; set to Obsidian vault path for direct integration |
| `LOOKBACK_HOURS` | `72` | How far back to look for new items (max 240) |
| `MAX_ITEMS_PER_SOURCE` | `5` | Cap per source per run (max 99) |
