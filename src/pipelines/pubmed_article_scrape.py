"""Fetch PubMed article metadata/HTML for all referenced PMIDs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from src.services.pubmed_fetcher import PubMedArticle, fetch_all

DEFAULT_REFERENCES_PATH = Path("artifacts/pubmed_references.json")
DEFAULT_OUTPUT_PATH = Path("artifacts/pubmed_articles.json")


def load_reference_index(path: Path, limit: int | None = None) -> tuple[List[str], Dict[str, Dict[str, List[dict]]]]:
    data = json.loads(path.read_text())
    index: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: {"ec_numbers": set(), "samples": []})

    for enzyme in data.get("enzymes", []):
        ec_number = enzyme.get("ec_number")
        references = enzyme.get("references", [])
        for reference in references:
            for pmid in reference.get("pubmed_ids", []):
                entry = index[pmid]
                entry["ec_numbers"].add(ec_number)
                if len(entry["samples"]) < 5:
                    entry["samples"].append(
                        {
                            "ec_number": ec_number,
                            "field_code": reference.get("field_code"),
                            "field_name": reference.get("field_name"),
                            "value_text": reference.get("value_text"),
                        }
                    )

    pmids = sorted(index.keys())
    if limit is not None:
        pmids = pmids[:limit]
    return pmids, index


def serialize_article(
    article: PubMedArticle,
    link_index: Dict[str, Dict[str, List[dict]]],
) -> dict:
    linked = link_index.get(article.pubmed_id, {"ec_numbers": set(), "samples": []})
    doi_url = article.doi_url
    return {
        "pubmed_id": article.pubmed_id,
        "pubmed_url": article.pubmed_url,
        "title": article.title,
        "journal": article.journal,
        "publication_date": article.publication_date,
        "doi": article.doi,
        "doi_url": doi_url,
        "authors": article.authors,
        "abstract": article.abstract,
        "clean_html": article.clean_html,
        "linked_ec_numbers": sorted(linked["ec_numbers"]),
        "sample_references": linked["samples"],
    }


def export_articles(
    *,
    references_path: Path,
    output_path: Path,
    limit: int | None = None,
) -> dict:
    if not references_path.exists():
        raise FileNotFoundError(f"Reference file not found: {references_path}")

    pmids, link_index = load_reference_index(references_path, limit)
    articles = fetch_all(pmids)

    serialized = [serialize_article(article, link_index) for article in articles]

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_references": str(references_path.resolve()),
        "total_pmids": len(pmids),
        "articles": serialized,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch PubMed articles for referenced PMIDs")
    parser.add_argument(
        "--references",
        type=Path,
        default=DEFAULT_REFERENCES_PATH,
        help="Path to pubmed reference index JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Destination JSON file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit of PMIDs to process (useful for testing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    export_articles(
        references_path=args.references.resolve(),
        output_path=args.output.resolve(),
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
