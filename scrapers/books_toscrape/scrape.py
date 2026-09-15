"""
Phase 1 scraper for books.toscrape.com.

Pipeline: fetch one catalogue page -> parse book rows -> save to CSV.
Run directly:  python -m scrapers.books_toscrape.scrape
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
CATALOGUE_URL = BASE_URL + "catalogue/page-1.html"
USER_AGENT = "data-scraping-tool-tutorial/0.1 (+https://github.com/; learning project)"

RATING_WORDS = {"Zero": 0, "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass
class Book:
    title: str
    price: float
    rating: int
    availability: str


def fetch_html(url: str = CATALOGUE_URL) -> str:
    """Download one page's raw HTML. Network call — not used in tests."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()
    return resp.text


def parse_books(html: str) -> list[Book]:
    """Pure function: HTML string in, list[Book] out. No network. This is
    what the offline test exercises against a saved fixture file."""
    soup = BeautifulSoup(html, "lxml")
    books: list[Book] = []

    for article in soup.select("article.product_pod"):
        title = article.select_one("h3 a")["title"].strip()

        price_text = article.select_one("p.price_color").get_text(strip=True)
        price = float(price_text.replace("£", "").replace("£", ""))

        rating_classes = article.select_one("p.star-rating")["class"]
        # classes look like ["star-rating", "Three"] -- the word is the rating
        rating_word = next((c for c in rating_classes if c != "star-rating"), "Zero")
        rating = RATING_WORDS.get(rating_word, 0)

        availability = article.select_one(".availability").get_text(strip=True)

        books.append(Book(title=title, price=price, rating=rating, availability=availability))

    return books


def save_csv(books: list[Book], out_path: Path) -> None:
    df = pd.DataFrame([asdict(b) for b in books])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def main() -> None:
    html = fetch_html()
    books = parse_books(html)
    out_path = Path("data/books_page1.csv")
    save_csv(books, out_path)
    print(f"Saved {len(books)} rows to {out_path}")


if __name__ == "__main__":
    sys.exit(main())
