from __future__ import annotations

from datetime import date

from sources import CATEGORY_LABELS, CATEGORY_ORDER


def format_tags(tags: list[str]) -> str:
    if not tags:
        return ""
    return " ".join(f"#{t}" for t in tags)


def render_item(item: dict) -> str:
    published = item.get("published", "")
    tags_str = format_tags(item.get("tags", []))
    category = item.get("category", "")

    lines = [
        f"## {item['source_name']} — {item['title']}",
        "",
        f"**Data:** {published}",
        f"**Link:** {item['url']}",
        f"**Categoria:** #{category}",
        "",
        f"**TL;DR:** {item.get('tldr', '')}",
        "",
        f"**Por que importa:** {item.get('por_que_importa', '')}",
        "",
        f"**Tags:** {tags_str}" if tags_str else "",
        "",
        "---",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def render_daily(items: list[dict], errors: list[str], run_date: date) -> str:
    date_str = run_date.isoformat()
    total = len(items)
    errors_yaml = (
        "[]"
        if not errors
        else "[" + ", ".join(f'"{e}"' for e in errors) + "]"
    )

    sections: list[str] = [
        "---",
        f"date: {date_str}",
        "type: ai-clipping",
        f"total_items: {total}",
        f"sources_com_erro: {errors_yaml}",
        "---",
        "",
        f"# AI Clipping — {date_str}",
        "",
        f"> **{total} updates** de {len(set(i['source_name'] for i in items))} fontes monitoradas.",
        "",
        "---",
        "",
    ]

    by_category: dict[str, list[dict]] = {}
    for item in items:
        by_category.setdefault(item["category"], []).append(item)

    for cat in CATEGORY_ORDER:
        cat_items = by_category.get(cat, [])
        if not cat_items:
            continue
        label = CATEGORY_LABELS.get(cat, cat)
        sections.append(f"# {label}")
        sections.append("")
        for item in cat_items:
            sections.append(render_item(item))

    return "\n".join(sections)
