from __future__ import annotations

import html as _html
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def _get_date_from_page(html: str) -> datetime | None:
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


def scrape_html(
    source: dict,
    seen_ids: set[str],
    lookback_hours: int,
    max_items: int,
) -> tuple[list[dict], str | None]:
    try:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        link_re = re.compile(source["link_pattern"])
        base_url = source.get("base_url", "")

        # Fetch listing page
        with httpx.Client(timeout=15, follow_redirects=True) as c:
            r = c.get(source["listing_url"], headers=HEADERS)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        seen_hrefs: set[str] = set()
        candidate_urls: list[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            # Resolve relative URLs first, then apply pattern to the full URL
            full_url = urljoin(base_url or str(r.url), href)
            parsed = urlparse(full_url)
            clean = parsed._replace(query="", fragment="").geturl().rstrip("/")
            if not link_re.search(href) and not link_re.search(clean):
                continue
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
                with httpx.Client(timeout=15, follow_redirects=True) as c:
                    r2 = c.get(url, headers=HEADERS)

                pub_dt = _get_date_from_page(r2.text)
                if pub_dt and pub_dt < cutoff:
                    continue

                result = trafilatura.bare_extraction(
                    r2.text, include_comments=False, include_tables=False
                )
                if result:
                    title = _clean_title(result.title) if result.title else _extract_title(r2.text, url)
                    content = result.text or ""
                else:
                    title = _extract_title(r2.text, url)
                    content = trafilatura.extract(r2.text) or ""

                if not content:
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
                time.sleep(0.5)
            except Exception:
                continue

        return items, None

    except Exception as exc:
        return [], str(exc)
