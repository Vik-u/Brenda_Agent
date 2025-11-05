"""Generate a lightweight index of PubMed articles linked to BRENDA EC numbers."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ARTICLES_DEFAULT = Path("artifacts/pubmed_articles.json")
OUTPUT_DEFAULT = Path("artifacts/pubmed_links.json")


def load_articles(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"PubMed article payload not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_link_index(
    *,
    articles_data: Dict[str, Any],
    source_path: Path,
    sample_limit: int,
) -> Dict[str, Any]:
    articles: List[Dict[str, Any]] = []
    for entry in articles_data.get("articles", []):
        samples = entry.get("sample_references") or []
        if sample_limit > 0:
            samples = samples[:sample_limit]
        articles.append(
            {
                "pubmed_id": entry.get("pubmed_id"),
                "pubmed_url": entry.get("pubmed_url"),
                "doi": entry.get("doi"),
                "doi_url": entry.get("doi_url"),
                "linked_ec_numbers": entry.get("linked_ec_numbers", []),
                "sample_references": samples,
            }
        )

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_articles": str(source_path.resolve()),
        "total_links": len(articles),
        "articles": articles,
    }


def write_output(payload: Dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a compact index of PubMed links derived from the scraped articles payload.",
    )
    parser.add_argument(
        "--articles",
        type=Path,
        default=ARTICLES_DEFAULT,
        help="Path to the pubmed_articles.json file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DEFAULT,
        help="Destination for the compact link index JSON.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="Truncate each article's sample reference list to this many entries (use 0 to keep all).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    articles = load_articles(args.articles.resolve())
    payload = build_link_index(
        articles_data=articles,
        source_path=args.articles,
        sample_limit=max(args.sample_limit, 0),
    )
    write_output(payload, args.output.resolve())
    print(f"Wrote {payload['total_links']} article links to {args.output}")


if __name__ == "__main__":
    main()
