#!/usr/bin/env python3
"""
Convert an audible-cli library export (JSON) into a Goodreads-compatible
import CSV.

Usage:
    python audible_to_goodreads.py library.json -o goodreads_import.csv

Where library.json comes from:
    audible library export -f json -o library.json

Goodreads has no ISBN for most audiobooks, so this script looks up each
title via the free Open Library Search API to backfill ISBN/ISBN13 and
improve match rates on import. Titles that can't be matched are still
included (Goodreads will create a new "book" entry for them, or you can
match manually after import).
"""

import argparse
import csv
import json
import sys
import time
import urllib.parse
from datetime import datetime

import requests

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"

GOODREADS_FIELDS = [
    "Title",
    "Author",
    "ISBN",
    "ISBN13",
    "My Rating",
    "Average Rating",
    "Publisher",
    "Binding",
    "Number of Pages",
    "Year Published",
    "Original Publication Year",
    "Date Read",
    "Date Added",
    "Bookshelves",
    "Exclusive Shelf",
    "My Review",
    "Private Notes",
    "Read Count",
    "Owned Copies",
]


def load_library(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # audible-cli exports either a bare list or {"library": [...]}
    if isinstance(data, dict):
        for key in ("library", "items", "books"):
            if key in data and isinstance(data[key], list):
                return data[key]
        raise ValueError(
            "Could not find a book list in the JSON file. "
            "Expected a top-level list or a 'library'/'items'/'books' key."
        )
    if isinstance(data, list):
        return data
    raise ValueError("Unrecognized JSON shape for library export.")


def first_author(authors_field):
    """audible-cli represents authors as a list of dicts, a list of
    strings, or a comma-joined string depending on version. Normalize."""
    if not authors_field:
        return ""
    if isinstance(authors_field, str):
        return authors_field.split(",")[0].strip()
    if isinstance(authors_field, list):
        first = authors_field[0]
        if isinstance(first, dict):
            return first.get("name", "").strip()
        return str(first).strip()
    return ""


def all_authors(authors_field):
    if not authors_field:
        return ""
    if isinstance(authors_field, str):
        return authors_field
    if isinstance(authors_field, list):
        names = []
        for a in authors_field:
            if isinstance(a, dict):
                names.append(a.get("name", "").strip())
            else:
                names.append(str(a).strip())
        return ", ".join(n for n in names if n)
    return ""


def parse_year(date_str):
    if not date_str:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y"):
        try:
            return str(datetime.strptime(date_str[: len(fmt) if fmt != "%Y" else 4], fmt).year)
        except ValueError:
            continue
    return ""


def to_goodreads_date(date_str):
    """Goodreads wants YYYY/MM/DD."""
    if not date_str:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y/%m/%d")
        except ValueError:
            continue
    return ""


def exclusive_shelf(book):
    """Map Audible listening progress to a Goodreads shelf."""
    is_finished = book.get("is_finished")
    percent = book.get("percent_complete")

    if is_finished is True:
        return "read"
    if percent is not None:
        try:
            pct = float(percent)
            if pct >= 100:
                return "read"
            if pct > 0:
                return "currently-reading"
        except (TypeError, ValueError):
            pass
    return "to-read"


def lookup_isbn(title, author, session, cache):
    """Query Open Library for an ISBN match. Returns (isbn, isbn13, publisher, pages)."""
    key = (title.lower().strip(), author.lower().strip())
    if key in cache:
        return cache[key]

    result = ("", "", "", "")
    try:
        params = {
            "title": title,
            "author": author,
            "limit": 1,
            "fields": "isbn,publisher,number_of_pages_median",
        }
        resp = session.get(OPEN_LIBRARY_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        if docs:
            doc = docs[0]
            isbns = doc.get("isbn", [])
            isbn10 = next((i for i in isbns if len(i) == 10), "")
            isbn13 = next((i for i in isbns if len(i) == 13), "")
            publisher = (doc.get("publisher") or [""])[0]
            pages = doc.get("number_of_pages_median", "")
            result = (isbn10, isbn13, publisher, str(pages) if pages else "")
    except requests.RequestException as e:
        print(f"  [warn] ISBN lookup failed for '{title}': {e}", file=sys.stderr)

    cache[key] = result
    return result


def convert(library, do_lookup=True, delay=0.5, progress_callback=None):
    """progress_callback(idx, total, title), if given, is called after each
    book is processed (used by the web UI to drive a progress bar)."""
    rows = []
    cache = {}
    session = requests.Session()
    session.headers.update({"User-Agent": "audible-to-goodreads/1.0"})

    total = len(library)
    for idx, book in enumerate(library, start=1):
        title = book.get("title") or book.get("Title") or ""
        subtitle = book.get("subtitle") or ""
        author = first_author(book.get("authors"))
        authors_all = all_authors(book.get("authors"))
        purchase_date = book.get("purchase_date") or book.get("date_added") or ""
        release_date = book.get("release_date") or ""
        rating = book.get("rating") or ""

        print(f"[{idx}/{total}] {title}")

        isbn10, isbn13, publisher, pages = ("", "", "", "")
        if do_lookup and title:
            isbn10, isbn13, publisher, pages = lookup_isbn(title, author, session, cache)
            time.sleep(delay)

        row = {
            "Title": title,
            "Author": author or authors_all,
            "ISBN": f'="{isbn10}"' if isbn10 else "",
            "ISBN13": f'="{isbn13}"' if isbn13 else "",
            "My Rating": "0",
            "Average Rating": rating,
            "Publisher": publisher,
            "Binding": "Audiobook",
            "Number of Pages": pages,
            "Year Published": parse_year(release_date),
            "Original Publication Year": parse_year(release_date),
            "Date Read": to_goodreads_date(purchase_date) if exclusive_shelf(book) == "read" else "",
            "Date Added": to_goodreads_date(purchase_date),
            "Bookshelves": "audiobook",
            "Exclusive Shelf": exclusive_shelf(book),
            "My Review": "",
            "Private Notes": f"ASIN: {book.get('asin', '')}" if book.get("asin") else "",
            "Read Count": "1" if exclusive_shelf(book) == "read" else "0",
            "Owned Copies": "1",
        }
        rows.append(row)

        if progress_callback:
            progress_callback(idx, total, title)

    return rows


def write_csv(rows, out_path):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GOODREADS_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Path to audible-cli library.json export")
    parser.add_argument("-o", "--output", default="goodreads_import.csv", help="Output CSV path")
    parser.add_argument("--no-isbn-lookup", action="store_true", help="Skip Open Library ISBN lookups (faster, lower match rate)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between Open Library requests (default 0.5)")
    args = parser.parse_args()

    library = load_library(args.input)
    print(f"Loaded {len(library)} titles from {args.input}")

    rows = convert(library, do_lookup=not args.no_isbn_lookup, delay=args.delay)
    write_csv(rows, args.output)

    matched = sum(1 for r in rows if r["ISBN"] or r["ISBN13"])
    print(f"\nWrote {len(rows)} rows to {args.output}")
    if not args.no_isbn_lookup:
        print(f"ISBN matched: {matched}/{len(rows)}")
    print("\nNext step: Goodreads -> My Books -> Import and export -> Import books, and upload this CSV.")


if __name__ == "__main__":
    main()
