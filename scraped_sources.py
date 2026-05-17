SCRAPED_SOURCES = [
    # ── SITEMAP ──────────────────────────────────────────────────────────────
    {
        "name": "Anthropic", "category": "foundation-model", "method": "sitemap",
        "sitemap_url": "https://www.anthropic.com/sitemap.xml",
        "url_pattern": r"anthropic\.com/(news|research)/[^/?#]+$",
    },
    {
        "name": "Mistral AI", "category": "foundation-model", "method": "sitemap",
        "sitemap_url": "https://mistral.ai/sitemap.xml",
        "url_pattern": r"mistral\.ai/(news|blog)/[^/?#]+$",
    },
    {
        "name": "Cohere", "category": "foundation-model", "method": "sitemap",
        "sitemap_url": "https://cohere.com/sitemap.xml",
        "url_pattern": r"cohere\.com/blog/[^/?#]+$",
    },
    {
        "name": "xAI", "category": "foundation-model", "method": "sitemap",
        "sitemap_url": "https://x.ai/sitemap.xml",
        "url_pattern": r"x\.ai/news/[^/?#]+$",  # sitemap uses /news/, not /blog/
        "parser": "lxml",  # sitemap has invalid XML entity
    },
    {
        "name": "Manus AI", "category": "agents-search", "method": "sitemap",
        "sitemap_url": "https://manus.im/sitemap.xml",
        "url_pattern": r"manus\.im/blog/[^/?#]+$",
        "fetch_dates": True,  # no lastmod in sitemap — use htmldate per article
    },
    {
        "name": "Cognition AI", "category": "agents-search", "method": "sitemap",
        "sitemap_url": "https://www.cognition.ai/sitemap.xml",
        "url_pattern": r"cognition\.ai/blog/[^/?#]+$",
        "fix_protocol": True,  # sitemap URLs lack https:// prefix
    },
    {
        "name": "Harvey AI", "category": "agents-search", "method": "sitemap",
        "sitemap_url": "https://www.harvey.ai/sitemap.xml",
        "url_pattern": r"harvey\.ai/blog/[^/?#]+$",
    },
    {
        "name": "Cerebras", "category": "infra-data", "method": "sitemap",
        "sitemap_url": "https://cerebras.ai/sitemap.xml",
        "url_pattern": r"cerebras\.ai/blog/[^/?#]+$",
    },
    {
        "name": "SambaNova", "category": "infra-data", "method": "sitemap",
        "sitemap_url": "https://sambanova.ai/sitemap.xml",
        "url_pattern": r"sambanova\.ai/blog/[^/?#]+$",
    },
    {
        "name": "Allen AI", "category": "research", "method": "sitemap",
        "sitemap_url": "https://allenai.org/sitemap.xml",
        "url_pattern": r"allenai\.org/blog/[^/?#]+$",
    },
    {
        "name": "Weights & Biases", "category": "dev-tools", "method": "sitemap",
        "sitemap_url": "https://wandb.ai/sitemap.xml",
        "url_pattern": r"wandb\.ai/fully-connected/[^/?#]+$",
    },
    {
        "name": "ElevenLabs", "category": "generative", "method": "sitemap",
        "sitemap_url": "https://elevenlabs.io/sitemap.xml",
        "url_pattern": r"elevenlabs\.io/blog/[^/?#]+$",
        "sub_pattern": "articles__en",  # blog posts are in articles__en sub-sitemap
    },
    {
        "name": "Cursor", "category": "dev-tools", "method": "sitemap",
        "sitemap_url": "https://www.cursor.com/sitemap.xml",
        "url_pattern": r"cursor\.com/blog/(?!topic)[^/?#]+$",
    },
    {
        "name": "Groq", "category": "infra-data", "method": "sitemap",
        "sitemap_url": "https://groq.com/sitemap.xml",
        "url_pattern": r"groq\.com/(blog|newsroom)/[^/?#]+$",
    },
    {
        "name": "Together AI", "category": "infra-data", "method": "sitemap",
        "sitemap_url": "https://www.together.ai/sitemap.xml",
        "url_pattern": r"together\.ai/blog/[^/?#]+$",
    },
    {
        "name": "Runway", "category": "generative", "method": "sitemap",
        "sitemap_url": "https://runwayml.com/sitemap.xml",
        "url_pattern": r"runwayml\.com/research/[a-z0-9]+(?:-[a-z0-9]+){2,}$",  # exclude single-word section pages
    },

    {
        "name": "AAIF", "category": "agents-search", "method": "sitemap",
        "sitemap_url": "https://aaif.io/sitemap.xml",
        "url_pattern": r"aaif\.io/blog/[a-z0-9][a-z0-9\-]+/?$",
        "sub_pattern": "post-sitemap",
    },
    {
        "name": "Novita AI", "category": "infra-data", "method": "sitemap",
        "sitemap_url": "https://blogs.novita.ai/sitemap.xml",
        "url_pattern": r"blogs\.novita\.ai/(?!tag/|category/|author/)[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?/?$",
        "sub_pattern": "post-sitemap",  # skip page-sitemap.xml
    },
    {
        "name": "Venice.ai", "category": "infra-data", "method": "sitemap",
        "sitemap_url": "https://venice.ai/sitemap.xml",
        "url_pattern": r"venice\.ai/blog/[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?$",
        # multi-lang hreflang (es, de) in sitemap; pattern restricts to English /blog/slug only
    },

    # ── HTML ESTÁTICO ─────────────────────────────────────────────────────────
    {
        "name": "Snowflake", "category": "infra-data", "method": "html",
        "listing_url": "https://www.snowflake.com/en/blog/",
        "link_pattern": r"/en/blog/[a-z0-9]+(?:-[a-z0-9]+){3,}/?$",  # require 3+ hyphens to skip category pages
        "base_url": "https://www.snowflake.com",
    },
    {
        "name": "Qwen (Alibaba)", "category": "foundation-model", "method": "html",
        "listing_url": "https://qwenlm.github.io/blog/",
        "link_pattern": r"qwenlm\.github\.io/blog/[^\"'?#\s]+$",
        "base_url": "https://qwenlm.github.io",
    },
    {
        "name": "MiniMax", "category": "foundation-model", "method": "html",
        "listing_url": "https://www.minimaxi.com/en/news",
        "link_pattern": r"/news/[^\"'?#\s]+$",  # URLs are /news/slug, not /en/news/slug
        "base_url": "https://www.minimaxi.com",
    },
    {
        "name": "Sakana AI", "category": "research", "method": "html",
        "listing_url": "https://sakana.ai/blog/",
        "link_pattern": r"sakana\.ai/[a-z][^/?#]+/?$",  # posts at root level, not /blog/slug
        "base_url": "https://sakana.ai",
    },
    {
        "name": "Moonshot AI", "category": "foundation-model", "method": "html",
        "listing_url": "https://www.kimi.com/blog/",
        "link_pattern": r"kimi\.com/blog/[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?$",
        "base_url": "https://www.kimi.com",
    },
    {
        "name": "Tessl", "category": "dev-tools", "method": "html",
        "listing_url": "https://tessl.io/blog/",
        "link_pattern": r"tessl\.io/blog/[a-z0-9][a-z0-9\-]+/?$",
        "base_url": "https://tessl.io",
    },
    {
        "name": "NanoGPT", "category": "infra-data", "method": "html",
        "listing_url": "https://nano-gpt.com/blog",
        "link_pattern": r"nano-gpt\.com/blog/[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?$",
        "base_url": "https://nano-gpt.com",
    },

    # ── PLAYWRIGHT (JS-heavy) ─────────────────────────────────────────────────
    {
        "name": "Modal Labs", "category": "infra-data", "method": "playwright",
        "listing_url": "https://modal.com/blog",
        "link_pattern": r"modal\.com/blog/[^/?#]+$",
    },
    {
        "name": "ByteDance", "category": "big-tech", "method": "playwright",
        "listing_url": "https://www.bytedance.com/en/techblog/",
        "link_pattern": r"bytedance\.com/en/techblog/[^/?#]+$",
    },
    {
        "name": "Scale AI", "category": "infra-data", "method": "playwright",
        "listing_url": "https://scale.com/blog",
        "link_pattern": r"scale\.com/blog/[^/?#]+$",
    },
    {
        "name": "Replit", "category": "dev-tools", "method": "playwright",
        "listing_url": "https://replit.com/blog",
        "link_pattern": r"replit\.com/blog/[^/?#]+$",
    },
    {
        "name": "DeepSeek", "category": "foundation-model", "method": "playwright",
        "listing_url": "https://www.deepseek.com/",
        "link_pattern": r"deepseek\.com/(news|blog|research)/[^/?#]+$",
    },
    # Zhipu AI (GLM) — NOT ENABLED: zhipuai.cn is a Vue SPA where news items are divs
    # with Vue click handlers, not <a> links — requires a custom scraping strategy.
    # {
    #     "name": "Zhipu AI", "category": "china", "method": "playwright",
    #     "listing_url": "https://www.zhipuai.cn/",
    #     "link_pattern": r"zhipuai\.cn/news-details/[^/?#]+$",
    #     "wait_until": "domcontentloaded",
    # },
]
