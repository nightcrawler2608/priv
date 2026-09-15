"""
Config-driven sites, end to end: create a site via the API (URL + CSS
selectors, no Python), run a job, check status/results/export -- all
through FastAPI + Celery (eager mode), with the pipeline's network calls
faked via the same HTML fixture used since Phase 1. Fully offline.

This is the actual proof the feature works: a real page's structure,
described entirely as JSON/selectors, produces the same rows the
hardcoded books_toscrape scraper produces.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"
PERMISSIVE_ROBOTS_TXT = "User-agent: *\nAllow: /\n"

SITE_PAYLOAD = {
    "name": "books_toscrape_generic",
    "base_url": "https://books.toscrape.com/",
    "list_url_template": "https://books.toscrape.com/catalogue/page-{page}.html",
    "item_selector": "article.product_pod",
    "key_selector": "h3 a",
    "key_attr": "href",
    "fields": [
        {"name": "title", "selector": "h3 a", "attr": "title"},
        {"name": "price", "selector": "p.price_color", "type": "number"},
        {"name": "availability", "selector": ".availability"},
    ],
    "max_pages": 1,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_generic_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from api.celery_app import celery_app
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

    monkeypatch.setattr("api.generic_tasks.fetch_robots_txt", lambda *a, **k: PERMISSIVE_ROBOTS_TXT)
    monkeypatch.setattr(
        "api.generic_tasks.iter_list_pages",
        lambda site, **k: iter([(1, FIXTURE.read_text(encoding="utf-8"), "https://books.toscrape.com/catalogue/page-1.html")]),
    )
    monkeypatch.setattr("api.generic_tasks.save_raw_snapshot", lambda *a, **k: None)

    from api.main import app
    return TestClient(app)


def test_create_site_persists_config(client):
    resp = client.post("/sites", json=SITE_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "books_toscrape_generic"
    assert len(body["fields"]) == 3
    assert "id" in body


def test_create_site_rejects_template_without_page_placeholder(client):
    bad = {**SITE_PAYLOAD, "list_url_template": "https://x.example/products"}
    resp = client.post("/sites", json=bad)
    assert resp.status_code == 422


def test_create_site_rejects_duplicate_field_names(client):
    bad = {**SITE_PAYLOAD, "fields": [
        {"name": "title", "selector": "h3 a"},
        {"name": "title", "selector": ".other"},
    ]}
    resp = client.post("/sites", json=bad)
    assert resp.status_code == 422


def test_list_sites_returns_created_site(client):
    client.post("/sites", json=SITE_PAYLOAD)
    resp = client.get("/sites")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_full_pipeline_via_config_matches_hardcoded_scraper_output(client):
    site_id = client.post("/sites", json=SITE_PAYLOAD).json()["id"]

    job = client.post(f"/sites/{site_id}/jobs").json()
    job_id = job["id"]

    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "succeeded"
    assert status["rows_new"] == 6  # same 6 books as the hardcoded-scraper tests
    assert status["rows_rejected"] == 0

    results = client.get(f"/sites/{site_id}/jobs/{job_id}/results", params={"limit": 50}).json()
    assert results["total"] == 6
    titles = {item["data"]["title"] for item in results["items"]}
    assert "A Light in the Attic" in titles
    assert "Unsellable Vaporware" in titles

    a_light = next(i for i in results["items"] if i["data"]["title"] == "A Light in the Attic")
    assert a_light["data"]["price"] == 51.77
    assert a_light["data"]["availability"] == "In stock"


def test_export_returns_csv_with_configured_columns(client):
    site_id = client.post("/sites", json=SITE_PAYLOAD).json()["id"]
    job_id = client.post(f"/sites/{site_id}/jobs").json()["id"]

    export = client.get(f"/sites/{site_id}/jobs/{job_id}/export")
    assert export.status_code == 200
    header = export.text.splitlines()[0]
    assert set(header.split(",")) == {"title", "price", "availability"}


def test_second_identical_job_reports_all_unchanged(client):
    site_id = client.post("/sites", json=SITE_PAYLOAD).json()["id"]
    client.post(f"/sites/{site_id}/jobs")

    job2_id = client.post(f"/sites/{site_id}/jobs").json()["id"]
    status2 = client.get(f"/jobs/{job2_id}").json()

    assert status2["rows_new"] == 0
    assert status2["rows_unchanged"] == 6


def test_job_not_found_for_wrong_site_returns_404(client):
    site_a = client.post("/sites", json=SITE_PAYLOAD).json()["id"]
    site_b = client.post("/sites", json={**SITE_PAYLOAD, "name": "other"}).json()["id"]
    job_id = client.post(f"/sites/{site_a}/jobs").json()["id"]

    resp = client.get(f"/sites/{site_b}/jobs/{job_id}/results")
    assert resp.status_code == 404


def test_unknown_site_returns_404(client):
    assert client.get("/sites/does-not-exist").status_code == 404
    assert client.post("/sites/does-not-exist/jobs").status_code == 404
