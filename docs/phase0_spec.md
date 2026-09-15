# Phase 0 — Project Spec

## Target site
- Site: `https://books.toscrape.com/` (catalogue pages, e.g. `catalogue/page-1.html` .. `page-50.html`)
- This is a public sandbox site built by Zyte specifically for scraping practice/tutorials. It has no login, no rate-limit enforcement, and its `robots.txt` sets no disallow rules for the catalogue — but we still fetch politely (delay + real user-agent) as if it were a real store, since the code should behave identically against a real site later.

## Fields to collect (one row per book)
| field        | type   | example                    | source in HTML                          |
|--------------|--------|-----------------------------|------------------------------------------|
| title        | str    | "A Light in the Attic"      | `article.product_pod h3 a[title]`        |
| price        | float  | 51.77                        | `p.price_color` (strip `£`, cast float)  |
| rating       | int    | 3                             | `p.star-rating` class word → number      |
| availability | str    | "In stock" / "Out of stock"  | `p.instock.availability` text, trimmed   |

## Refresh cadence
Hourly — this project is framed as near-real-time price/availability monitoring.
Because of the hourly cadence we will, from Phase 2 onward, be strict about
rate limiting and about only re-storing rows that actually changed (hash-based
change detection), so an hourly job against ~1000 books stays cheap and polite.

## Final use
Monitoring dashboard: track price and stock-status changes for a catalogue of
books over time.

## Legal/robots check
`books.toscrape.com/robots.txt` allows crawling of the catalogue (it's a
scraping sandbox site, built for this exact purpose). No personal data is
collected — books are public product listings, not people. When this pipeline
is later pointed at a real store, this same check (fetch and read
`robots.txt`, confirm the target paths aren't disallowed, prefer an official
API if one exists) must be repeated before scraping it.

