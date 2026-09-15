"""
The generic extraction step: given a SiteDefinition and one page's HTML,
pull out each item's fields using nothing but the CSS selectors in the
config. Pure function -- no network -- same shape as books_toscrape's
parse_books(), just data-driven instead of hardcoded.
"""
from __future__ import annotations

import hashlib
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import SiteDefinition


def parse_items(html: str, page_url: str, site: SiteDefinition) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items: list[dict] = []

    for element in soup.select(site.item_selector):
        row: dict[str, object] = {}
        for field in site.fields:
            target = element.select_one(field.selector)
            if target is None:
                row[field.name] = None
                continue
            if field.attr == "text":
                row[field.name] = target.get_text(strip=True)
            else:
                value = target.get(field.attr)
                if value and field.attr in ("href", "src"):
                    value = urljoin(page_url, value)
                row[field.name] = value

        row["_key"] = _item_key(element, page_url, site, row)
        items.append(row)

    return items


def _item_key(element, page_url: str, site: SiteDefinition, row: dict) -> str:
    if site.key_selector:
        key_el = element.select_one(site.key_selector)
        if key_el is not None:
            raw_key = key_el.get(site.key_attr)
            if raw_key:
                return urljoin(page_url, raw_key)

    # No key_selector configured (or it didn't match this item): fall back
    # to a hash of the extracted values. Stable as long as the item's
    # visible content doesn't change; two genuinely identical items would
    # collide -- a real link-based key_selector avoids that and is
    # recommended whenever the site has one.
    payload = str(sorted(row.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
