"""
"Paste a URL, get data" -- guesses a SiteDefinition's item_selector and
fields straight from a page's HTML, no CSS knowledge required from the
user. Pure heuristics, no AI/LLM call, no API key needed:

1. Find the "item" pattern: group every element by (tag, sorted class
   list), and pick the group with the most repeated siblings under a
   single parent -- the classic signature of a product grid, article
   list, search results page, etc.
2. Within one example item, guess likely fields: the first heading is
   probably the title; text containing a currency symbol is probably a
   price; the first link is probably the item's own page (used as the
   key); the first image is probably a thumbnail.

This is a *guess* meant for a human to review before saving, not a
blind auto-save -- heuristics get it wrong on unusual layouts. Detected
selectors are written relative to the item root, so they work in
scrapers.generic.parser.parse_items() exactly like a hand-written config.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import Tag

_CURRENCY_RE = re.compile(r"[£$€¥][\s]?\d|(\d[\s]?[£$€¥])")
_MIN_REPEATS = 3  # fewer than this isn't a confident "this is a list" signal


@dataclass
class DetectedField:
    name: str
    selector: str  # relative to the item root
    attr: str
    type: str


@dataclass
class DetectionResult:
    item_selector: str
    key_selector: str | None
    key_attr: str
    fields: list[DetectedField]
    item_count: int  # how many matching items were found on the page -- a confidence signal


def _element_signature(tag: Tag) -> tuple[str, tuple[str, ...]]:
    classes = tuple(sorted(tag.get("class", [])))
    return (tag.name, classes)


def _find_item_candidates(soup: BeautifulSoup) -> list[Tag]:
    """Group elements by (tag, classes) sharing the same parent; return
    the members of whichever group repeats the most. Blocklist tags that
    are structural, not "an item" (html/body/head, script/style)."""
    skip_tags = {"html", "body", "head", "script", "style", "meta", "link", "br", "hr"}
    groups: dict[tuple[Tag, tuple[str, tuple[str, ...]]], list[Tag]] = {}

    for tag in soup.find_all(True):
        if tag.name in skip_tags or not tag.get("class"):
            continue
        parent = tag.parent
        if parent is None:
            continue
        key = (parent, _element_signature(tag))
        groups.setdefault(key, []).append(tag)

    best_group: list[Tag] = []
    for members in groups.values():
        if len(members) >= _MIN_REPEATS and len(members) > len(best_group):
            best_group = members

    return best_group


def _css_selector_for(tag: Tag) -> str:
    """A short, robust selector for this tag: its own tag+class combo."""
    classes = tag.get("class", [])
    if classes:
        return f"{tag.name}." + ".".join(classes)
    return tag.name


def _guess_key_link(item: Tag) -> Tag | None:
    return item.find("a", href=True)


def _guess_title(item: Tag) -> Tag | None:
    heading = item.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading is not None:
        return heading
    link = item.find("a")
    if link is not None and link.get_text(strip=True):
        return link
    return None


def _guess_price(item: Tag) -> Tag | None:
    for el in item.find_all(string=_CURRENCY_RE):
        parent = el.parent
        if isinstance(parent, Tag):
            return parent
    return None


def _guess_image(item: Tag) -> Tag | None:
    return item.find("img", src=True)


def detect_site_structure(html: str) -> DetectionResult | None:
    """Best-effort guess at item_selector + fields for one page's HTML.
    Returns None if no confident repeated-item pattern was found (e.g. a
    page that isn't a list of anything -- a single article, a login
    page)."""
    soup = BeautifulSoup(html, "lxml")
    candidates = _find_item_candidates(soup)
    if not candidates:
        return None

    item_selector = _css_selector_for(candidates[0])
    example = candidates[0]

    fields: list[DetectedField] = []
    seen_names: set[str] = set()

    def add_field(name: str, el: Tag | None, attr: str, field_type: str) -> None:
        if el is None or el is example or name in seen_names:
            return  # el is example: the guessed field IS the item root -- too rare/ambiguous to express as a selector, skip it
        selector = _css_selector_for(el)
        fields.append(DetectedField(name=name, selector=selector, attr=attr, type=field_type))
        seen_names.add(name)

    title_el = _guess_title(example)
    add_field("title", title_el, "text", "text")

    price_el = _guess_price(example)
    add_field("price", price_el, "text", "number")

    key_link = _guess_key_link(example)
    if key_link is not None:
        add_field("link", key_link, "href", "text")

    image_el = _guess_image(example)
    add_field("image", image_el, "src", "text")

    if not fields:
        return None

    key_selector = _css_selector_for(key_link) if key_link is not None else None

    return DetectionResult(
        item_selector=item_selector,
        key_selector=key_selector,
        key_attr="href",
        fields=fields,
        item_count=len(candidates),
    )
