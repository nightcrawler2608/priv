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
