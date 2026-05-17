# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**AI Clipping** — Fetches content from ~50 AI sources (RSS feeds + scraped websites), summarizes each item with Claude Haiku (structured JSON: TL;DR + why it matters + tags), and generates a daily Markdown file ready for Obsidian Dataview.

## Commands

```bash
# Setup
pip install -r requirements.txt
playwright install chromium     # required for JS-heavy scrapers

cp .env.example .env            # then fill in ANTHROPIC_API_KEY

# Run
python main.py                  # fetches all sources, processes with LLM, writes output/YYYY-MM-DD-vN.md

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

The pipeline is fully sequential and single-process:

```
main.py
  ├── fetcher.py        (RSS sources from sources.py)
  └── scraper.py        (web sources from scraped_sources.py)
       ├── sitemap_scraper.py
       ├── html_scraper.py
       └── playwright_scraper.py
  └── processor.py      (Claude Haiku LLM enrichment)
  └── renderer.py       (Markdown output)
```

- **`sources.py`** — RSS feed list (`SOURCES`) + `CATEGORY_ORDER` / `CATEGORY_LABELS`
- **`scraped_sources.py`** — Web scraping config list (`SCRAPED_SOURCES`); each entry has `method: "sitemap" | "html" | "playwright"` and method-specific keys
- **`fetcher.py`** — RSS fetch via `feedparser`; falls back to `trafilatura` when summary < 200 chars; deduplication via `seen_ids`
- **`scraper.py`** — Dispatcher: routes each `SCRAPED_SOURCE` entry to the right scraper based on `method`
- **`sitemap_scraper.py`** — Fetches XML sitemaps (handles sitemap indexes, `lxml` fallback, `fetch_dates`, `fix_protocol`, `sub_pattern` quirks); extracts content with `trafilatura`
- **`html_scraper.py`** — Fetches static listing pages with `httpx`+`BeautifulSoup`, follows matched links, extracts content with `trafilatura`
- **`playwright_scraper.py`** — Uses headless Chromium for JS-rendered listing pages; same content extraction as the others
- **`processor.py`** — Claude Haiku API with **prompt caching** (`cache_control: ephemeral` on the system prompt, reused across all items → ~90% cached-token savings); JSON parsing with fallback
- **`renderer.py`** — Assembles YAML frontmatter + per-item markdown blocks, grouped by `CATEGORY_ORDER`
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
- **Lookback window**: `LOOKBACK_HOURS` env var (default 72h)
- **Model**: `claude-haiku-4-5-20251001` with `cache_control: ephemeral`

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
| `OUTPUT_DIR` | `./output` | Absolute path to Obsidian vault works too |
| `LOOKBACK_HOURS` | `72` | How far back to look for new items |
| `MAX_ITEMS_PER_SOURCE` | `5` | Cap per source per run |
