# Notas sobre as fontes

Contexto e decisões de configuração para `sources.json` e `scraped_sources.json`.

## Fontes RSS ausentes

Labs chineses de IA **não possuem RSS público ativo em inglês**:
Baidu, Alibaba/Qwen, ByteDance, DeepSeek, Zhipu, Moonshot, MiniMax.
Todos são cobertos indiretamente via **Pandaily** (categoria `china`).
Qwen, MiniMax, Moonshot e ByteDance têm entradas próprias em `scraped_sources.json`.

## Flags especiais em `scraped_sources.json`

| Fonte | Flag | Motivo |
|---|---|---|
| xAI | `"parser": "lxml"` | Sitemap contém entidade XML inválida |
| Manus AI | `"fetch_dates": true` | Sitemap não tem `lastmod` — usa `htmldate` por artigo |
| Cognition AI | `"fix_protocol": true` | URLs no sitemap não têm prefixo `https://` |
| ElevenLabs | `"sub_pattern": "articles__en"` | Posts ficam no sub-sitemap `articles__en`, não no raiz |
| AAIF | `"sub_pattern": "post-sitemap"` | Usar apenas o sub-sitemap de posts, ignorar `page-sitemap.xml` |
| Novita AI | `"sub_pattern": "post-sitemap"` | Idem — ignorar `page-sitemap.xml` |
| Cursor | `url_pattern` com `(?!topic)` | Exclui páginas de tópico `/blog/topic/...` |
| Runway | `url_pattern` com `{2,}` | Exclui páginas de seção (palavra única) como `/research/` |

## Fontes desabilitadas

- **Zhipu AI (GLM)**: `zhipuai.cn` é um SPA Vue onde os itens de notícia são `<div>` com
  handlers Vue, não `<a>`. Requer estratégia de scraping customizada além do Playwright padrão.
