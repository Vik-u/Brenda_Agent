"""Analytical summaries for the ingested BRENDA SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from tabulate import tabulate

DB_PATH = Path("data/processed/brenda.db")


def load_rows(query: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def summarize() -> Dict[str, Any]:
    totals = load_rows(
        """
        SELECT
            (SELECT COUNT(*) FROM enzymes) AS enzyme_count,
            (SELECT SUM(protein_count) FROM enzymes) AS protein_annotations,
            (SELECT COUNT(*) FROM proteins) AS protein_rows,
            (SELECT COUNT(*) FROM enzyme_facts) AS fact_rows,
            (SELECT COUNT(*) FROM text_facts) AS text_rows
        """
    )[0]

    top_categories = load_rows(
        """
        SELECT category, COUNT(*) AS records
        FROM enzyme_facts
        GROUP BY category
        ORDER BY records DESC
        LIMIT 15
        """
    )

    top_inhibitors = load_rows(
        """
        SELECT value, COUNT(*) AS hits
        FROM enzyme_facts
        WHERE category = 'inhibitor' AND value IS NOT NULL
        GROUP BY value
        ORDER BY hits DESC
        LIMIT 10
        """
    )

    top_cofactors = load_rows(
        """
        SELECT value, COUNT(*) AS hits
        FROM enzyme_facts
        WHERE category = 'cofactor' AND value IS NOT NULL
        GROUP BY value
        ORDER BY hits DESC
        LIMIT 10
        """
    )

    top_organisms = load_rows(
        """
        SELECT organism, COUNT(*) AS proteins
        FROM proteins
        WHERE organism IS NOT NULL AND organism != ''
        GROUP BY organism
        ORDER BY proteins DESC
        LIMIT 10
        """
    )

    kinetics = load_rows(
        """
        SELECT
            category,
            COUNT(*) AS records,
            MIN(value_numeric_low) AS min_value,
            AVG(value_numeric_low) AS avg_value,
            MAX(value_numeric_high) AS max_value
        FROM enzyme_facts
        WHERE category IN ('km_value', 'turnover_number', 'kcat_km_value', 'specific_activity')
            AND value_numeric_low IS NOT NULL
        GROUP BY category
        """
    )

    text_fields = load_rows(
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

    return {
        "totals": dict(totals),
        "top_categories": [dict(row) for row in top_categories],
        "top_inhibitors": [dict(row) for row in top_inhibitors],
        "top_cofactors": [dict(row) for row in top_cofactors],
        "top_organisms": [dict(row) for row in top_organisms],
        "kinetics": [dict(row) for row in kinetics],
        "text_fields": [dict(row) for row in text_fields],
    }


def write_report(report_path: Path) -> None:
    summary = summarize()

    lines = ["# BRENDA Database Snapshot", ""]

    totals = summary["totals"]
    lines.append("## Totals")
    lines.append(
        tabulate(
            [
                ("Enzymes", totals["enzyme_count"]),
                ("Proteins (distinct annotations)", totals["protein_annotations"]),
                ("Protein rows", totals["protein_rows"]),
                ("Structured facts", totals["fact_rows"]),
                ("Text facts", totals["text_rows"]),
            ],
            headers=["Metric", "Value"],
        )
    )
    lines.append("")

    lines.append("## Most Populated Fact Categories")
    lines.append(
        tabulate(
            [(row["category"], row["records"]) for row in summary["top_categories"]],
            headers=["Category", "Records"],
        )
    )
    lines.append("")

    lines.append("## Frequent Inhibitors")
    lines.append(
        tabulate(
            [(row["value"], row["hits"]) for row in summary["top_inhibitors"]],
            headers=["Inhibitor", "Hits"],
        )
    )
    lines.append("")

    lines.append("## Frequent Cofactors")
    lines.append(
        tabulate(
            [(row["value"], row["hits"]) for row in summary["top_cofactors"]],
            headers=["Cofactor", "Hits"],
        )
    )
    lines.append("")

    lines.append("## Organisms With Most Protein Entries")
    lines.append(
        tabulate(
            [(row["organism"], row["proteins"]) for row in summary["top_organisms"]],
            headers=["Organism", "Protein Records"],
        )
    )
    lines.append("")

    lines.append("## Kinetic Parameter Ranges")
    lines.append(
        tabulate(
            [
                (
                    row["category"],
                    row["records"],
                    row["min_value"],
                    row["avg_value"],
                    row["max_value"],
                )
                for row in summary["kinetics"]
            ],
            headers=["Parameter", "Records", "Min", "Average", "Max"],
            floatfmt=("", "", ".3g", ".3g", ".3g"),
        )
    )
    lines.append("")

    lines.append("## Text Field Coverage")
    lines.append(
        tabulate(
            [
                (
                    row["field_code"],
                    row["field_name"],
                    row["records"],
                )
                for row in summary["text_fields"]
            ],
            headers=["Field", "Label", "Records"],
        )
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate markdown report from BRENDA DB")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/brenda_analysis.md"),
        help="Output markdown file",
    )
    args = parser.parse_args()

    write_report(args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
