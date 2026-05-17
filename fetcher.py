from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import trafilatura


def load_seen_ids(path: str) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen_ids(ids: set[str], path: str) -> None:
    Path(path).write_text(json.dumps(list(ids), indent=2))


def fetch_full_content(url: str) -> str:
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
        text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        return text or ""
    except Exception:
        return ""


def _parse_published(entry) -> datetime | None:
    pt = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if pt:
        try:
            return datetime(*pt[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def fetch_feed(
    source: dict,
    seen_ids: set[str],
    lookback_hours: int,
    max_items: int,
) -> tuple[list[dict], str | None]:
    try:
        parsed = feedparser.parse(source["feed_url"])

        # bozo flag means malformed feed; still try if entries exist
        if not parsed.entries:
            reason = getattr(parsed, "bozo_exception", "empty feed")
            return [], f"no entries ({reason})"

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        items: list[dict] = []

        for entry in parsed.entries:
            if len(items) >= max_items:
                break

            entry_id: str = getattr(entry, "id", None) or getattr(entry, "link", None) or ""
            if not entry_id or entry_id in seen_ids:
                continue

            pub_dt = _parse_published(entry)
            if pub_dt and pub_dt < cutoff:
                continue

            content: str = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            if len(content) < 200:
                link = getattr(entry, "link", "")
                if link:
                    fetched = fetch_full_content(link)
                    if fetched:
                        content = fetched

            items.append({
                "id": entry_id,
                "title": getattr(entry, "title", "Sem título"),
                "url": getattr(entry, "link", ""),
                "published": getattr(entry, "published", ""),
                "source_name": source["name"],
                "category": source["category"],
                "content": content[:4000],  # cap to avoid huge prompts
            })

        return items, None

    except Exception as exc:
        return [], str(exc)


def fetch_all(
    sources: list[dict],
    seen_ids: set[str],
    lookback_hours: int,
    max_items: int,
) -> tuple[list[dict], list[str], set[str]]:
    all_items: list[dict] = []
    error_sources: list[str] = []
    updated_ids = set(seen_ids)

    for source in sources:
        items, error = fetch_feed(source, updated_ids, lookback_hours, max_items)
        if error:
            error_sources.append(source["name"])
            print(f"  [WARN] {source['name']}: {error}")
        else:
            print(f"  [OK]   {source['name']}: {len(items)} novo(s)")
        for item in items:
            updated_ids.add(item["id"])
        all_items.extend(items)

    return all_items, error_sources, updated_ids
