"""
Phase 4: FastAPI backend.

POST   /jobs                -> create a scrape job, hand it to Celery, return 202 immediately
GET    /jobs/{id}            -> job status + row counts
GET    /jobs/{id}/results    -> paginated rows that job produced
GET    /jobs/{id}/export     -> CSV download of that job's rows

Run locally:  uvicorn api.main:app --reload --port 8000
(needs a Celery worker running too: celery -A api.celery_app worker --loglevel=info,
 and Redis reachable at REDIS_URL)
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrapers.books_toscrape.logging_config import configure_logging
from scrapers.books_toscrape.storage.db import BookHistoryORM, JobORM, get_engine, init_db

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
