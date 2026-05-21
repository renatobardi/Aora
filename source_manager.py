from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

from json_repair import repair_json

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


# ── CROSSCHECK ───────────────────────────────────────────────────────────────

_CROSSCHECK_SYSTEM_PROMPT = _SYSTEM_PROMPT + """

INSTRUÇÃO ESPECIAL PARA CRUZAMENTO:
- Esta fonte JÁ tem uma configuração existente (descrita acima).
- Sugira APENAS o tipo complementar que falta (RSS ou web).
- Se não houver RSS disponível, retorne null.
- Se não houver scraping viável, retorne null.
- Não repita o tipo que já existe.
- Seja conservador: só sugira se tiver alta confiança que funciona."""


def _parse_suggestions(text: str) -> list[dict]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0].rstrip()
    raw = raw.strip()
    if not raw or raw.lower() == "null":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(repair_json(raw))
        except Exception:
            return []
    if parsed is None:
        return []
    return parsed if isinstance(parsed, list) else [parsed]


def _derive_main_url(source: dict, source_type: str) -> str:
    if source_type == "rss":
        p = urlparse(source["feed_url"])
        return f"{p.scheme}://{p.netloc}"
    return source.get("listing_url") or source.get("sitemap_url", "")


def crosscheck_sources(provider: BaseProvider) -> None:
    """Audit all sources for RSS ↔ web scraping coverage, propose additions."""
    from processor import get_model  # noqa: PLC0415
    from progress_utils import console, make_progress, ok_line, warn_line  # noqa: PLC0415

    rss = _load(_SOURCES_PATH)
    web = _load(_SCRAPED_PATH)

    rss_names_lower = {s["name"].lower() for s in rss}
    web_names_lower = {s["name"].lower() for s in web}

    rss_only = [s for s in rss if s["name"].lower() not in web_names_lower]
    web_only = [s for s in web if s["name"].lower() not in rss_names_lower]

    total = len(rss_only) + len(web_only)
    console.print(f"  Só em RSS: {len(rss_only)}  |  Só em web: {len(web_only)}  |  Total a auditar: {total}\n")

    model = get_model(provider)
    proposals: list[dict] = []

    def _probe_and_ask(source: dict, source_type: str, want_type: str) -> list[dict]:
        main_url = _derive_main_url(source, source_type)
        if not main_url:
            return []
        probe = _probe_url(main_url)

        user_parts = [
            f"URL: {main_url}",
            f"Configuração {source_type.upper()} existente: {json.dumps(source, ensure_ascii=False)}",
        ]
        if probe["rss_links"]:
            user_parts.append(f"Feeds RSS encontrados: {', '.join(probe['rss_links'])}")
        if probe["has_sitemap"]:
            pu = urlparse(main_url)
            user_parts.append(f"Sitemap disponível em: {pu.scheme}://{pu.netloc}/sitemap.xml")
        if probe["robots_sitemaps"]:
            user_parts.append(f"Sitemaps via robots.txt: {', '.join(probe['robots_sitemaps'])}")
        if probe["html"]:
            user_parts.append(f"\nHTML da página (primeiros 8000 chars):\n{probe['html']}")

        result = provider.generate(
            model=model,
            system=_CROSSCHECK_SYSTEM_PROMPT,
            user="\n".join(user_parts),
            max_tokens=1024,
        )
        suggestions = _parse_suggestions(result.text)
        return [
            s for s in suggestions
            if s.get("type") == want_type
            and s.get("config")
            and not _validate_config(s["type"], s["config"])
        ]

    with make_progress() as progress:
        task = progress.add_task("Auditando fontes", total=total)

        for source in rss_only:
            try:
                found = _probe_and_ask(source, "rss", "web")
                if found:
                    for s in found:
                        proposals.append({"name": source["name"], "existing_type": "rss", "suggestion": s})
                    progress.console.print(ok_line(f"{source['name']} rss→web", len(found)))
                else:
                    progress.console.print(f"  [--]   {source['name']}: sem web disponível")
            except Exception as exc:
                progress.console.print(warn_line(source["name"], str(exc)[:80]))
            progress.advance(task)

        for source in web_only:
            try:
                found = _probe_and_ask(source, "web", "rss")
                if found:
                    for s in found:
                        proposals.append({"name": source["name"], "existing_type": "web", "suggestion": s})
                    progress.console.print(ok_line(f"{source['name']} web→rss", len(found)))
                else:
                    progress.console.print(f"  [--]   {source['name']}: sem RSS disponível")
            except Exception as exc:
                progress.console.print(warn_line(source["name"], str(exc)[:80]))
            progress.advance(task)

    if not proposals:
        console.print("\n  Nenhuma sugestão nova encontrada.")
        return

    console.print(f"\n{'='*60}")
    console.print(f"  CRUZAMENTO RSS ↔ WEB — {len(proposals)} sugestão(ões)")
    console.print(f"{'='*60}\n")

    for p in proposals:
        arrow = "RSS→WEB" if p["existing_type"] == "rss" else "WEB→RSS"
        console.print(f"  [{arrow}] {p['name']}")
        console.print(json.dumps(p["suggestion"]["config"], ensure_ascii=False, indent=4))
        console.print()

    confirm = input(f"Aplicar todas as {len(proposals)} sugestão(ões)? [s/N] ").strip().lower()
    if confirm not in ("s", "sim", "y", "yes"):
        console.print("Cancelado.")
        return

    rss_list = _load(_SOURCES_PATH)
    web_list = _load(_SCRAPED_PATH)
    added_rss = added_web = 0

    for p in proposals:
        stype = p["suggestion"]["type"]
        cfg = p["suggestion"]["config"]
        if stype == "rss":
            if cfg["name"].lower() not in {e["name"].lower() for e in rss_list}:
                rss_list.append(cfg)
                added_rss += 1
                console.print(f"  [OK] '{cfg['name']}' → sources.json")
            else:
                console.print(f"  [SKIP] '{cfg['name']}' já existe.")
        else:
            if cfg["name"].lower() not in {e["name"].lower() for e in web_list}:
                web_list.append(cfg)
                added_web += 1
                console.print(f"  [OK] '{cfg['name']}' → scraped_sources.json")
            else:
                console.print(f"  [SKIP] '{cfg['name']}' já existe.")

    if added_rss > 0:
        _save(_SOURCES_PATH, rss_list)
    if added_web > 0:
        _save(_SCRAPED_PATH, web_list)

    console.print(f"\n  ✓ {added_rss} RSS + {added_web} web adicionados.")


