"""
Phase 3: what a "good row" looks like, and turning raw parsed rows into
trustworthy ones.

Book       = raw, unvalidated output of parse_books() straight from HTML.
BookRecord = validated row. Only BookRecords are allowed into storage.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

logger = logging.getLogger(__name__)


@dataclass
class Book:
    """Raw, unvalidated row straight out of HTML parsing."""
    url: str
    title: str
    price: float
    rating: int
    availability: str


class BookRecord(BaseModel):
    """A validated row. Values here are guaranteed to satisfy the rules
    below — nothing gets this far without passing them."""

    model_config = ConfigDict(frozen=True)

    url: str
    title: str
    price: float
    rating: int
    availability: str

    @field_validator("url")
    @classmethod
    def url_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url must not be blank")
        return v

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be blank")
        return v

    @field_validator("price")
    @classmethod
    def price_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("price must be >= 0")
        return v

    @field_validator("rating")
    @classmethod
    def rating_in_range(cls, v: int) -> int:
        if not 0 <= v <= 5:
            raise ValueError("rating must be between 0 and 5 stars")
        return v

    @property
    def in_stock(self) -> bool:
        return "in stock" in self.availability.lower()

    def row_hash(self) -> str:
        """Stable fingerprint of the fields that matter for change
        detection. Same fields -> same hash -> nothing to re-store."""
        payload = f"{self.title}|{self.price}|{self.rating}|{self.availability}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clean_and_validate(raw_books: list[Book]) -> list[BookRecord]:
    """Validate raw parsed rows; log and drop anything malformed instead of
    ever letting bad data reach storage."""
    clean: list[BookRecord] = []
    for b in raw_books:
        try:
            clean.append(BookRecord(
                url=b.url, title=b.title, price=b.price,
                rating=b.rating, availability=b.availability,
            ))
        except ValidationError as exc:
            logger.warning("rejected row (url=%s): %s", getattr(b, "url", "?"), exc)
    return clean
