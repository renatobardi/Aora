from __future__ import annotations

import html as _html
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import trafilatura

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False


def _get_date_from_html(html: str) -> datetime | None:
    try:
        import htmldate
        found = htmldate.find_date(html, extensive_search=True)
        if found:
            return datetime.fromisoformat(found).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _clean_title(title: str) -> str:
    title = _html.unescape(title).strip()
    parts = re.split(r"\s*[|·–—\\]\s*", title)
    if len(parts) > 1:
        title = max(parts, key=len).strip()
    return title


def _extract_title(html_text: str, url: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)", html_text, re.IGNORECASE)
    if m:
        title = _clean_title(m.group(1))
        if title:
            return title
    return url.rstrip("/").split("/")[-1].replace("-", " ").title()


def scrape_playwright(
    source: dict,
    seen_ids: set[str],
    lookback_hours: int,
    max_items: int,
) -> tuple[list[dict], str | None]:
    if not PLAYWRIGHT_OK:
        return [], "playwright não instalado — rode: pip install playwright && playwright install chromium"

    try:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        link_re = re.compile(source["link_pattern"])

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(extra_http_headers={"User-Agent": HEADERS["User-Agent"]})

                # Fetch listing page
                page.goto(source["listing_url"], wait_until="networkidle", timeout=30000)
                time.sleep(2)

                # Extract all links
                hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                seen_hrefs: set[str] = set()
                candidate_urls: list[str] = []
                for href in hrefs:
                    if not link_re.search(href):
                        continue
                    parsed = urlparse(href)
                    clean = parsed._replace(query="", fragment="").geturl().rstrip("/")
                    if clean not in seen_hrefs:
                        seen_hrefs.add(clean)
                        candidate_urls.append(clean)

                items: list[dict] = []
                for url in candidate_urls:
                    if len(items) >= max_items:
                        break
                    if url in seen_ids:
                        continue

                    try:
                        page.goto(url, wait_until="networkidle", timeout=20000)
                        time.sleep(1)
                        html = page.content()

                        pub_dt = _get_date_from_html(html)
                        if pub_dt and pub_dt < cutoff:
                            continue

                        result = trafilatura.bare_extraction(
                            html, include_comments=False, include_tables=False
                        )
                        if result:
                            title = _clean_title(result.title) if result.title else _extract_title(html, url)
                            content = result.text or ""
                        else:
                            title = _extract_title(html, url)
                            content = trafilatura.extract(html) or ""

                        if not content or len(content) < 100:
                            continue

                        items.append({
                            "id": url,
                            "title": title,
                            "url": url,
                            "published": pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000") if pub_dt else "",
                            "source_name": source["name"],
                            "category": source["category"],
                            "content": content[:4000],
                        })
                    except Exception:
                        continue
            finally:
                browser.close()

        return items, None

    except Exception as exc:
        return [], str(exc)