## Status
Phase 0: done (this file).
Phase 1: single-site, single-script scraper → CSV, tested against a saved
HTML fixture (see `tests/fixtures/books_page1.html`).
Phase 2: robust fetching — retries with exponential backoff on transient
errors (timeout/connection/5xx/429), fail-fast on permanent errors (404/403),
runtime `robots.txt` check, rate-limited pagination across catalogue pages,
optional Playwright path documented for JS-rendered sites. All tested offline
by mocking HTTP responses (`tests/test_fetch_robustness.py`), no live network
calls in the test suite.
Phase 3: validate/clean/store — Pydantic `BookRecord` rejects malformed rows
(negative price, blank title, out-of-range rating) and logs rejections
(`models.py`); a `row_hash()` fingerprint drives idempotent upserts into
SQLAlchemy tables `books` (current state) and `book_history` (append-only,
new row only when the hash changes) — defaults to a local SQLite file,
swaps to Postgres via `DATABASE_URL` with no code change (`storage/db.py`);
raw HTML is snapshotted per page, content-addressed by hash so an unchanged
page is never re-stored (`storage/raw_snapshots.py`). All offline: SQLite
temp files and tmp_path fixtures, no live network or live DB server needed
(`tests/test_models.py`, `tests/test_storage.py`, `tests/test_raw_snapshots.py`).
Phase 4: backend API + job queue — `api/` package: FastAPI exposes
POST /jobs (202, hands off to Celery, returns immediately), GET /jobs/{id}
(status + row counts), GET /jobs/{id}/results (paginated, job-scoped rows),
GET /jobs/{id}/export (CSV download); `api/tasks.py`'s Celery task wraps the
full Phase 1-3 pipeline and always resolves the job to `succeeded` or
`failed` (any exception is caught, job never stuck in `running`). Jobs table
added to `storage/db.py`; `book_history` rows now carry the `job_id` that
produced them. Runs behind a real Redis broker in production
(`REDIS_URL`); tests run Celery in `task_always_eager` mode (synchronous,
no broker) with the pipeline's network calls faked via the same HTML
fixture used since Phase 1 (`tests/test_api.py`) — fully offline, 32/32
tests passing.
Phase 5: frontend dashboard — `frontend/` (Vite + React + TypeScript +
Tailwind v4 + TanStack Query + Recharts). Job creation form, jobs list that
polls each job's status every 2s while queued/running and stops once
resolved, paginated results table with an in-stock/out-of-stock filter, CSV
download link, and a bar chart of new/changed/unchanged/rejected row counts.
7 Vitest component tests, all offline (API calls mocked). Manually verified
end to end in a real browser (Playwright screenshot) against a stub server
matching the real API's exact response shapes — this sandbox blocks live
network to books.toscrape.com, so a true success-path run against the real
site couldn't be demoed here; the real backend's logic is already covered
by the 32 Phase 1-4 tests, which do run against real (fixture-driven)
parsing/storage code. Run locally: `npm run dev` in `frontend/` with
`VITE_API_URL` pointing at a running `uvicorn api.main:app`.
Phase 6: automation — `config/books_toscrape.yaml` holds the site's
schedule, page limit, and quality thresholds (`scrapers/books_toscrape/config.py`
loads/validates it as config-over-code: a new site is a new YAML file, not
new Python). `celery_app.py`'s `beat_schedule` fires `run_scrape_job_from_config`
hourly and `retry_failed_jobs` every 15 minutes (`celery -A api.celery_app beat`).
Quality gates (`quality.py`) catch the failure mode retries/error-handling
can't: a broken selector doesn't crash, it just silently produces
wrong/empty data, so every run's reject ratio and row-count-vs-previous-run
are checked and an alert fires (`alerts.py`, opt-in via `ALERT_WEBHOOK_URL`
— e.g. an n8n webhook or Slack incoming webhook) when either looks wrong.
Self-healing retries re-queue a failed job up to `retry.max_retries` times
(transient errors get another chance); a job that exhausts its budget is
left failed and alerted on exactly once (`permanently_failed` flag prevents
repeat alerts). All offline: Celery tasks called directly (bypasses broker
entirely, runs synchronously) with the pipeline's network calls faked via
the Phase 1 fixture, `requests.post` mocked for alert delivery
(`tests/test_config.py`, `tests/test_quality.py`, `tests/test_alerts.py`,
`tests/test_automation.py`) — 50/50 tests passing.
Phase 7: monitoring, deployment, CI — `logging_config.py` wires structured
logging (loguru: human-readable to stdout, JSON lines to a rotating file)
and opt-in Sentry error tracking (`SENTRY_DSN`) into every entry point
(FastAPI startup, `scrape.py`'s CLI `main()`, Celery tasks); exceptions in
`run_scrape_job` are both logged with a traceback and reported to Sentry
when configured. `quality.build_quality_report()` adds a per-run report
(null/blank % per field, reject ratio, row count vs. previous run) stored
as JSON on each job (`JobORM.quality_report`) alongside the existing
pass/fail warnings. `Dockerfile` (backend, shared by api/worker/beat via
command override) + `frontend/Dockerfile` + `docker-compose.yml` (Postgres,
Redis, api, worker, beat, frontend, with healthchecks) — `docker compose
config` validates the file, but a full `docker compose up` couldn't be run
in this sandbox (Docker Hub is blocked by its network policy), so the
compose stack is unverified end-to-end; try it in an unrestricted
environment. `.github/workflows/ci.yml` runs `pytest` and `tsc`+`vitest`
on every push/PR. New tests: `tests/test_quality_report.py`,
`tests/test_logging_config.py` — 57/57 backend tests passing, 7/7 frontend
tests passing.
Config-driven sites ("paste a URL + CSS selectors, no code") — a second,
generic scraping engine (`scrapers/generic/`) that coexists with the
hardcoded books_toscrape pipeline rather than replacing it:
`models.SiteDefinition` describes a site as data (base URL, a
`{page}`-templated list URL, an item CSS selector, and a list of fields
each with their own selector/attribute/type/required); `parser.py`
extracts items with BeautifulSoup driven entirely by that config;
`validate.py` coerces/rejects rows per field type, same idempotent
row-hash pattern as Phase 3; `storage.py` adds `sites`/`items`/`item_history`
tables (items stored as JSON since fields vary per site) sharing the same
database as the books_toscrape tables; `JobORM` gained a nullable `site_id`
so one `jobs` table covers both engines. Reused rather than duplicated:
Phase 2's retry/backoff/robots.txt logic moved to `scrapers/common/fetch.py`
(books_toscrape now imports it too — refactor, not a rewrite) and Phase 6's
`check_job_quality()` pass/fail thresholds. New API endpoints: `POST /sites`,
`GET /sites`, `GET /sites/{id}`, `POST /sites/{id}/jobs`,
`GET /sites/{id}/jobs/{job_id}/results`, `GET /sites/{id}/jobs/{job_id}/export`.
Frontend: a "Custom Sites" tab alongside the existing Books dashboard, with
a form for entering a site's selectors (dynamic field rows) and a results
table with dynamic columns matching whatever fields were configured.
Documented v1 limits: only simple one-selector-per-field extraction (no
per-site special-casing like books_toscrape's star-rating-from-CSS-class
logic), pagination is a single URL template (no JS-rendered infinite
scroll, no POST-based pagination). Tested offline (parser/validator/storage
unit tests plus a full API test proving the config-driven engine reproduces
the hardcoded scraper's output against the same fixture:
`tests/test_generic_parser.py`, `test_generic_validate.py`,
`test_generic_storage.py`, `test_generic_api.py`) and additionally verified
with a real, non-mocked HTTP run (backend actually scraping a local test
server via retry/robots.txt/pagination logic, driven end-to-end through the
real browser UI) — 79/79 backend tests passing, 11/11 frontend tests
passing.
