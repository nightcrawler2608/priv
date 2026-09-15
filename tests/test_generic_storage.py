"""Config-driven sites: generic storage idempotency/change-detection tests.
Same pattern as tests/test_storage.py (Phase 3), generalized to arbitrary
fields via row dicts, against a real (local, file-based) SQLite database."""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from scrapers.books_toscrape.storage.db import get_engine, init_db
from scrapers.generic.models import FieldConfig, SiteDefinition
from scrapers.generic.storage import ItemHistoryORM, ItemORM, upsert_items

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc)

SITE = SiteDefinition(
    id="s1", name="test", base_url="https://x/", list_url_template="https://x/{page}",
    item_selector="div", fields=[FieldConfig(name="title", selector="h1"), FieldConfig(name="price", selector=".p", type="number")],
)


def _engine(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    return engine


def test_new_item_creates_current_row_and_history_row(tmp_path):
    engine = _engine(tmp_path)
    row = {"_key": "k1", "title": "Book", "price": 10.0}

    with Session(engine) as session:
        stats = upsert_items(session, SITE, [row], scraped_at=T0)

    assert stats == {"new": 1, "changed": 0, "unchanged": 0}
    with Session(engine) as session:
        assert session.query(ItemORM).count() == 1
        assert session.query(ItemHistoryORM).count() == 1


def test_running_the_same_scrape_twice_is_idempotent(tmp_path):
    engine = _engine(tmp_path)
    row = {"_key": "k1", "title": "Book", "price": 10.0}

    with Session(engine) as session:
        upsert_items(session, SITE, [row], scraped_at=T0)
    with Session(engine) as session:
        stats2 = upsert_items(session, SITE, [row], scraped_at=T1)

    assert stats2 == {"new": 0, "changed": 0, "unchanged": 1}
    with Session(engine) as session:
        assert session.query(ItemHistoryORM).count() == 1  # still just one


def test_changed_field_updates_current_and_appends_history(tmp_path):
    engine = _engine(tmp_path)
    v1 = {"_key": "k1", "title": "Book", "price": 10.0}
    v2 = {"_key": "k1", "title": "Book", "price": 12.0}

    with Session(engine) as session:
        upsert_items(session, SITE, [v1], scraped_at=T0)
    with Session(engine) as session:
        stats2 = upsert_items(session, SITE, [v2], scraped_at=T1)

    assert stats2 == {"new": 0, "changed": 1, "unchanged": 0}
    with Session(engine) as session:
        current = session.get(ItemORM, "s1:k1")
        assert json.loads(current.data_json)["price"] == 12.0
        assert session.query(ItemHistoryORM).count() == 2


def test_different_sites_keep_separate_items_even_with_same_key(tmp_path):
    """Two sites both extracting an item with _key='k1' must not collide --
    the storage key is namespaced by site_id."""
    engine = _engine(tmp_path)
    other_site = SITE.model_copy(update={"id": "s2"})
    row = {"_key": "k1", "title": "Book", "price": 10.0}

    with Session(engine) as session:
        upsert_items(session, SITE, [row], scraped_at=T0)
        upsert_items(session, other_site, [row], scraped_at=T0)
        assert session.query(ItemORM).count() == 2
