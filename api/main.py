"""
Phase 4: FastAPI backend. Plus the config-driven "sites" feature (any URL,
any fields, described by a SiteDefinition instead of hardcoded Python):

POST   /jobs                       -> create a books_toscrape scrape job, 202 immediately
GET    /jobs/{id}                  -> job status + row counts (works for either kind of job)
GET    /jobs/{id}/results          -> paginated rows that job produced (books_toscrape)
GET    /jobs/{id}/export           -> CSV download of that job's rows (books_toscrape)

POST   /sites                      -> save a new site definition (URL + CSS selectors)
GET    /sites                      -> list saved sites
GET    /sites/{site_id}            -> one site definition
POST   /sites/detect                -> "paste a URL, get data": guess item_selector/fields from a live page
POST   /sites/{site_id}/jobs       -> create+run a scrape job for that site, 202 immediately
GET    /sites/{site_id}/jobs/{id}/results -> paginated rows that job produced
GET    /sites/{site_id}/jobs/{id}/export  -> CSV download of that job's rows

Run locally:  uvicorn api.main:app --reload --port 8000
(needs a Celery worker running too: celery -A api.celery_app worker --loglevel=info,
 and Redis reachable at REDIS_URL)
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrapers.books_toscrape.logging_config import configure_logging
from scrapers.books_toscrape.storage.db import BookHistoryORM, JobORM, get_engine, init_db
from scrapers.common.fetch import PermanentFetchError, TransientFetchError, fetch_html
from scrapers.generic.autodetect import detect_site_structure
from scrapers.generic.models import SiteDefinition
from scrapers.generic.parser import parse_items
from scrapers.generic.storage import ItemHistoryORM, SiteORM  # noqa: F401 -- import registers these tables on Base.metadata
from scrapers.generic.validate import clean_and_validate_items

from .generic_schemas import (
    DetectSiteRequest,
    DetectSiteResponse,
    FieldConfigIn,
    ItemOut,
    PaginatedItems,
    SiteCreate,
    SiteOut,
)
from .generic_tasks import run_generic_scrape_job
from .schemas import BookOut, JobCreate, JobOut, PaginatedBooks
from .tasks import run_scrape_job

configure_logging()
app = FastAPI(title="Data Scraping Tool API")

# Frontend (Vite dev server) runs on a different origin/port than the API,
# so the browser needs an explicit CORS allow before it can call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _session() -> Session:
    """Fresh engine per call (re-reads DATABASE_URL each time) -- keeps
    tests trivially isolated by env var; Phase 7 will switch this to an
    engine created once at app startup for production use."""
    engine = get_engine()
    init_db(engine)
    return Session(engine)


@app.post("/jobs", status_code=202, response_model=JobOut)
def create_job(payload: JobCreate) -> JobOut:
    job_id = uuid.uuid4().hex
    with _session() as session:
        job = JobORM(
            id=job_id,
            status="queued",
            max_pages=payload.max_pages,
            created_at=datetime.now(timezone.utc),
            rows_new=0, rows_changed=0, rows_unchanged=0, rows_rejected=0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        out = JobOut.model_validate(job)

    run_scrape_job.delay(job_id, payload.max_pages)  # hands off to the worker; API returns now
    return out


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str) -> JobOut:
    with _session() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return JobOut.model_validate(job)


@app.get("/jobs/{job_id}/results", response_model=PaginatedBooks)
def get_results(job_id: str, limit: int = 50, offset: int = 0) -> PaginatedBooks:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")

    with _session() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")

        base = select(BookHistoryORM).where(BookHistoryORM.job_id == job_id)
        total = session.scalar(select(func.count()).select_from(base.subquery()))
        rows = session.scalars(
            base.order_by(BookHistoryORM.url).limit(limit).offset(offset)
        ).all()

        return PaginatedBooks(
            total=total or 0,
            limit=limit,
            offset=offset,
            items=[BookOut.model_validate(r) for r in rows],
        )


@app.get("/jobs/{job_id}/export")
def export_results(job_id: str) -> StreamingResponse:
    with _session() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")

        rows = session.scalars(
            select(BookHistoryORM).where(BookHistoryORM.job_id == job_id).order_by(BookHistoryORM.url)
        ).all()
        df = pd.DataFrame([{
            "url": r.url, "title": r.title, "price": r.price,
            "rating": r.rating, "availability": r.availability,
        } for r in rows])

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="books_{job_id}.csv"'},
    )


def _site_orm_to_out(row: SiteORM) -> SiteOut:
    return SiteOut(
        id=row.id, name=row.name, base_url=row.base_url,
        list_url_template=row.list_url_template, item_selector=row.item_selector,
        key_selector=row.key_selector, key_attr=row.key_attr,
        fields=[FieldConfigIn(**f) for f in json.loads(row.fields_json)],
        max_pages=row.max_pages, created_at=row.created_at,
    )


@app.post("/sites", status_code=201, response_model=SiteOut)
def create_site(payload: SiteCreate) -> SiteOut:
    site_id = uuid.uuid4().hex
    try:
        # Round-trip through SiteDefinition so the same validation used at
        # scrape time (unique field names, single-page max_pages capping,
        # etc.) applies immediately instead of at the first job. Store the
        # VALIDATED object's fields below, not the raw payload -- e.g.
        # max_pages may have been corrected (capped to 1 for a template
        # with no {page} placeholder), and that correction must actually
        # reach the database, not just this in-memory check.
        site_def = SiteDefinition(
            id=site_id, name=payload.name, base_url=payload.base_url,
            list_url_template=payload.list_url_template, item_selector=payload.item_selector,
            key_selector=payload.key_selector, key_attr=payload.key_attr,
            fields=[f.model_dump() for f in payload.fields], max_pages=payload.max_pages,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with _session() as session:
        row = SiteORM(
            id=site_id, name=site_def.name, base_url=site_def.base_url,
            list_url_template=site_def.list_url_template, item_selector=site_def.item_selector,
            key_selector=site_def.key_selector, key_attr=site_def.key_attr,
            fields_json=json.dumps([f.model_dump() for f in site_def.fields]),
            max_pages=site_def.max_pages, created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _site_orm_to_out(row)


@app.get("/sites", response_model=list[SiteOut])
def list_sites() -> list[SiteOut]:
    with _session() as session:
        rows = session.scalars(select(SiteORM).order_by(SiteORM.created_at.desc())).all()
        return [_site_orm_to_out(r) for r in rows]


@app.post("/sites/detect", response_model=DetectSiteResponse)
def detect_site(payload: DetectSiteRequest) -> DetectSiteResponse:
    """"Paste a URL, get data": fetches the page live and guesses
    item_selector + fields, no CSS knowledge required. Returns a preview
    of actually-extracted rows so the caller can sanity-check the guess
    before saving it as a site (POST /sites) -- a heuristic, not magic,
    so it's meant to be reviewed, not blindly trusted."""
    try:
        html = fetch_html(payload.url)
    except PermanentFetchError as exc:
        raise HTTPException(status_code=422, detail=f"could not fetch that URL: {exc}") from exc
    except TransientFetchError as exc:
        raise HTTPException(status_code=502, detail=f"that site isn't responding right now: {exc}") from exc

    detected = detect_site_structure(html)
    if detected is None:
        raise HTTPException(
            status_code=422,
            detail="couldn't find a repeated list/grid of items on that page -- "
                   "try a category or search-results page rather than a single article, "
                   "or fall back to the manual selector form below",
        )

    parsed = urlparse(payload.url)
    base_url = f"{parsed.scheme}://{parsed.netloc}/"
    fields_out = [FieldConfigIn(name=f.name, selector=f.selector, attr=f.attr, type=f.type, required=False) for f in detected.fields]

    # A real preview, not just the guessed selector names -- built from a
    # throwaway SiteDefinition run through the actual parser, so what the
    # user sees here is exactly what saving this config would produce.
    preview_site = SiteDefinition(
        id="preview", name="preview", base_url=base_url, list_url_template=payload.url,
        item_selector=detected.item_selector, key_selector=detected.key_selector,
        key_attr=detected.key_attr, fields=[f.model_dump() for f in fields_out],
    )
    raw_items = parse_items(html, payload.url, preview_site)
    clean_items, _ = clean_and_validate_items(raw_items, preview_site)
    preview_rows = [{f.name: item.get(f.name) for f in detected.fields} for item in clean_items[:5]]

    return DetectSiteResponse(
        name=parsed.netloc, base_url=base_url, list_url_template=payload.url,
        item_selector=detected.item_selector, key_selector=detected.key_selector,
        key_attr=detected.key_attr, fields=fields_out, max_pages=1,
        item_count=detected.item_count, preview=preview_rows,
    )


