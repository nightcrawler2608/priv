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
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import Book, clean_and_validate
from .storage.db import get_engine, init_db, upsert_books
from .storage.raw_snapshots import save_raw_snapshot

BASE_URL = "https://books.toscrape.com/"
CATALOGUE_URL = BASE_URL + "catalogue/page-1.html"
ROBOTS_URL = BASE_URL + "robots.txt"
USER_AGENT = "data-scraping-tool-tutorial/0.1 (+https://github.com/; learning project)"

RATING_WORDS = {"Zero": 0, "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

# Requests that failed for a reason worth retrying (network hiccup, server
# overloaded, rate-limited). The caller should back off and try again.
class TransientFetchError(Exception):
    pass


# Requests that failed for a reason that will never change on retry (page
# genuinely doesn't exist, we're blocked). Retrying is pointless / rude.
class PermanentFetchError(Exception):
    pass


def _fetch_once(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise TransientFetchError(f"network error fetching {url}: {exc}") from exc

    if resp.status_code == 404:
        raise PermanentFetchError(f"404 Not Found: {url}")
    if resp.status_code == 403:
        raise PermanentFetchError(f"403 Forbidden (blocked?): {url}")
    if resp.status_code == 429 or 500 <= resp.status_code < 600:
        raise TransientFetchError(f"HTTP {resp.status_code} from {url}")

    resp.raise_for_status()
    return resp.text


def fetch_html(url: str = CATALOGUE_URL, *, max_attempts: int = 4, base_delay: float = 1.0) -> str:
    """Download one page's raw HTML, retrying transient failures with
    exponential backoff. Permanent failures (404/403) raise immediately,
    with no retry."""
    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_delay, min=base_delay, max=base_delay * 8),
        retry=retry_if_exception_type(TransientFetchError),
        reraise=True,
    )
    return retryer(_fetch_once, url)


def is_allowed(robots_txt: str, path: str, user_agent: str = USER_AGENT) -> bool:
    """Pure function: given robots.txt content, is this path allowed?"""
    rp = RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch(user_agent, path)


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


def save_csv(books: list[Book], out_path: Path) -> None:
    df = pd.DataFrame([asdict(b) for b in books])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def main() -> None:
    robots_txt = fetch_robots_txt()
    if not is_allowed(robots_txt, "/catalogue/page-1.html"):
        print("robots.txt disallows the catalogue path — stopping.")
        return

    engine = get_engine()
    init_db(engine)

    raw_books: list[Book] = []
    for page_num, html in iter_catalogue_pages(delay_seconds=1.0):
        page_url = f"{BASE_URL}catalogue/page-{page_num}.html"
        save_raw_snapshot(html, page_num, Path("data/raw_html"))
        page_books = parse_books(html, page_url=page_url)
        print(f"page {page_num}: {len(page_books)} rows")
        raw_books.extend(page_books)

    clean_books = clean_and_validate(raw_books)
    rejected = len(raw_books) - len(clean_books)

    with Session(engine) as session:
        stats = upsert_books(session, clean_books)

    print(
        f"validated {len(clean_books)}/{len(raw_books)} rows "
        f"({rejected} rejected) — new={stats['new']} changed={stats['changed']} "
        f"unchanged={stats['unchanged']}"
    )

    out_path = Path("data/books_catalogue.csv")
    save_csv([Book(url=r.url, title=r.title, price=r.price, rating=r.rating,
                    availability=r.availability) for r in clean_books], out_path)
    print(f"Saved {len(clean_books)} current rows to {out_path}")


if __name__ == "__main__":
    sys.exit(main())
