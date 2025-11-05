"""Check open-access availability for DOIs using the Unpaywall API."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List

import httpx
from urllib.parse import quote

ARTICLES_DEFAULT = Path("artifacts/pubmed_articles.json")
STATUS_LOG_DEFAULT = Path("artifacts/unpaywall_status.jsonl")
SUMMARY_DEFAULT = Path("artifacts/unpaywall_summary.json")

REQUEST_DELAY = 0.2  # five requests per second to stay polite
TIMEOUT_SECONDS = 30


def load_articles(path: Path) -> Iterable[dict]:
    data = json.loads(path.read_text())
    for article in data.get("articles", []):
        doi = article.get("doi")
        if doi:
            yield {
                "pubmed_id": article.get("pubmed_id"),
                "doi": doi,
            }


def load_existing_status(path: Path) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    if not path.exists():
        return results
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            results[record["doi"]] = record
    return results


def persist_status(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def fetch_unpaywall(doi: str, email: str) -> dict:
    url = f"https://api.unpaywall.org/v2/{quote(doi, safe='')}"
    params = {"email": email}
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    is_oa = payload.get("is_oa", False)
    best_loc = payload.get("best_oa_location") or {}
    oa_url = best_loc.get("url_for_pdf") or best_loc.get("url")
    return {
        "doi": doi,
        "is_oa": bool(is_oa),
        "oa_status": payload.get("oa_status"),
        "has_repository_copy": bool(payload.get("oa_locations")),
        "best_oa_url": oa_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate open-access coverage via Unpaywall")
    parser.add_argument("--articles", type=Path, default=ARTICLES_DEFAULT)
    parser.add_argument("--email", required=True, help="Contact email for Unpaywall API")
    parser.add_argument("--status-log", type=Path, default=STATUS_LOG_DEFAULT)
    parser.add_argument("--summary", type=Path, default=SUMMARY_DEFAULT)
    parser.add_argument("--limit", type=int, help="Optional limit on number of DOIs to query")
    args = parser.parse_args()

    existing = load_existing_status(args.status_log)
    seen = set(existing.keys())

    articles = list(load_articles(args.articles))
    if args.limit is not None:
        articles = articles[: args.limit]

    total = len(articles)
    processed = 0

    for entry in articles:
        doi = entry["doi"]
        if doi in seen:
            processed += 1
            continue
        try:
            record = fetch_unpaywall(doi, args.email)
        except httpx.HTTPStatusError as exc:
            record = {
                "doi": doi,
                "error": f"HTTP {exc.response.status_code}",
            }
        except httpx.HTTPError as exc:  # timeout or other errors
            record = {
                "doi": doi,
                "error": str(exc),
            }
        persist_status(args.status_log, record)
        existing[doi] = record
        seen.add(doi)
        processed += 1
        if processed % 100 == 0:
            print(f"Processed {processed}/{total} DOIs")
        time.sleep(REQUEST_DELAY)

    counters = Counter()
    for record in existing.values():
        if record.get("error"):
            counters["error"] += 1
        elif record.get("is_oa"):
            counters["open_access"] += 1
            if record.get("best_oa_url"):
                counters["open_access_with_url"] += 1
        else:
            counters["closed"] += 1

    summary = {
        "total_records": len(existing),
        "open_access": counters.get("open_access", 0),
        "open_access_with_url": counters.get("open_access_with_url", 0),
        "closed": counters.get("closed", 0),
        "errors": counters.get("error", 0),
    }

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
