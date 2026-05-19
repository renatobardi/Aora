from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from provider import BaseProvider
from sources import CATEGORY_ORDER, CATEGORY_LABELS

_ROOT = Path(__file__).parent
_SOURCES_PATH = _ROOT / "sources.json"
_SCRAPED_PATH = _ROOT / "scraped_sources.json"

_REQUIRED_FIELDS: dict[str, set[str]] = {
    "rss":        {"name", "feed_url", "category"},
    "sitemap":    {"name", "category", "sitemap_url", "url_pattern"},
    "html":       {"name", "category", "listing_url", "link_pattern", "base_url"},
    "playwright": {"name", "category", "listing_url", "link_pattern"},
}


def _load(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        print(f"ERRO: arquivo de fontes não encontrado: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERRO: {path.name} está corrompido: {e}")
        sys.exit(1)


def _save(path: Path, data: list[dict]) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
        os.replace(tmp_name, path)
    except Exception:
        os.unlink(tmp_name)
        raise


# ── LIST ─────────────────────────────────────────────────────────────────────

def list_sources() -> None:
    rss = _load(_SOURCES_PATH)
    web = _load(_SCRAPED_PATH)

    rss_by_cat: dict[str, list] = {}
    for s in rss:
        rss_by_cat.setdefault(s["category"], []).append(s)

    web_by_cat: dict[str, list] = {}
    for s in web:
        web_by_cat.setdefault(s["category"], []).append(s)

    all_cats = CATEGORY_ORDER + [c for c in set(list(rss_by_cat) + list(web_by_cat)) if c not in CATEGORY_ORDER]

    print(f"\nFONTES RSS ({len(rss)})")
    print("-" * 60)
    for cat in all_cats:
        for s in rss_by_cat.get(cat, []):
            label = CATEGORY_LABELS.get(cat, cat)
            print(f"  {s['name']:<28} {label}")

    print(f"\nFONTES WEB ({len(web)})")
    print("-" * 60)
    for cat in all_cats:
        for s in web_by_cat.get(cat, []):
            label = CATEGORY_LABELS.get(cat, cat)
            print(f"  {s['name']:<28} {s['method']:<10} {label}")

    print(f"\nTotal: {len(rss)} RSS + {len(web)} web = {len(rss) + len(web)} fontes\n")


# ── ADD ───────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
Você é um assistente de configuração de fontes para o Aora, um agregador de notícias de IA.
Dado o conteúdo de uma página web, sugira a melhor configuração para monitorar essa fonte.

CATEGORIAS DISPONÍVEIS:
- foundation-model: Labs e modelos fundacionais (Anthropic, OpenAI, Mistral, Cohere, DeepSeek...)
- big-tech: Big Tech com divisão de IA (Google, Meta, Microsoft, AWS, NVIDIA, Apple, ByteDance...)
- infra-data: Infraestrutura de ML, cloud, dados (Hugging Face, Databricks, Groq, Modal, Cerebras...)
- dev-tools: Ferramentas para devs (GitHub, LangChain, Cursor, Replit, Weights & Biases...)
- generative: Geração de mídia, voz, imagem, vídeo (ElevenLabs, Runway...)
- agents-search: Agentes e busca com IA (Harvey, Cognition, Manus, AAIF...)
- research: Pesquisa acadêmica e institutos (ArXiv, Allen AI, Sakana AI...)
- media: Mídia tech e jornalismo (MIT Tech Review, TechCrunch, The Verge, Ars Technica...)
- newsletter: Newsletters e analistas individuais (Simon Willison, Import AI, Interconnects...)
- china: Ecossistema de IA da China (Pandaily, Qwen, MiniMax, Moonshot, ByteDance...)

TIPOS DE FONTE:
1. "rss" — feed RSS/Atom (preferir quando disponível)
   config obrigatório: name, feed_url, category

2. "web" com method "sitemap" — scraping via XML sitemap
   config obrigatório: name, category, method, sitemap_url, url_pattern (regex Python)
   config opcional: parser="lxml", fetch_dates=true, fix_protocol=true, sub_pattern

3. "web" com method "html" — scraping de página de listagem estática
   config obrigatório: name, category, method, listing_url, link_pattern (regex Python), base_url

4. "web" com method "playwright" — página com JavaScript heavy (SPA, lazy loading)
   config obrigatório: name, category, method, listing_url, link_pattern (regex Python)
   config opcional: wait_until (padrão: "networkidle"; use "domcontentloaded" para SPAs que nunca param)

REGRAS:
- Se a página tem feed RSS ativo, SEMPRE inclua uma entrada "rss".
- Se a página também tem sitemap ou estrutura scrapeável via HTML/Playwright, inclua TAMBÉM uma entrada "web".
- Retorne um array JSON quando sugerir múltiplas configs; um único objeto quando for apenas uma.
- url_pattern e link_pattern devem ser regex Python (sem /delimitadores/), escapar \\ para \\\\
- url_pattern deve filtrar apenas posts de blog/notícias, excluindo páginas de categoria, tags, etc.
- Sempre tente inferir um bom url_pattern baseado na estrutura de URLs vista no HTML.

Responda APENAS com JSON válido (sem markdown, sem explicação).
Formato para uma única config:
{"type": "rss", "config": {"name": "...", "feed_url": "...", "category": "..."}}
Formato para múltiplas configs (RSS + web):
[{"type": "rss", "config": {...}}, {"type": "web", "config": {...}}]"""


def _normalize_url(url: str) -> str:
    """Ensure URL has a scheme; default to https if missing."""
    if "://" not in url:
        url = "https://" + url
    return url


def _probe_url(url: str) -> dict:
    """Fetch the URL and look for RSS feeds and sitemap hints."""
    result = {"html": "", "rss_links": [], "has_sitemap": False, "robots_sitemaps": []}

    headers = {"User-Agent": "Mozilla/5.0 (compatible; Aora/1.0; +https://github.com/renatobardi/aora)"}

    try:
        r = httpx.get(url, follow_redirects=True, timeout=10, headers=headers)
        html = r.text[:8000]
        result["html"] = html

        # Look for RSS/Atom link tags via BeautifulSoup (avoids regex on HTML)
        soup = BeautifulSoup(html, "html.parser")
        for mime in ("application/rss+xml", "application/atom+xml"):
            for link in soup.find_all("link", type=mime):
                href = link.get("href")
                if href:
                    full = urljoin(url, href)
                    if full not in result["rss_links"]:
                        result["rss_links"].append(full)
    except Exception:
        print("Aviso: não foi possível acessar a URL — sugestão da IA pode ser imprecisa.")

    # Try sitemap.xml
    base = urlparse(url)
    sitemap_url = f"{base.scheme}://{base.netloc}/sitemap.xml"
    try:
        sr = httpx.head(sitemap_url, follow_redirects=True, timeout=5, headers=headers)
        if sr.status_code == 200:
            result["has_sitemap"] = True
    except Exception:
        pass

    # Try robots.txt for Sitemap: directives
    robots_url = f"{base.scheme}://{base.netloc}/robots.txt"
    try:
        rr = httpx.get(robots_url, follow_redirects=True, timeout=5, headers=headers)
        if rr.status_code == 200:
            sitemaps = re.findall(r"^Sitemap:[ \t]*([^\r\n]+)", rr.text, re.MULTILINE | re.IGNORECASE)
            result["robots_sitemaps"] = [s.strip() for s in sitemaps]
    except Exception:
        pass

    return result


def _validate_config(source_type: str, config: dict) -> list[str]:
    """Return list of missing required field names for the given type/method."""
    if source_type == "rss":
        required = _REQUIRED_FIELDS["rss"]
    else:
        method = config.get("method", "")
        required = _REQUIRED_FIELDS.get(method, set())
        if not required:
            return [f"method inválido ou ausente: '{method}'"]
    return sorted(required - config.keys())


def add_source(url: str, provider: BaseProvider) -> None:
    from processor import get_model  # noqa: PLC0415

    url = _normalize_url(url)
    print(f"\nAnalisando {url} ...")
    probe = _probe_url(url)

    user_parts = [f"URL: {url}"]
    if probe["rss_links"]:
        user_parts.append(f"Feeds RSS encontrados: {', '.join(probe['rss_links'])}")
    if probe["has_sitemap"]:
        base = urlparse(url)
        user_parts.append(f"Sitemap disponível em: {base.scheme}://{base.netloc}/sitemap.xml")
    if probe["robots_sitemaps"]:
        user_parts.append(f"Sitemaps via robots.txt: {', '.join(probe['robots_sitemaps'])}")
    if probe["html"]:
        user_parts.append(f"\nHTML da página (primeiros 8000 chars):\n{probe['html']}")

    user_message = "\n".join(user_parts)

    print("Consultando IA para sugerir configuração...")
    result = provider.generate(
        model=get_model(provider),
        system=_SYSTEM_PROMPT,
        user=user_message,
        max_tokens=2048,
    )

    raw = result.text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0].rstrip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print(f"ERRO: IA retornou resposta inválida:\n{raw}")
        sys.exit(1)

    # Normalize to list — AI may return a single object or an array
    suggestions = parsed if isinstance(parsed, list) else [parsed]

    valid: list[dict] = []
    for i, s in enumerate(suggestions, 1):
        stype = s.get("type")
        cfg = s.get("config", {})
        if stype not in ("rss", "web"):
            print(f"  [WARN] sugestão {i}: tipo inválido '{stype}', ignorando")
            continue
        missing = _validate_config(stype, cfg)
        if missing:
            print(f"  [WARN] sugestão {i}: campos faltando ({', '.join(missing)}), ignorando")
            continue
        valid.append(s)

    if not valid:
        print("ERRO: nenhuma sugestão válida retornada pela IA.")
        sys.exit(1)

    label_n = f"{len(valid)} config(s)" if len(valid) > 1 else "1 config"
    print(f"\nSugestão da IA ({label_n}):")
    display = valid if len(valid) > 1 else valid[0]
    print(json.dumps(display, ensure_ascii=False, indent=2))

    print()
    label_verb = "essas fontes" if len(valid) > 1 else "essa fonte"
    confirm = input(f"Adicionar {label_verb}? [s/N] ").strip().lower()
    if confirm not in ("s", "sim", "y", "yes"):
        print("Cancelado.")
        return

    rss_list: list[dict] | None = None
    web_list: list[dict] | None = None

    for s in valid:
        stype = s["type"]
        cfg = s["config"]
        if stype == "rss":
            if rss_list is None:
                rss_list = _load(_SOURCES_PATH)
            if cfg["name"].lower() in {e["name"].lower() for e in rss_list}:
                print(f"  [SKIP] '{cfg['name']}' já existe em sources.json.")
            else:
                rss_list.append(cfg)
                print(f"  [OK] '{cfg['name']}' → sources.json")
        else:
            if web_list is None:
                web_list = _load(_SCRAPED_PATH)
            if cfg["name"].lower() in {e["name"].lower() for e in web_list}:
                print(f"  [SKIP] '{cfg['name']}' já existe em scraped_sources.json.")
            else:
                web_list.append(cfg)
                print(f"  [OK] '{cfg['name']}' → scraped_sources.json")

    if rss_list is not None:
        _save(_SOURCES_PATH, rss_list)
    if web_list is not None:
        _save(_SCRAPED_PATH, web_list)


# ── REMOVE ────────────────────────────────────────────────────────────────────

def _lookup_source(name: str, rss: list, web: list) -> tuple[dict | None, bool]:
    """Return (source_dict, is_rss). Prints suggestions and returns (None, False) if not found."""
    name_lower = name.lower()
    rss_match = [s for s in rss if s["name"].lower() == name_lower]
    web_match = [s for s in web if s["name"].lower() == name_lower]
    if rss_match or web_match:
        return (rss_match + web_match)[0], bool(rss_match)

    rss_partial = [s for s in rss if name_lower in s["name"].lower()]
    web_partial = [s for s in web if name_lower in s["name"].lower()]
    all_partial = rss_partial + web_partial
    if all_partial:
        print(f"\nFonte '{name}' não encontrada. Fontes similares:")
        for s in all_partial:
            kind = "rss" if s in rss_partial else s.get("method", "web")
            print(f"  {s['name']}  [{kind}]")
    else:
        print(f"\nFonte '{name}' não encontrada.")
    return None, False


def remove_source(name: str) -> None:
    rss = _load(_SOURCES_PATH)
    web = _load(_SCRAPED_PATH)

    found, in_rss = _lookup_source(name, rss, web)
    if found is None:
        return

    print("\nFonte encontrada:")
    print(json.dumps(found, ensure_ascii=False, indent=2))

    print()
    c1 = input(f"Remover '{found['name']}'? [s/N] ").strip().lower()
    if c1 not in ("s", "sim", "y", "yes"):
        print("Cancelado.")
        return

    c2 = input("Digite o nome exato da fonte para confirmar: ").strip()
    if c2.lower() != found["name"].lower():
        print("Nome não confere. Cancelado.")
        return

    name_lower = name.lower()
    if in_rss:
        _save(_SOURCES_PATH, [s for s in rss if s["name"].lower() != name_lower])
    else:
        _save(_SCRAPED_PATH, [s for s in web if s["name"].lower() != name_lower])

    print(f"\nFonte '{found['name']}' removida com sucesso.")
