"""
Scrapes Reddit for Financial Times mentions using the public JSON API.
No authentication required — uses reddit.com/r/{sub}/search.json.
Uses only stdlib + pandas (no extra HTTP library needed).

Usage:
    uv run python -m src.scraper             # full run
    uv run python -m src.scraper --limit 5   # dry run
"""

import argparse
import json
import ssl
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import certifi
import pandas as pd

# macOS Python.org builds don't ship CA certs; use certifi's bundle
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

SEARCH_TERMS = [
    "Financial Times",
    "FT.com",
    "FT paywall",
    "FT Edit app",
    "Unhedged podcast",
]

SUBREDDITS = ["investing", "finance", "ukpolitics", "journalism"]

OUTPUT_FILE = "raw_reddit_data.csv"
ONE_YEAR_AGO = datetime.now(timezone.utc) - timedelta(days=365)

# Reddit blocks default Python user-agent; mimic a browser
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
        return json.loads(resp.read())


def _search_subreddit(
    subreddit: str,
    term: str,
    limit: int | None,
) -> list[dict]:
    rows: list[dict] = []
    after: str | None = None
    page_size = min(limit or 25, 25)  # Reddit max is 25 per page

    while True:
        params: dict = {
            "q": term,
            "restrict_sr": 1,
            "t": "year",
            "sort": "relevance",
            "limit": page_size,
        }
        if after:
            params["after"] = after

        url = f"https://www.reddit.com/r/{subreddit}/search.json?{urlencode(params)}"

        try:
            data = _get_json(url)["data"]
        except Exception as e:
            print(f"  Request failed: {e}")
            break

        children = data.get("children", [])
        if not children:
            break

        for child in children:
            post = child["data"]
            created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
            if created < ONE_YEAR_AGO:
                continue

            rows.append({
                "id": post["id"],
                "post_id": post["id"],
                "type": "post",
                "subreddit": subreddit,
                "search_term": term,
                "title": post.get("title", ""),
                "body": post.get("selftext", ""),
                "author": post.get("author", "[deleted]"),
                "created_utc": created.isoformat(),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "url": f"https://reddit.com{post.get('permalink', '')}",
            })

            if limit and len(rows) >= limit:
                return rows

        after = data.get("after")
        if not after:
            break

        time.sleep(2)  # conservative rate limit between pages

    return rows


def scrape(limit: int | None = None) -> pd.DataFrame:
    all_rows: list[dict] = []
    seen_ids: set[str] = set()
    total = 0

    for sub_name in SUBREDDITS:
        for term in SEARCH_TERMS:
            print(f"Searching r/{sub_name} for '{term}'...")

            remaining = (limit - total) if limit else None
            rows = _search_subreddit(sub_name, term, remaining)

            for row in rows:
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    all_rows.append(row)
                    total += 1

            print(f"  → {len(rows)} posts (total so far: {total})")
            time.sleep(2)

            if limit and total >= limit:
                break

        if limit and total >= limit:
            break

    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(df)} rows to {OUTPUT_FILE}")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Reddit for FT mentions")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max total posts to collect (omit for full run)",
    )
    args = parser.parse_args()
    scrape(limit=args.limit)
