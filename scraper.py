from __future__ import annotations

from html_scraper import scrape_html
from playwright_scraper import scrape_playwright
from sitemap_scraper import scrape_sitemap


def scrape_all(
    sources: list[dict],
    seen_ids: set[str],
    lookback_hours: int,
    max_items: int,
) -> tuple[list[dict], list[str], set[str]]:
    all_items: list[dict] = []
    error_sources: list[str] = []
    updated_ids = set(seen_ids)

    for source in sources:
        method = source["method"]
        if method == "sitemap":
            items, error = scrape_sitemap(source, updated_ids, lookback_hours, max_items)
        elif method == "html":
            items, error = scrape_html(source, updated_ids, lookback_hours, max_items)
        elif method == "playwright":
            items, error = scrape_playwright(source, updated_ids, lookback_hours, max_items)
        else:
            items, error = [], f"método desconhecido: {method}"

        if error:
            error_sources.append(source["name"])
            print(f"  [WARN] {source['name']}: {error}")
        else:
            print(f"  [OK]   {source['name']}: {len(items)} novo(s)")

        for item in items:
            updated_ids.add(item["id"])
        all_items.extend(items)

    return all_items, error_sources, updated_ids
