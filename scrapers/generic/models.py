"""
The "config-driven sites" feature: instead of one Python module per site
(like scrapers/books_toscrape), a site is described entirely by data --
a SiteDefinition, submitted through the API/frontend and stored in the
database. Adding a new site becomes filling in a form, not writing code.

Deliberate v1 scope limits (documented, not hidden):
- Only simple "one CSS selector -> one field" extraction. books_toscrape's
  special-case logic (reading a rating out of a CSS *class name* like
  "star-rating Three") isn't expressible here -- that kind of per-site
  quirk is exactly why scrapers/books_toscrape exists as its own module.
- Pagination is a single URL template with a {page} placeholder. Sites
  using POST requests, JS-rendered infinite scroll, or cursor-based
  pagination aren't supported (JS rendering has the same Playwright
  escape hatch documented in books_toscrape/fetch_js.py; nothing here
  is fetch_js-aware yet).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class FieldConfig(BaseModel):
    name: str  # becomes a column name in results -- keep it simple (letters/digits/underscore)
    selector: str  # CSS selector, applied within each matched item element
    attr: str = "text"  # "text" (get_text) or an HTML attribute name, e.g. "href", "src", "title"
    type: str = "text"  # "text" or "number"
    required: bool = True

    @field_validator("name")
    @classmethod
    def name_is_identifier_like(cls, v: str) -> str:
        v = v.strip()
        if not v or not v.replace("_", "").isalnum():
            raise ValueError(f"field name must be letters/digits/underscore, got {v!r}")
        return v

    @field_validator("type")
    @classmethod
    def type_is_supported(cls, v: str) -> str:
        if v not in ("text", "number"):
            raise ValueError(f"field type must be 'text' or 'number', got {v!r}")
        return v


class SiteDefinition(BaseModel):
    id: str
    name: str
    base_url: str
    # A plain URL (single page, e.g. "https://example.com/products") works
    # as-is -- max_pages is effectively 1 in that case, since re-fetching
    # the same URL just re-scrapes identical content. Include the literal
    # placeholder "{page}" (e.g. "https://example.com/products?page={page}")
    # only for a site with real pagination you want to walk through.
    list_url_template: str
    item_selector: str  # CSS selector matching each repeated item/row on the list page
    key_selector: str | None = None  # CSS selector for a link whose href becomes the item's stable id
    key_attr: str = "href"
    fields: list[FieldConfig] = Field(min_length=1)
    max_pages: int = Field(ge=1, le=200, default=10)

    @model_validator(mode="after")
    def single_page_when_no_placeholder(self) -> "SiteDefinition":
        # No {page} in the template means every "page" is the same URL --
        # cap max_pages at 1 so we don't re-fetch identical content.
        if "{page}" not in self.list_url_template and self.max_pages > 1:
            self.max_pages = 1
        return self

    @model_validator(mode="after")
    def field_names_unique(self) -> "SiteDefinition":
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            raise ValueError(f"field names must be unique, got {names}")
        return self