@app.get("/sites/{site_id}", response_model=SiteOut)
def get_site(site_id: str) -> SiteOut:
    with _session() as session:
        row = session.get(SiteORM, site_id)
        if row is None:
            raise HTTPException(status_code=404, detail="site not found")
        return _site_orm_to_out(row)


@app.post("/sites/{site_id}/jobs", status_code=202, response_model=JobOut)
def create_site_job(site_id: str) -> JobOut:
    with _session() as session:
        site_row = session.get(SiteORM, site_id)
        if site_row is None:
            raise HTTPException(status_code=404, detail="site not found")

        job_id = uuid.uuid4().hex
        job = JobORM(
            id=job_id, status="queued", max_pages=site_row.max_pages, site_id=site_id,
            created_at=datetime.now(timezone.utc),
            rows_new=0, rows_changed=0, rows_unchanged=0, rows_rejected=0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        out = JobOut.model_validate(job)

    run_generic_scrape_job.delay(job_id, site_id)
    return out


@app.get("/sites/{site_id}/jobs/{job_id}/results", response_model=PaginatedItems)
def get_site_job_results(site_id: str, job_id: str, limit: int = 50, offset: int = 0) -> PaginatedItems:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")

    with _session() as session:
        job = session.get(JobORM, job_id)
        if job is None or job.site_id != site_id:
            raise HTTPException(status_code=404, detail="job not found for this site")

        base = select(ItemHistoryORM).where(ItemHistoryORM.job_id == job_id)
        total = session.scalar(select(func.count()).select_from(base.subquery()))
        rows = session.scalars(
            base.order_by(ItemHistoryORM.item_key).limit(limit).offset(offset)
        ).all()

        return PaginatedItems(
            total=total or 0,
            limit=limit,
            offset=offset,
            items=[ItemOut(key=r.item_key, data=json.loads(r.data_json), recorded_at=r.recorded_at) for r in rows],
        )


@app.get("/sites/{site_id}/jobs/{job_id}/export")
def export_site_job_results(site_id: str, job_id: str) -> StreamingResponse:
    with _session() as session:
        job = session.get(JobORM, job_id)
        if job is None or job.site_id != site_id:
            raise HTTPException(status_code=404, detail="job not found for this site")

        rows = session.scalars(
            select(ItemHistoryORM).where(ItemHistoryORM.job_id == job_id).order_by(ItemHistoryORM.item_key)
        ).all()
        df = pd.DataFrame([json.loads(r.data_json) for r in rows])

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{site_id}_{job_id}.csv"'},
    )
