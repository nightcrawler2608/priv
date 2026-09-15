"""
End-to-end test for POST /sites/detect ("paste a URL, get data"): fetches
a page, guesses the structure, and returns a real preview -- offline, with
the pipeline's network call faked via the same fixture used since Phase 1.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_detect.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("api.main.fetch_html", lambda url, **k: FIXTURE.read_text(encoding="utf-8"))

    from api.main import app
    return TestClient(app)


def test_detect_returns_a_confident_guess_with_a_real_preview(client):
    resp = client.post("/sites/detect", json={"url": "https://books.toscrape.com/catalogue/page-1.html"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["item_count"] == 6
    assert {f["name"] for f in body["fields"]} >= {"title", "price"}
    assert len(body["preview"]) > 0
    assert body["preview"][0]["title"]  # a real title string, not empty


def test_detect_result_can_be_saved_directly_as_a_site(client):
    """The whole point: the detect response should be postable to /sites
    with no editing, and it should work."""
    detected = client.post(
        "/sites/detect", json={"url": "https://books.toscrape.com/catalogue/page-1.html"}
    ).json()

    site_payload = {k: detected[k] for k in (
        "name", "base_url", "list_url_template", "item_selector",
        "key_selector", "key_attr", "fields", "max_pages",
    )}
    resp = client.post("/sites", json=site_payload)
    assert resp.status_code == 201


def test_detect_422s_on_a_page_with_no_repeated_structure(client, monkeypatch):
    monkeypatch.setattr("api.main.fetch_html", lambda url, **k: "<html><body><h1>Nothing here</h1></body></html>")
    resp = client.post("/sites/detect", json={"url": "https://example.com/"})
    assert resp.status_code == 422
