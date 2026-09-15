"""Request/response shapes for the config-driven "sites" API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FieldConfigIn(BaseModel):
    name: str
    selector: str
    attr: str = "text"
    type: str = "text"
    required: bool = True


class SiteCreate(BaseModel):
    name: str
    base_url: str
    list_url_template: str
    item_selector: str
    key_selector: str | None = None
    key_attr: str = "href"
    fields: list[FieldConfigIn] = Field(min_length=1)
    max_pages: int = Field(ge=1, le=200, default=10)


class SiteOut(BaseModel):
    id: str
    name: str
    base_url: str
    list_url_template: str
    item_selector: str
    key_selector: str | None
    key_attr: str
    fields: list[FieldConfigIn]
    max_pages: int
    created_at: datetime


class ItemOut(BaseModel):
    key: str
    data: dict[str, Any]
    recorded_at: datetime


class PaginatedItems(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ItemOut]


class DetectSiteRequest(BaseModel):
    url: str


class DetectSiteResponse(BaseModel):
    name: str
    base_url: str
    list_url_template: str
    item_selector: str
    key_selector: str | None
    key_attr: str
    fields: list[FieldConfigIn]
    max_pages: int
    item_count: int  # how many repeated items were found -- a confidence signal for the UI
    preview: list[dict[str, Any]]  # a few extracted rows, so the user can sanity-check before saving
