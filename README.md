# Aora — AI Clipping

Daily digest of AI news from ~60 sources, summarized by an LLM (Claude Haiku or Gemini Flash) and saved as a Markdown file ready for [Obsidian Dataview](https://blacksmithgu.github.io/obsidian-dataview/).

Each run fetches new items from RSS feeds and scraped websites, sends them through the configured model for structured summarization (TL;DR + why it matters + tags), and writes a versioned daily file.

## Output

```
output/2026-05-17-v1.md
```

```yaml
---
date: 2026-05-17
type: ai-clipping
total_items: 42
sources_com_erro: []
---

# Foundation Models & Labs

## Anthropic — Claude 4 System Card
**Data:** Sat, 17 May 2026 10:00:00 +0000
**Link:** https://www.anthropic.com/research/claude-4-system-card
**Categoria:** #foundation-model

**TL;DR:** Anthropic publishes the system card for Claude 4, detailing safety evaluations...
**Por que importa:** First model in the series to undergo pre-deployment CBRN red-teaming...
**Tags:** #foundation-model #pesquisa #segurança
```

Re-running on the same day increments the version (`-v2.md`, `-v3.md`) and merges with previous items.

## Sources

**28 RSS feeds** — OpenAI, Google AI, DeepMind, Meta AI, Microsoft Research, AWS ML, NVIDIA, Apple ML, Databricks, Hugging Face, GitHub, LangChain, Character.AI, ArXiv CS.AI, MIT Tech Review, TechCrunch AI, The Verge AI, Ars Technica, IEEE Spectrum, VentureBeat, Ahead of AI, Interconnects, Import AI, Last Week in AI, Simon Willison, Pandaily, Writer, The M.Akita Chronicles

**31 scraped websites** (sitemap / static HTML / Playwright) — Anthropic, Mistral AI, Cohere, xAI, Cerebras, SambaNova, Groq, Together AI, Runway, ElevenLabs, Cursor, Weights & Biases, Allen AI, Manus AI, Cognition AI, Harvey AI, Novita AI, Venice.ai, AAIF, Moonshot AI (Kimi), Sakana AI, Qwen, MiniMax, Snowflake, Modal Labs, ByteDance, Scale AI, Replit, DeepSeek, NanoGPT, Tessl

See [SOURCE_NOTES.md](SOURCE_NOTES.md) for context on special scraping flags and sources without RSS coverage.

## Installation

```bash
git clone https://github.com/renatobardi/Aora.git
cd Aora
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Run the interactive setup wizard:

```bash
aora config
```

## Usage

```bash
aora              # full pipeline: RSS + web scraping + LLM
aora rss          # RSS only
aora web          # web scraping only
aora config       # interactive .env setup
```

Output is written to `./output/YYYY-MM-DD-v1.md` by default. Set `OUTPUT_DIR` to an absolute path to write directly into your Obsidian vault.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AI_PROVIDER` | `anthropic` | `anthropic` or `google` |
| `ANTHROPIC_API_KEY` | — | Required if `AI_PROVIDER=anthropic` |
| `GOOGLE_API_KEY` | — | Required if `AI_PROVIDER=google` |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model for enrichment |
| `GOOGLE_MODEL` | `gemini-2.5-flash-lite` | Google model for enrichment |
| `PROCESS_MODE` | `sync` | `sync` (prompt caching) or `async` (Batch API, 50% cheaper, Anthropic-only) |
| `OUTPUT_DIR` | `./output` | Destination folder (Obsidian vault path works) |
| `LOOKBACK_HOURS` | `72` | How far back to look for new items (max 240) |
| `MAX_ITEMS_PER_SOURCE` | `5` | Cap per source per run (max 99) |

## Cost

A typical run with 30–50 new items costs roughly:

- **Claude Haiku** (Anthropic, sync): ~$0.01–$0.03 USD — prompt caching reduces input cost ~90%
- **Claude Haiku** (Anthropic, async Batch API): ~$0.005–$0.015 USD — additional 50% discount
- **Gemini Flash** (Google): ~$0.001–$0.005 USD

## Automation

To run Aora automatically every day, see **[AUTOMATION.md](AUTOMATION.md)** for step-by-step guides covering:

- GitHub Actions (cron workflow, commits output back to repo)
- Claude Code (`/schedule` — session or persistent cloud routine)
- macOS LaunchAgent (recommended for local use — survives sleep)
- crontab (Linux / macOS)

## Managing sources

Sources are stored in `sources.json` (RSS) and `scraped_sources.json` (web scraping) — plain JSON files you can edit directly.

The CLI provides five commands for source management:

```bash
# List all configured sources grouped by category
aora source list

# Add a new source — Claude auto-detects RSS / sitemap / HTML / Playwright
aora source add https://example.com/blog

# Remove a source (two-step confirmation)
aora source remove "Source Name"

# Health report: stale (>30 days), suspect (7–30 days), active (<7 days)
# Populated automatically on every pipeline run
aora source health

# Cross-check RSS ↔ web coverage: finds sites that only have one method
# and proposes adding the complementary config via AI
aora source crosscheck
```

`source add` fetches the URL, probes for RSS link tags and `sitemap.xml`, then asks the configured model to suggest the best scraping strategy. You review the suggestion before it's saved.

`source health` reads `source_health.json`, updated silently on every `aora` run, and shows a color-coded report. Use it to detect feeds that silently stopped producing items.

`source crosscheck` audits all sources for RSS ↔ web scraping coverage gaps. For each RSS-only source it checks if web scraping is viable; for each web-only source it looks for an RSS feed. Results are shown as a consolidated report before any changes are applied.

See [SOURCE_NOTES.md](SOURCE_NOTES.md) for context on special flags (`parser: lxml`, `fetch_dates`, etc.) and why certain sources aren't covered via RSS.

## Wiki Manager

The wiki commands operate on an Obsidian vault and delegate to `claude -p` autonomously:

```bash
aora ingest [file]   # ingest raw clipping file(s) into the wiki
aora lint            # audit vault for contradictions, orphan pages, stale claims
aora query "..."     # answer a question with citations from the wiki
```

See [CLAUDE.md](CLAUDE.md) for vault layout and wiki workflow details.

## License

MIT
