#!/usr/bin/env python
"""Generate consolidated and per-category statistics for the BRENDA dataset."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DB_PATH = Path("data/processed/brenda.db")
DEFAULT_DOI_PATH = Path("artifacts/doi_links.txt")
DEFAULT_PUBMED_ARTICLES_PATH = Path("artifacts/pubmed_articles.json")


def _fact_category_details(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    base_rows = conn.execute(
        """
        SELECT
            category,
            COUNT(*) AS records,
            COUNT(DISTINCT ec_number) AS ec_coverage,
            SUM(CASE WHEN value_numeric_low IS NOT NULL THEN 1 ELSE 0 END) AS numeric_records,
            SUM(CASE WHEN reference_ids IS NOT NULL AND reference_ids <> '' THEN 1 ELSE 0 END) AS reference_records,
            SUM(CASE WHEN proteins IS NOT NULL AND proteins <> '' THEN 1 ELSE 0 END) AS protein_records,
            MIN(value_numeric_low) AS min_numeric,
            AVG(value_numeric_low) AS avg_numeric,
            MAX(value_numeric_high) AS max_numeric
        FROM enzyme_facts
        GROUP BY category
        ORDER BY records DESC
        """
    )
    details: List[Dict[str, Any]] = []
    for row in base_rows:
        category = row["category"]
        record_count = row["records"] or 0
        detail: Dict[str, Any] = {key: row[key] for key in row.keys()}
        detail["numeric_fraction"] = (
            detail["numeric_records"] / record_count if record_count else 0.0
        )
        detail["reference_fraction"] = (
            detail["reference_records"] / record_count if record_count else 0.0
        )
        detail["protein_fraction"] = (
            detail["protein_records"] / record_count if record_count else 0.0
        )
        unit_stats = conn.execute(
            """
            SELECT unit, COUNT(*) AS records
            FROM enzyme_facts
            WHERE category = ? AND unit IS NOT NULL AND unit <> ''
            GROUP BY unit
            ORDER BY records DESC
            LIMIT 3
            """,
            (category,),
        ).fetchall()
        detail["distinct_units"] = conn.execute(
            """
            SELECT COUNT(DISTINCT unit) AS cnt
            FROM enzyme_facts
            WHERE category = ? AND unit IS NOT NULL AND unit <> ''
            """,
            (category,),
        ).fetchone()["cnt"]
        detail["top_units"] = [
            {"unit": unit_row["unit"], "records": unit_row["records"]}
            for unit_row in unit_stats
        ]
        context_rows = conn.execute(
            """
            SELECT context, COUNT(*) AS records
            FROM enzyme_facts
            WHERE category = ? AND context IS NOT NULL AND context <> ''
            GROUP BY context
            ORDER BY records DESC
            LIMIT 3
            """,
            (category,),
        ).fetchall()
        detail["top_contexts"] = [
            {"context": ctx_row["context"], "records": ctx_row["records"]}
            for ctx_row in context_rows
        ]
        details.append(detail)
    return details


def _text_field_details(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    base_rows = conn.execute(
        """
        SELECT
            field_code,
            COALESCE(NULLIF(field_name, ''), field_code) AS field_name,
            COUNT(*) AS records,
            COUNT(DISTINCT ec_number) AS ec_coverage,
            SUM(CASE WHEN reference_tokens IS NOT NULL AND reference_tokens <> '' THEN 1 ELSE 0 END) AS reference_records,
            SUM(CASE WHEN protein_tokens IS NOT NULL AND protein_tokens <> '' THEN 1 ELSE 0 END) AS protein_records,
            SUM(CASE WHEN qualifiers IS NOT NULL AND qualifiers <> '' THEN 1 ELSE 0 END) AS qualifier_records
        FROM text_facts
        GROUP BY field_code, field_name
        ORDER BY records DESC
        """
    )
    details: List[Dict[str, Any]] = []
    for row in base_rows:
        field_code = row["field_code"]
        record_count = row["records"] or 0
        detail: Dict[str, Any] = {key: row[key] for key in row.keys()}
        detail["reference_fraction"] = (
            detail["reference_records"] / record_count if record_count else 0.0
        )
        detail["protein_fraction"] = (
            detail["protein_records"] / record_count if record_count else 0.0
        )
        detail["qualifier_fraction"] = (
            detail["qualifier_records"] / record_count if record_count else 0.0
        )
        sample_refs = conn.execute(
            """
            SELECT value_text AS sample_text
            FROM text_facts
            WHERE field_code = ? AND value_text IS NOT NULL AND value_text <> ''
            LIMIT 3
            """,
            (field_code,),
        ).fetchall()
        detail["sample_values"] = [entry["sample_text"] for entry in sample_refs]
        details.append(detail)
    return details


def _entity_linkage(conn: sqlite3.Connection) -> Dict[str, Any]:
    coverage = conn.execute(
        """
        SELECT
            SUM(CASE WHEN proteins_cnt > 0 THEN 1 ELSE 0 END) AS enzymes_with_proteins,
            SUM(CASE WHEN facts_cnt > 0 THEN 1 ELSE 0 END) AS enzymes_with_facts,
            SUM(CASE WHEN text_cnt > 0 THEN 1 ELSE 0 END) AS enzymes_with_text,
            SUM(CASE WHEN proteins_cnt > 0 AND facts_cnt > 0 AND text_cnt > 0 THEN 1 ELSE 0 END) AS enzymes_with_all,
            SUM(CASE WHEN proteins_cnt > 0 AND facts_cnt > 0 AND text_cnt = 0 THEN 1 ELSE 0 END) AS proteins_and_facts,
            SUM(CASE WHEN proteins_cnt > 0 AND facts_cnt = 0 AND text_cnt > 0 THEN 1 ELSE 0 END) AS proteins_and_text,
            SUM(CASE WHEN proteins_cnt = 0 AND facts_cnt > 0 AND text_cnt > 0 THEN 1 ELSE 0 END) AS facts_and_text,
            SUM(CASE WHEN proteins_cnt > 0 AND facts_cnt = 0 AND text_cnt = 0 THEN 1 ELSE 0 END) AS proteins_only,
            SUM(CASE WHEN proteins_cnt = 0 AND facts_cnt > 0 AND text_cnt = 0 THEN 1 ELSE 0 END) AS facts_only,
            SUM(CASE WHEN proteins_cnt = 0 AND facts_cnt = 0 AND text_cnt > 0 THEN 1 ELSE 0 END) AS text_only
        FROM (
            SELECT
                e.ec_number,
                COALESCE(p.protein_cnt, 0) AS proteins_cnt,
                COALESCE(f.fact_cnt, 0) AS facts_cnt,
                COALESCE(t.text_cnt, 0) AS text_cnt
            FROM enzymes AS e
            LEFT JOIN (
                SELECT ec_number, COUNT(*) AS protein_cnt FROM proteins GROUP BY ec_number
            ) AS p USING (ec_number)
            LEFT JOIN (
                SELECT ec_number, COUNT(*) AS fact_cnt FROM enzyme_facts GROUP BY ec_number
            ) AS f USING (ec_number)
            LEFT JOIN (
                SELECT ec_number, COUNT(*) AS text_cnt FROM text_facts GROUP BY ec_number
            ) AS t USING (ec_number)
        ) AS coverage_counts
        """
    ).fetchone()

    averages = conn.execute(
        """
        SELECT
            AVG(proteins_cnt) AS avg_proteins,
            AVG(facts_cnt) AS avg_facts,
            AVG(text_cnt) AS avg_text
        FROM (
            SELECT
                e.ec_number,
                COALESCE(p.protein_cnt, 0) AS proteins_cnt,
                COALESCE(f.fact_cnt, 0) AS facts_cnt,
                COALESCE(t.text_cnt, 0) AS text_cnt
            FROM enzymes AS e
            LEFT JOIN (
                SELECT ec_number, COUNT(*) AS protein_cnt FROM proteins GROUP BY ec_number
            ) AS p USING (ec_number)
            LEFT JOIN (
                SELECT ec_number, COUNT(*) AS fact_cnt FROM enzyme_facts GROUP BY ec_number
            ) AS f USING (ec_number)
            LEFT JOIN (
                SELECT ec_number, COUNT(*) AS text_cnt FROM text_facts GROUP BY ec_number
            ) AS t USING (ec_number)
        ) AS coverage_counts
        """
    ).fetchone()

    linkage = {key: coverage[key] for key in coverage.keys()}
    linkage.update({key: averages[key] for key in averages.keys()})
    return linkage


def load_db_stats(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        stats: Dict[str, Any] = {}

        def fetchone(query: str) -> sqlite3.Row:
            return conn.execute(query).fetchone()

        stats["totals"] = {
            "enzymes": fetchone("SELECT COUNT(*) AS c FROM enzymes")["c"],
            "proteins": fetchone("SELECT COUNT(*) AS c FROM proteins")["c"],
            "enzyme_facts": fetchone("SELECT COUNT(*) AS c FROM enzyme_facts")["c"],
            "text_facts": fetchone("SELECT COUNT(*) AS c FROM text_facts")["c"],
        }

        protein_ec_total = fetchone(
            "SELECT COUNT(DISTINCT ec_number) AS c FROM proteins"
        )["c"]
        protein_ec_matched = fetchone(
            """
            SELECT COUNT(*) AS c FROM (
                SELECT p.ec_number
                FROM proteins AS p
                INNER JOIN enzymes AS e ON e.ec_number = p.ec_number
                GROUP BY p.ec_number
            )
            """
        )["c"]

        fact_ec_total = fetchone(
            "SELECT COUNT(DISTINCT ec_number) AS c FROM enzyme_facts"
        )["c"]
        fact_ec_matched = fetchone(
            """
            SELECT COUNT(*) AS c FROM (
                SELECT f.ec_number
                FROM enzyme_facts AS f
                INNER JOIN enzymes AS e ON e.ec_number = f.ec_number
                GROUP BY f.ec_number
            )
            """
        )["c"]

        text_ec_total = fetchone(
            "SELECT COUNT(DISTINCT ec_number) AS c FROM text_facts"
        )["c"]
        text_ec_matched = fetchone(
            """
            SELECT COUNT(*) AS c FROM (
                SELECT tf.ec_number
                FROM text_facts AS tf
                INNER JOIN enzymes AS e ON e.ec_number = tf.ec_number
                GROUP BY tf.ec_number
            )
            """
        )["c"]

        stats["coverage"] = {
            "enzyme_total": stats["totals"]["enzymes"],
            "enzymes_with_inhibitors": fetchone(
                "SELECT COUNT(*) AS c FROM enzymes WHERE inhibitor_count > 0"
            )["c"],
            "protein_ec_total": protein_ec_total,
            "protein_ec_matched": protein_ec_matched,
            "fact_ec_total": fact_ec_total,
            "fact_ec_matched": fact_ec_matched,
            "text_ec_total": text_ec_total,
            "text_ec_matched": text_ec_matched,
        }

        stats["protein_summary"] = dict(
            fetchone(
                """
                SELECT
                    AVG(protein_count) AS avg_per_enzyme,
                    MAX(protein_count) AS max_per_enzyme
                FROM enzymes
                """
            )
        )

        stats["fact_links"] = {
            "facts_with_numeric_values": fetchone(
                "SELECT COUNT(*) AS c FROM enzyme_facts WHERE value_numeric_low IS NOT NULL"
            )["c"],
            "facts_with_references": fetchone(
                "SELECT COUNT(*) AS c FROM enzyme_facts WHERE reference_ids IS NOT NULL AND reference_ids <> ''"
            )["c"],
            "facts_with_protein_tokens": fetchone(
                "SELECT COUNT(*) AS c FROM enzyme_facts WHERE proteins IS NOT NULL AND proteins <> ''"
            )["c"],
        }

        stats["top_fact_categories"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT category, COUNT(*) AS records
                FROM enzyme_facts
                GROUP BY category
                ORDER BY records DESC
                LIMIT 15
                """
            )
        ]

        stats["top_text_fields"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    field_code,
                    COALESCE(NULLIF(field_name, ''), field_code) AS field_name,
                    COUNT(*) AS records
                FROM text_facts
                GROUP BY field_code, field_name
                ORDER BY records DESC
                LIMIT 15
                """
            )
        ]

        stats["fact_category_details"] = _fact_category_details(conn)
        stats["text_field_details"] = _text_field_details(conn)
        stats["entity_linkage"] = _entity_linkage(conn)

        stats["top_enzymes_by_proteins"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT ec_number, protein_count
                FROM enzymes
                ORDER BY protein_count DESC
                LIMIT 10
                """
            )
        ]

        stats["top_enzymes_by_fact_volume"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT ec_number, COUNT(*) AS records
                FROM enzyme_facts
                GROUP BY ec_number
                ORDER BY records DESC
                LIMIT 10
                """
            )
        ]

        return stats
    finally:
        conn.close()


def load_doi_stats(doi_path: Path) -> Dict[str, Any]:
    if not doi_path.exists():
        return {}
    dois = [line.strip() for line in doi_path.read_text().splitlines() if line.strip()]
    domains = Counter()
    for entry in dois:
        if "//" not in entry:
            continue
        host = entry.split("//", 1)[1].split("/", 1)[0].lower()
        domains[host] += 1
    return {
        "total_doi_links": len(dois),
        "top_domains": domains.most_common(5),
    }


def load_pubmed_stats(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    articles = payload.get("articles", [])
    ec_counts = [len(item.get("linked_ec_numbers", [])) for item in articles]
    ec_counts_sorted = sorted(ec_counts)
    median_ec = ec_counts_sorted[len(ec_counts_sorted) // 2] if ec_counts_sorted else 0
    return {
        "total_articles": len(articles),
        "articles_with_doi": sum(1 for item in articles if item.get("doi")),
        "unique_pubmed_ids": len({item.get("pubmed_id") for item in articles}),
        "max_ec_per_article": max(ec_counts_sorted) if ec_counts_sorted else 0,
        "median_ec_per_article": median_ec,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report BRENDA database statistics")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--doi-links", type=Path, default=DEFAULT_DOI_PATH)
    parser.add_argument("--pubmed-articles", type=Path, default=DEFAULT_PUBMED_ARTICLES_PATH)
    parser.add_argument("--output", type=Path, help="Optional path to write JSON report")
    args = parser.parse_args()

    db_path = args.database.expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found at {db_path}")

    report: Dict[str, Any] = {
        "database": str(db_path),
        "db_stats": load_db_stats(db_path),
        "doi_stats": load_doi_stats(args.doi_links),
        "pubmed_stats": load_pubmed_stats(args.pubmed_articles),
    }

    text = json.dumps(report, indent=2)
    print(text)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)


if __name__ == "__main__":
    main()
