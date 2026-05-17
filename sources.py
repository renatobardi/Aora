# Feed status verified 2026-05-16
# Chinese AI labs (Baidu, Alibaba/Qwen, ByteDance, DeepSeek, Zhipu, Moonshot, MiniMax)
# não possuem RSS público ativo em inglês — cobertos via Pandaily

SOURCES = [
    # Foundation Models & Labs
    {"name": "OpenAI",          "feed_url": "https://openai.com/news/rss.xml",                          "category": "foundation-model"},

    # Big Tech AI
    {"name": "Google AI",       "feed_url": "https://blog.google/technology/ai/rss/",                   "category": "big-tech"},
    {"name": "DeepMind",        "feed_url": "https://deepmind.google/blog/rss.xml",                     "category": "big-tech"},
    {"name": "Meta AI",         "feed_url": "https://engineering.fb.com/feed/",                         "category": "big-tech"},
    {"name": "Microsoft Res",   "feed_url": "https://www.microsoft.com/en-us/research/feed/",           "category": "big-tech"},
    {"name": "AWS ML",          "feed_url": "https://aws.amazon.com/blogs/machine-learning/feed/",      "category": "big-tech"},
    {"name": "NVIDIA",          "feed_url": "https://blogs.nvidia.com/feed/",                           "category": "big-tech"},
    {"name": "Apple ML",        "feed_url": "https://machinelearning.apple.com/rss.xml",                "category": "big-tech"},

    # Infraestrutura & Data
    {"name": "Databricks",      "feed_url": "https://www.databricks.com/feed",                          "category": "infra-data"},
    {"name": "Hugging Face",    "feed_url": "https://huggingface.co/blog/feed.xml",                     "category": "infra-data"},

    # Dev Tools & Coding
    {"name": "GitHub",          "feed_url": "https://github.blog/feed/",                                "category": "dev-tools"},
    {"name": "LangChain",       "feed_url": "https://blog.langchain.dev/rss.xml",                       "category": "dev-tools"},
    {"name": "Writer",          "feed_url": "https://writer.com/blog/feed/",                            "category": "dev-tools"},

    # AI Search & Agents
    {"name": "Character.AI",    "feed_url": "https://blog.character.ai/rss/",                           "category": "agents-search"},

    # Research
    {"name": "ArXiv CS.AI",     "feed_url": "https://export.arxiv.org/rss/cs.AI",                      "category": "research"},

    # Tech Media
    {"name": "MIT Tech Review", "feed_url": "https://www.technologyreview.com/feed/",                   "category": "media"},
    {"name": "TechCrunch AI",   "feed_url": "https://techcrunch.com/category/artificial-intelligence/feed/", "category": "media"},
    {"name": "The Verge AI",    "feed_url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "category": "media"},
    {"name": "Ars Technica",    "feed_url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "category": "media"},
    {"name": "IEEE Spectrum",   "feed_url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss", "category": "media"},
    {"name": "VentureBeat AI",  "feed_url": "https://feeds.feedburner.com/venturebeat/SZYF",            "category": "media"},

    # Newsletters & Analysts
    {"name": "Ahead of AI",     "feed_url": "https://magazine.sebastianraschka.com/feed",               "category": "newsletter"},
    {"name": "Interconnects",   "feed_url": "https://www.interconnects.ai/feed.xml",                    "category": "newsletter"},
    {"name": "Import AI",       "feed_url": "https://jack-clark.net/feed/",                             "category": "newsletter"},
    {"name": "Last Week in AI", "feed_url": "https://lastweekin.ai/feed",                               "category": "newsletter"},
    {"name": "Simon Willison",  "feed_url": "https://simonwillison.net/atom/everything/",               "category": "newsletter"},

    # China
    {"name": "Pandaily",        "feed_url": "https://pandaily.com/feed/",                               "category": "china"},
]

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
