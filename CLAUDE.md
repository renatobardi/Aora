# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**AI Clipping** — Python script that consumes RSS feeds from ~25 AI companies, summarizes each item with Claude Haiku (structured JSON: TL;DR + why it matters + tags), and generates a daily Markdown file ready for Obsidian Dataview.

## Commands

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env          # then fill in ANTHROPIC_API_KEY

# Run
python main.py                # fetches feeds, processes with LLM, writes output/YYYY-MM-DD.md

# Dry-run / debug a single feed
python -c "import feedparser; f = feedparser.parse('https://huggingface.co/blog/feed.xml'); print(len(f.entries), 'entries')"
```

## Architecture

The pipeline is fully sequential and single-process:

```
main.py → fetcher.py → processor.py → renderer.py
```

- **`sources.py`** — static list of RSS feeds (`SOURCES`) + category ordering/labels
- **`fetcher.py`** — RSS fetch via `feedparser`; fallback to full-page extraction via `trafilatura` when summary < 200 chars; deduplication via `seen_ids.json`
- **`processor.py`** — Claude Haiku API calls with **prompt caching** on the system prompt (same system message reused N times → ~90% savings on cached tokens); JSON response parsing with fallback
- **`renderer.py`** — assembles YAML frontmatter + per-item markdown blocks, grouped by category in the order defined in `CATEGORY_ORDER`
- **`main.py`** — orchestrates all stages, writes output file, appends errors to `feed_errors.log`, prints cost summary

## Key behaviors

- **Idempotent**: `seen_ids.json` tracks processed entry IDs. Re-running on the same day adds only new items without duplicates.
- **Fault-tolerant**: each feed is wrapped in individual try/except; failures are logged to `feed_errors.log` and do not block the pipeline.
- **Lookback window**: controlled by `LOOKBACK_HOURS` env var (default 48h) — picks up items published in that window.
- **Model**: `claude-haiku-4-5-20251001` with `cache_control: ephemeral` on the system prompt block.

## Runtime files (generated, not committed)

| File | Purpose |
|---|---|
| `seen_ids.json` | Deduplication state — list of processed entry IDs |
| `feed_errors.log` | Append-only log of feeds that failed, with timestamps |
| `output/YYYY-MM-DD.md` | Daily clipping file for Obsidian |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `OUTPUT_DIR` | `./output` | Absolute path to Obsidian vault folder works too |
| `LOOKBACK_HOURS` | `48` | How far back to look for new items |
| `MAX_ITEMS_PER_SOURCE` | `5` | Cap per feed per run |
