"""
Generic validation/cleaning (Phase 3's idea, data-driven instead of
Pydantic-model-per-site): a required field that's missing/blank rejects
the row; a "number" field gets currency symbols etc. stripped and is
parsed as a float, rejected if that fails.
"""
from __future__ import annotations

import hashlib
import json
import re

from loguru import logger

from .models import SiteDefinition

_NUMERIC_STRIP = re.compile(r"[^0-9.\-]")


def _coerce(value: object, field_type: str) -> object:
    if field_type == "number":
        if value is None:
            return None
        cleaned = _NUMERIC_STRIP.sub("", str(value))
        if cleaned in ("", "-", "."):
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    if isinstance(value, str):
        value = value.strip()
    return value


def clean_and_validate_items(raw_items: list[dict], site: SiteDefinition) -> tuple[list[dict], int]:
    """Returns (clean_items, rejected_count). Every clean item keeps its
    "_key" (see parser.py) plus one entry per configured field."""
    clean: list[dict] = []
    rejected = 0

    for raw in raw_items:
        row: dict[str, object] = {}
        ok = True
        for field in site.fields:
            value = _coerce(raw.get(field.name), field.type)
            if field.required and (value is None or value == ""):
                ok = False
                break
            row[field.name] = value

        if not ok:
            rejected += 1
            logger.warning("rejected item (key={}) for site {}: a required field is missing", raw.get("_key"), site.name)
            continue

        row["_key"] = raw["_key"]
        clean.append(row)

    return clean, rejected


def item_row_hash(row: dict, site: SiteDefinition) -> str:
    """Fingerprint of a row's field values (Phase 3's change-detection
    idea) -- same field values -> same hash -> nothing new to store."""
    payload = {f.name: row.get(f.name) for f in site.fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
