"""
Phase 1+2+3 scraper for books.toscrape.com.

Pipeline: check robots.txt -> paginate catalogue pages (retrying on transient
errors, rate-limited between requests) -> save raw HTML snapshots -> parse
each page -> validate/clean -> upsert into storage (change-detected,
idempotent) -> export current state to CSV.
Run directly:  python -m scrapers.books_toscrape.scrape
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common.fetch import PermanentFetchError, TransientFetchError, fetch_html, is_allowed
from .logging_config import configure_logging
from .models import Book, clean_and_validate
from .storage.db import BookORM, get_engine, init_db, upsert_books
from .storage.raw_snapshots import save_raw_snapshot

BASE_URL = "https://books.toscrape.com/"
CATALOGUE_URL = BASE_URL + "catalogue/page-1.html"
ROBOTS_URL = BASE_URL + "robots.txt"
USER_AGENT = "data-scraping-tool-tutorial/0.1 (+https://github.com/; learning project)"

RATING_WORDS = {"Zero": 0, "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

# TransientFetchError, PermanentFetchError, fetch_html, is_allowed now live
# in scrapers.common.fetch (shared with the generic scraper) -- re-exported
# here (via the import above) so existing imports of this module keep working.


def fetch_robots_txt(base_url: str = BASE_URL) -> str:
    return fetch_html(base_url + "robots.txt")


def iter_catalogue_pages(
    max_pages: int = 50,
    delay_seconds: float = 1.0,
    max_attempts: int = 4,
    base_delay: float = 1.0,
):
    """Yield (page_number, html) for each catalogue page, stopping cleanly
    (not erroring) once pagination runs off the end (404). Sleeps
    delay_seconds between requests so we don't hammer the site."""
    for page_num in range(1, max_pages + 1):
        url = f"{BASE_URL}catalogue/page-{page_num}.html"
        try:
            html = fetch_html(url, max_attempts=max_attempts, base_delay=base_delay)
        except PermanentFetchError:
            break
        yield page_num, html
        if page_num < max_pages:
            time.sleep(delay_seconds)


def parse_books(html: str, page_url: str = CATALOGUE_URL) -> list[Book]:
    """Pure function: HTML string in, list[Book] out. No network. This is
    what the offline test exercises against a saved fixture file.

    page_url is the URL the html was fetched from -- needed to resolve each
    book's relative link into an absolute, stable url (used as the storage
    key in Phase 3)."""
    soup = BeautifulSoup(html, "lxml")
    books: list[Book] = []

    for article in soup.select("article.product_pod"):
        link = article.select_one("h3 a")
        title = link["title"].strip()
        url = urljoin(page_url, link["href"])

        price_text = article.select_one("p.price_color").get_text(strip=True)
        price = float(price_text.replace("£", "").replace("£", ""))

        rating_classes = article.select_one("p.star-rating")["class"]
        # classes look like ["star-rating", "Three"] -- the word is the rating
        rating_word = next((c for c in rating_classes if c != "star-rating"), "Zero")
        rating = RATING_WORDS.get(rating_word, 0)

        availability = article.select_one(".availability").get_text(strip=True)

        books.append(Book(url=url, title=title, price=price, rating=rating, availability=availability))

    return books


def export_books_csv(session: Session, out_path: Path) -> int:
    """Export the current `books` table state to CSV, queried straight
    from storage rather than built up from rows held in memory during the
    scrape -- reflects the true current state (all books ever seen, not
    just this run's), and never needs the whole site's rows in memory."""
    rows = session.scalars(select(BookORM).order_by(BookORM.url)).all()
    df = pd.DataFrame([{
        "url": r.url, "title": r.title, "price": r.price,
        "rating": r.rating, "availability": r.availability,
    } for r in rows])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return len(rows)


def main() -> None:
    configure_logging()
    robots_txt = fetch_robots_txt()
    if not is_allowed(robots_txt, "/catalogue/page-1.html"):
        logger.warning("robots.txt disallows the catalogue path — stopping.")
        return

    engine = get_engine()
    init_db(engine)

    # Process and save one page at a time instead of accumulating every
    # row in memory before storing anything -- bounds memory to roughly
    # one page's worth of rows regardless of how many pages the site has,
    # and a crash partway through still leaves everything scraped so far
    # safely committed to the database.
    total_parsed = 0
    total_rejected = 0
    totals = {"new": 0, "changed": 0, "unchanged": 0}

    with Session(engine) as session:
        for page_num, html in iter_catalogue_pages(delay_seconds=1.0):
            page_url = f"{BASE_URL}catalogue/page-{page_num}.html"
            save_raw_snapshot(html, page_num, Path("data/raw_html"))

            raw_page = parse_books(html, page_url=page_url)
            clean_page = clean_and_validate(raw_page)
            total_parsed += len(raw_page)
            total_rejected += len(raw_page) - len(clean_page)

            page_stats = upsert_books(session, clean_page)  # commits this page now
            for key in totals:
                totals[key] += page_stats[key]
            logger.info(
                "page {}: {} rows ({} rejected)",
                page_num, len(clean_page), len(raw_page) - len(clean_page),
            )

        out_path = Path("data/books_catalogue.csv")
        row_count = export_books_csv(session, out_path)

    logger.info(
        "validated {}/{} rows ({} rejected) — new={} changed={} unchanged={}",
        total_parsed - total_rejected, total_parsed, total_rejected,
        totals["new"], totals["changed"], totals["unchanged"],
    )
    logger.info("Saved {} current rows to {}", row_count, out_path)


if __name__ == "__main__":
    sys.exit(main())