# ── HEALTH ───────────────────────────────────────────────────────────────────

_HEALTH_PATH = _ROOT / "source_health.json"

_STALE_DAYS   = 30  # RED: sem itens há mais de N dias
_SUSPECT_DAYS = 7   # YELLOW: sem itens há mais de N dias


def _load_health() -> dict:
    try:
        return json.loads(_HEALTH_PATH.read_text()) if _HEALTH_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_health(health: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=_HEALTH_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(health, ensure_ascii=False, indent=2))
        os.replace(tmp, _HEALTH_PATH)
    except Exception:
        os.unlink(tmp)
        raise


def update_source_health(
    checked_sources: list[dict],
    items: list[dict],
    error_names: set[str],
) -> None:
    """Silently update source_health.json after a pipeline run."""
    from datetime import date  # noqa: PLC0415

    health = _load_health()
    today = date.today().isoformat()

    # Map source_name → date of most recent item seen
    source_hit: set[str] = {item["source_name"] for item in items}

    for source in checked_sources:
        name = source["name"]
        entry = health.get(name, {"last_item_date": None, "consecutive_zeros": 0})
        entry["last_run"] = today

        if name in error_names:
            pass  # error already surfaced as WARN; don't penalize zeros
        elif name in source_hit:
            entry["last_item_date"] = today
            entry["consecutive_zeros"] = 0
        else:
            entry["consecutive_zeros"] = entry.get("consecutive_zeros", 0) + 1

        health[name] = entry

    _save_health(health)


def show_health() -> None:
    """Print a color-coded health report from source_health.json."""
    from datetime import date  # noqa: PLC0415
    from progress_utils import console  # noqa: PLC0415

    health = _load_health()
    if not health:
        console.print("  Nenhum dado de saúde encontrado. Execute 'aora all' primeiro.")
        return

    rss = _load(_SOURCES_PATH)
    web = _load(_SCRAPED_PATH)
    all_names = sorted({s["name"] for s in rss + web})
    today = date.today()

    stale: list[tuple]   = []
    suspect: list[tuple] = []
    healthy: list[str]   = []
    unseen: list[str]    = []  # in config but never ran

    for name in all_names:
        entry = health.get(name)
        if not entry:
            unseen.append(name)
            continue

        last_str = entry.get("last_item_date")
        zeros = entry.get("consecutive_zeros", 0)

        if last_str is None:
            stale.append((name, None, zeros))
        else:
            days = (today - date.fromisoformat(last_str)).days
            if days > _STALE_DAYS:
                stale.append((name, last_str, zeros))
            elif days > _SUSPECT_DAYS:
                suspect.append((name, last_str, days, zeros))
            else:
                healthy.append(name)

    console.print(f"\n  Fontes monitoradas: {len(all_names)}  |  Hoje: {today}\n")

    if stale:
        console.print(f"[red bold]  ESTAGNADAS ({len(stale)}) — sem itens há >{_STALE_DAYS} dias ou nunca[/red bold]")
        for name, last, zeros in stale:
            if last is None:
                detail = "nunca produziu itens"
            else:
                days = (today - date.fromisoformat(last)).days
                detail = f"último item: {last} ({days}d atrás)"
            console.print(f"[red]    {name:<32} {zeros:>3} zeros  |  {detail}[/red]")
        console.print()

    if suspect:
        console.print(f"[yellow bold]  SUSPEITAS ({len(suspect)}) — sem itens há {_SUSPECT_DAYS}-{_STALE_DAYS} dias[/yellow bold]")
        for name, last, days, zeros in suspect:
            console.print(f"[yellow]    {name:<32} {zeros:>3} zeros  |  último item: {last} ({days}d atrás)[/yellow]")
        console.print()

    console.print(f"[green]  ATIVAS ({len(healthy)}) — produziram itens nos últimos {_SUSPECT_DAYS} dias[/green]")
    for name in healthy:
        entry = health[name]
        console.print(f"[green]    {name:<32} último item: {entry['last_item_date']}[/green]")

    if unseen:
        console.print(f"\n  SEM DADOS ({len(unseen)}) — nunca rodaram (execute 'aora all' para popular)")
        for name in unseen:
            console.print(f"    {name}")

    if stale or suspect:
        console.print("\n  Dica: 'aora source crosscheck' verifica alternativas para as estagnadas.")
    console.print()


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
