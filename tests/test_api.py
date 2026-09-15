"""
Phase 4 tests: FastAPI TestClient + Celery in "always eager" mode (tasks run
synchronously in-process, no Redis broker or separate worker needed) and the
whole scrape pipeline's network calls faked out with the same HTML fixture
used since Phase 1. Fully offline.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"
PERMISSIVE_ROBOTS_TXT = "User-agent: *\nAllow: /\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from api.celery_app import celery_app
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

    def fake_fetch_robots_txt(*args, **kwargs):
        return PERMISSIVE_ROBOTS_TXT

    def fake_iter_catalogue_pages(*args, **kwargs):
        yield 1, FIXTURE.read_text(encoding="utf-8")

    monkeypatch.setattr("api.tasks.fetch_robots_txt", fake_fetch_robots_txt)
    monkeypatch.setattr("api.tasks.iter_catalogue_pages", fake_iter_catalogue_pages)
    monkeypatch.setattr("api.tasks.save_raw_snapshot", lambda *a, **k: None)

    from api.main import app
    return TestClient(app)


def test_create_job_returns_202_with_queued_status(client):
    resp = client.post("/jobs", json={"max_pages": 1})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert "id" in body


def test_job_reaches_succeeded_with_correct_counts(client):
    resp = client.post("/jobs", json={"max_pages": 1})
    job_id = resp.json()["id"]

    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "succeeded"
    assert status["rows_new"] == 6  # 6 books in the fixture
    assert status["rows_changed"] == 0
    assert status["rows_rejected"] == 0
    assert status["finished_at"] is not None


def test_results_endpoint_returns_this_jobs_rows_paginated(client):
    job_id = client.post("/jobs", json={"max_pages": 1}).json()["id"]

    page = client.get(f"/jobs/{job_id}/results", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 6
    assert page["limit"] == 2
    assert len(page["items"]) == 2

    next_page = client.get(f"/jobs/{job_id}/results", params={"limit": 2, "offset": 2}).json()
    assert len(next_page["items"]) == 2
    assert {i["url"] for i in page["items"]}.isdisjoint({i["url"] for i in next_page["items"]})


def test_export_endpoint_returns_csv_with_expected_columns(client):
    job_id = client.post("/jobs", json={"max_pages": 1}).json()["id"]

    export = client.get(f"/jobs/{job_id}/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    header = export.text.splitlines()[0]
    assert header == "url,title,price,rating,availability"
    assert len(export.text.strip().splitlines()) == 7  # header + 6 rows


def test_second_identical_job_reports_all_rows_unchanged(client):
    """Running the scrape twice must not fabricate new 'changed' rows --
    this exercises the Phase 3 idempotency guarantee through the API."""
    job1 = client.post("/jobs", json={"max_pages": 1}).json()["id"]
    client.get(f"/jobs/{job1}")

    job2_id = client.post("/jobs", json={"max_pages": 1}).json()["id"]
    status2 = client.get(f"/jobs/{job2_id}").json()

    assert status2["status"] == "succeeded"
    assert status2["rows_new"] == 0
    assert status2["rows_changed"] == 0
    assert status2["rows_unchanged"] == 6


def test_unknown_job_id_returns_404(client):
    for path in ["/jobs/does-not-exist", "/jobs/does-not-exist/results", "/jobs/does-not-exist/export"]:
        assert client.get(path).status_code == 404


def test_job_marked_failed_when_pipeline_raises_never_stuck_running(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr("api.tasks.iter_catalogue_pages", boom)

    job_id = client.post("/jobs", json={"max_pages": 1}).json()["id"]
    status = client.get(f"/jobs/{job_id}").json()

    assert status["status"] == "failed"
    assert "simulated worker crash" in status["error_message"]
