"""Compute ontology coverage metrics from the BRENDA SQLite mirror."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

UNIPROT_RE = re.compile(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]{5})\b")
PUBMED_RE = re.compile(r"pubmed:(\d+)", re.IGNORECASE)
CHEBI_RE = re.compile(r"\bchebi:\d+\b", re.IGNORECASE)
PUBCHEM_RE = re.compile(r"\bpubchem:\d+\b", re.IGNORECASE)
INCHIKEY_RE = re.compile(r"\b[A-Z]{14}-[A-Z]{10}-[A-Z]\b")
TAXID_RE = re.compile(r"\btaxid[:=]\s*\d+\b", re.IGNORECASE)

LIGAND_CATEGORIES = {
    "inhibitor",
    "cofactor",
    "activating_compound",
    "metals_ions",
    "substrates_products",
    "natural_substrates_products",
}


@dataclass
class ScorecardResult:
    counts: Dict[str, Any]
    coverage: Dict[str, Any]
    distinct: Dict[str, Any]
    present_ontologies: List[str]


def _iter_column(
    conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = (), batch: int = 5000
) -> Iterator[str]:
    cursor = conn.execute(query, params)
    while True:
        rows = cursor.fetchmany(batch)
        if not rows:
            break
        for row in rows:
            if row[0] is None:
                continue
            yield str(row[0])


def _count_rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> int:
    return int(conn.execute(query, params).fetchone()[0])


def _coverage_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def compute_scorecard(db_path: Path) -> ScorecardResult:
    db_path = db_path.expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    conn = sqlite3.connect(db_path)
    try:
        total_proteins = _count_rows(conn, "SELECT COUNT(*) FROM proteins")
        total_facts = _count_rows(conn, "SELECT COUNT(*) FROM enzyme_facts")
        total_text = _count_rows(conn, "SELECT COUNT(*) FROM text_facts")

        uniprot_hits = 0
        for protein_id in _iter_column(conn, "SELECT protein_id FROM proteins"):
            if UNIPROT_RE.search(protein_id):
                uniprot_hits += 1

        taxid_hits = 0
        for organism in _iter_column(conn, "SELECT organism FROM proteins WHERE organism IS NOT NULL"):
            if TAXID_RE.search(organism):
                taxid_hits += 1

        ligand_total = 0
        ligand_normalized = 0
        for value in _iter_column(
            conn,
            """
            SELECT value
            FROM enzyme_facts
            WHERE category IN ({})
              AND value IS NOT NULL
            """.format(
                ",".join("?" for _ in LIGAND_CATEGORIES)
            ),
            tuple(sorted(LIGAND_CATEGORIES)),
        ):
            ligand_total += 1
            if (
                CHEBI_RE.search(value)
                or PUBCHEM_RE.search(value)
                or INCHIKEY_RE.search(value)
            ):
                ligand_normalized += 1

        reference_total = _count_rows(
            conn,
            "SELECT COUNT(*) FROM text_facts WHERE field_code = 'RF'",
        )
        reference_pubmed = 0
        for ref in _iter_column(
            conn,
            "SELECT value_text FROM text_facts WHERE field_code = 'RF'",
        ):
            if PUBMED_RE.search(ref):
                reference_pubmed += 1

        distinct_categories = _count_rows(
            conn, "SELECT COUNT(DISTINCT category) FROM enzyme_facts"
        )
        distinct_text_fields = _count_rows(
            conn, "SELECT COUNT(DISTINCT field_code) FROM text_facts"
        )

        present_ontologies = []
        if uniprot_hits:
            present_ontologies.append("uniprot_accession")
        if taxid_hits:
            present_ontologies.append("ncbi_taxonomy")
        if ligand_normalized:
            present_ontologies.append("chebi_pubchem_inchikey")
        if reference_pubmed:
            present_ontologies.append("pubmed")

        counts = {
            "proteins": total_proteins,
            "enzyme_facts": total_facts,
            "text_facts": total_text,
            "uniprot_hits": uniprot_hits,
            "taxid_hits": taxid_hits,
            "ligand_total": ligand_total,
            "ligand_normalized": ligand_normalized,
            "reference_total": reference_total,
            "reference_pubmed": reference_pubmed,
        }

        coverage = {
            "protein_uniprot_coverage": _coverage_ratio(uniprot_hits, total_proteins),
            "protein_taxid_coverage": _coverage_ratio(taxid_hits, total_proteins),
            "ligand_normalized_coverage": _coverage_ratio(
                ligand_normalized, ligand_total
            ),
            "reference_pubmed_coverage": _coverage_ratio(
                reference_pubmed, reference_total
            ),
        }

        distinct = {
            "distinct_fact_categories": distinct_categories,
            "distinct_text_fields": distinct_text_fields,
        }

        return ScorecardResult(
            counts=counts,
            coverage=coverage,
            distinct=distinct,
            present_ontologies=present_ontologies,
        )
    finally:
        conn.close()


def _as_markdown(result: ScorecardResult) -> str:
    lines = ["# Ontology Coverage Scorecard", ""]
    lines.append("## Counts")
    for key, value in result.counts.items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Coverage")
    for key, value in result.coverage.items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Distinct")
    for key, value in result.distinct.items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("## Present Ontologies")
    if result.present_ontologies:
        for name in result.present_ontologies:
            lines.append(f"- {name}")
    else:
        lines.append("- none_detected")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute ontology coverage metrics for the BRENDA SQLite mirror."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/processed/brenda.db"),
        help="Path to the SQLite database.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    result = compute_scorecard(args.database)
    payload = {
        "counts": result.counts,
        "coverage": result.coverage,
        "distinct": result.distinct,
        "present_ontologies": result.present_ontologies,
    }

    print(json.dumps(payload, indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(_as_markdown(result))


if __name__ == "__main__":
    main()
