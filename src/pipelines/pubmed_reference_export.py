"""Export PubMed-linked references from the BRENDA SQLite mirror."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from src.core.settings import get_settings

PUBMED_PATTERN = re.compile(r"pubmed:(\d+)", re.IGNORECASE)


def _resolve_database_path(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    settings = get_settings()
    configured = settings.chatbot.database_path or settings.services.database.url
    if configured.startswith("sqlite:///"):
        configured = configured.replace("sqlite:///", "", 1)
    return Path(configured).expanduser().resolve()


def _fetch_rows(conn: sqlite3.Connection, limit: int | None) -> List[sqlite3.Row]:
    base_query = """
        SELECT
            tf.ec_number,
            tf.field_code,
            COALESCE(NULLIF(tf.field_name, ''), tf.field_code) AS field_name,
            tf.value_text,
            tf.value_raw,
            tf.reference_tokens,
            tf.qualifiers,
            e.recommended_name,
            e.systematic_name,
            e.enzyme_id,
            e.protein_count,
            e.synonym_count
        FROM text_facts AS tf
        JOIN enzymes AS e ON e.ec_number = tf.ec_number
        WHERE (
            LOWER(COALESCE(tf.value_text, '')) LIKE '%pubmed%'
            OR LOWER(COALESCE(tf.reference_tokens, '')) LIKE '%pubmed%'
            OR LOWER(COALESCE(tf.value_raw, '')) LIKE '%pubmed%'
        )
        ORDER BY tf.ec_number
    """
    if limit is not None:
        base_query += " LIMIT ?"
        return conn.execute(base_query, (limit,)).fetchall()
    return conn.execute(base_query).fetchall()


def _extract_pubmed_ids(*values: str | None) -> List[str]:
    ids = set()
    for value in values:
        if not value:
            continue
        ids.update(PUBMED_PATTERN.findall(value))
    return sorted(ids)


def export_pubmed_references(
    *,
    db_path: Path,
    output_path: Path,
    limit: int | None = None,
) -> Dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_rows(conn, limit)
    finally:
        conn.close()

    aggregated: Dict[str, Dict[str, Any]] = {}
    stats = defaultdict(int)

    for row in rows:
        pubmed_ids = _extract_pubmed_ids(
            row["value_text"], row["value_raw"], row["reference_tokens"], row["qualifiers"]
        )
        if not pubmed_ids:
            continue

        ec_number = row["ec_number"]
        if ec_number not in aggregated:
            aggregated[ec_number] = {
                "ec_number": ec_number,
                "enzyme_id": row["enzyme_id"],
                "recommended_name": row["recommended_name"],
                "systematic_name": row["systematic_name"],
                "protein_count": row["protein_count"],
                "synonym_count": row["synonym_count"],
                "references": [],
            }

        aggregated[ec_number]["references"].append(
            {
                "pubmed_ids": pubmed_ids,
                "field_code": row["field_code"],
                "field_name": row["field_name"],
                "value_text": row["value_text"],
                "value_raw": row["value_raw"],
                "reference_tokens": row["reference_tokens"],
                "qualifiers": row["qualifiers"],
            }
        )

        for pubmed_id in pubmed_ids:
            stats[pubmed_id] += 1

    payload = {
        "database": str(db_path),
        "enzyme_count": len(aggregated),
        "reference_records": sum(len(item["references"]) for item in aggregated.values()),
        "unique_pubmed_ids": len(stats),
        "top_pubmed_ids": sorted(
            (
                {"pubmed_id": pid, "occurrences": count}
                for pid, count in stats.items()
            ),
            key=lambda item: item["occurrences"],
            reverse=True,
        )[:25],
        "enzymes": list(aggregated.values()),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export PubMed-linked references from the BRENDA SQLite mirror",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/pubmed_references.json"),
        help="Destination JSON file",
    )
    parser.add_argument(
        "--database",
        type=str,
        help="Override path to the SQLite database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional row limit for debugging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = _resolve_database_path(args.database)
    export_pubmed_references(db_path=db_path, output_path=args.output.resolve(), limit=args.limit)


if __name__ == "__main__":
    main()
