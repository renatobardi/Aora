import json
from pathlib import Path

SOURCES = json.loads((Path(__file__).parent / "sources.json").read_text())

CATEGORY_ORDER = [
    "foundation-model",
    "big-tech",
    "infra-data",
    "dev-tools",
    "generative",
    "agents-search",
    "research",
    "media",
    "newsletter",
    "china",
]

CATEGORY_LABELS = {
    "foundation-model": "Foundation Models & Labs",
    "big-tech":         "Big Tech AI",
    "infra-data":       "Infraestrutura & Data",
    "dev-tools":        "Dev Tools & Coding",
    "generative":       "Geração & Criatividade",
    "agents-search":    "AI Search & Agents",
    "research":         "Research",
    "media":            "Tech Media",
    "newsletter":       "Newsletters & Analistas",
    "china":            "China AI",
}
