"""Phase 4: request/response shapes for the API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    max_pages: int = 50


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    max_pages: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    rows_new: int
    rows_changed: int
    rows_unchanged: int
    rows_rejected: int
    error_message: str | None


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    title: str
    price: float
    rating: int
    availability: str
    recorded_at: datetime


class PaginatedBooks(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[BookOut]
