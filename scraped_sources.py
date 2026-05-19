import json
from pathlib import Path

SCRAPED_SOURCES = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
