"""
Phase 3: raw HTML snapshots, content-addressed by hash.

Storing the raw page alongside the parsed rows means you can re-parse
history later (e.g. after fixing a selector bug) without re-scraping the
live site. Naming each file by a hash of its content gives change
detection for free: if a page's HTML is byte-identical to what we already
saved for that page, the file already exists and we skip the write --
useful on an hourly job where most pages don't change hour to hour.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def save_raw_snapshot(html: str, page_num: int, snapshot_dir: Path) -> Path | None:
    """Write `html` to snapshot_dir, named by page number + content hash.
    Returns the path written, or None if this exact content was already
    saved for this page (nothing new to store)."""
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshot_dir / f"page-{page_num}_{content_hash}.html"
    if out_path.exists():
        return None
    out_path.write_text(html, encoding="utf-8")
    return out_path
