# Aora — AI Clipping

Daily digest of AI news from ~50 sources, summarized by Claude Haiku and saved as a Markdown file ready for [Obsidian Dataview](https://blacksmithgu.github.io/obsidian-dataview/).

Each run fetches new items from RSS feeds and scraped websites, sends them through Claude Haiku for structured summarization (TL;DR + why it matters + tags), and writes a versioned daily file.

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

**27 RSS feeds** — OpenAI, Google AI, DeepMind, Meta AI, Microsoft Research, AWS ML, NVIDIA, Apple ML, Databricks, Hugging Face, GitHub, LangChain, Character.AI, ArXiv CS.AI, MIT Tech Review, TechCrunch AI, The Verge AI, Ars Technica, IEEE Spectrum, VentureBeat, Ahead of AI, Interconnects, Import AI, Last Week in AI, Simon Willison, Pandaily, Writer

**~25 scraped websites** (sitemap / static HTML / Playwright) — Anthropic, Mistral AI, Cohere, xAI, Cerebras, SambaNova, Groq, Together AI, Runway, ElevenLabs, Cursor, Weights & Biases, Allen AI, Novita AI, Venice.ai, AAIF, Moonshot AI (Kimi), Sakana AI, Qwen, MiniMax, Snowflake, Modal Labs, ByteDance, Scale AI, Replit, DeepSeek, NanoGPT, Tessl

## Installation

```bash
git clone https://github.com/renatobardi/Aora.git
cd Aora
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
python3 main.py
```

Output is written to `./output/YYYY-MM-DD-v1.md` by default. Set `OUTPUT_DIR` to an absolute path to write directly into your Obsidian vault.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `OUTPUT_DIR` | `./output` | Destination folder (Obsidian vault path works) |
| `LOOKBACK_HOURS` | `48` | How far back to look for new items |
| `MAX_ITEMS_PER_SOURCE` | `5` | Cap per source per run |

## Cost

Prompt caching on the system prompt reduces input token cost by ~90% across a batch. A typical run with 30–50 new items costs **~$0.01–$0.03 USD** using Claude Haiku.

## Adding sources

See [CLAUDE.md](CLAUDE.md) for the scraper architecture and instructions on adding RSS feeds (`sources.py`) or scraped websites (`scraped_sources.py`).

## License

MIT
