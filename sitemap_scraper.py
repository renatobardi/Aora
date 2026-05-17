from __future__ import annotations

import html as _html
import re
import time
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import httpx
import trafilatura

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        s = s.strip()
        if len(s) == 10:
            s += "T00:00:00+00:00"
        s = s.replace("Z", "+00:00")
        if s.endswith("+0000"):
            s = s[:-5] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _parse_xml(text: str, content: bytes, use_lxml: bool) -> ET.Element:
    if use_lxml:
        from lxml import etree
        return etree.fromstring(content)
    return ET.fromstring(text)


def _findall(root, tag: str, use_lxml: bool) -> list:
    if use_lxml:
        return root.findall(f"{{{NS}}}{tag}")
    return root.findall(f"{{{NS}}}{tag}")


def _findtext(el, tag: str) -> str | None:
    child = el.find(f"{{{NS}}}{tag}")
    return child.text if child is not None else None


def _fetch_sitemap_entries(url: str, use_lxml: bool = False) -> tuple[list, bool]:
    """Returns (entries, is_index). entries = list of (loc, lastmod_or_None)."""
    with httpx.Client(timeout=15, follow_redirects=True) as c:
        r = c.get(url, headers=HEADERS)
    r.raise_for_status()
    root = _parse_xml(r.text, r.content, use_lxml)
    indexes = _findall(root, "sitemap", use_lxml)
    if indexes:
        return [((_findtext(i, "loc") or ""), None) for i in indexes if _findtext(i, "loc")], True
    urls = _findall(root, "url", use_lxml)
    return [((_findtext(u, "loc") or ""), _findtext(u, "lastmod")) for u in urls if _findtext(u, "loc")], False


def _get_date_from_page(url: str) -> datetime | None:
    try:
        import htmldate
        with httpx.Client(timeout=12, follow_redirects=True) as c:
            r = c.get(url, headers=HEADERS)
        found = htmldate.find_date(r.text, extensive_search=True)
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


def scrape_sitemap(
    source: dict,
    seen_ids: set[str],
    lookback_hours: int,
    max_items: int,
) -> tuple[list[dict], str | None]:
    try:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        use_lxml = source.get("parser") == "lxml"
        fetch_dates = source.get("fetch_dates", False)
        sub_pattern = source.get("sub_pattern", "")
        fix_protocol = source.get("fix_protocol", False)
        url_re = re.compile(source["url_pattern"])

        # Fetch top-level sitemap
        entries, is_index = _fetch_sitemap_entries(source["sitemap_url"], use_lxml)

        # Some sitemaps omit https:// — prepend it when missing
        if fix_protocol:
            entries = [
                (url if url.startswith("http") else f"https://{url}", lm)
                for url, lm in entries
            ]

        # If sitemap index, recurse into matching sub-sitemaps
        if is_index:
            all_entries: list[tuple[str, str | None]] = []
            for sub_url, _ in entries:
                if sub_pattern and sub_pattern not in sub_url:
                    continue
                try:
                    sub_entries, _ = _fetch_sitemap_entries(sub_url, use_lxml)
                    all_entries.extend(sub_entries)
                    time.sleep(0.3)
                except Exception:
                    continue
            entries = all_entries

        items: list[dict] = []
        for url, lastmod in entries:
            if len(items) >= max_items:
                break
            if not url_re.search(url):
                continue
            if url in seen_ids:
                continue

            # Date filtering
            if fetch_dates or lastmod is None:
                pub_dt = _get_date_from_page(url)
            else:
                pub_dt = _parse_date(lastmod)

            if pub_dt and pub_dt < cutoff:
                continue

            # Fetch article content
            try:
                with httpx.Client(timeout=15, follow_redirects=True) as c:
                    r = c.get(url, headers=HEADERS)
                result = trafilatura.bare_extraction(
                    r.text, include_comments=False, include_tables=False
                )
                if result:
                    title = _clean_title(result.title) if result.title else _extract_title(r.text, url)
                    content = result.text or ""
                else:
                    title = _extract_title(r.text, url)
                    content = trafilatura.extract(r.text) or ""

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
                time.sleep(0.5)
            except Exception:
                continue

        return items, None

    except Exception as exc:
        return [], str(exc)
