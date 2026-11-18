"""Build an ontology-oriented knowledge graph from the BRENDA SQLite mirror."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

BATCH_SIZE = 1000

LIGAND_CATEGORIES = {
    "inhibitor",
    "cofactor",
    "activating_compound",
    "metals_ions",
    "substrates_products",
    "natural_substrates_products",
}

KINETIC_CATEGORIES = {
    "km_value",
    "turnover_number",
    "kcat_km_value",
    "ki_value",
    "ic50_value",
    "specific_activity",
}


@dataclass
class KGStats:
    nodes: int
    edges: int


def build_kg(
    source_db: Path,
    target_db: Path,
    *,
    include_text: bool = True,
    limit: Optional[int] = None,
) -> KGStats:
    source_db = source_db.expanduser().resolve()
    target_db = target_db.expanduser().resolve()
    if not source_db.exists():
        raise FileNotFoundError(source_db)

    target_db.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(source_db)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(target_db)
    try:
        _init_schema(target)
        node_count = 0
        edge_count = 0

        enzyme_rows = _iter_rows(
            source,
            "SELECT ec_number, recommended_name, systematic_name FROM enzymes",
            limit=limit,
        )
        for row in enzyme_rows:
            node_id = f"enzyme:{row['ec_number']}"
            label = row["recommended_name"] or row["systematic_name"]
            node_count += _insert_node(
                target,
                node_id=node_id,
                node_type="enzyme",
                label=label,
                properties={"ec_number": row["ec_number"]},
            )

        protein_rows = _iter_rows(
            source,
            "SELECT id, ec_number, protein_id, organism FROM proteins",
            limit=limit,
        )
        edge_buffer: List[Tuple[str, str, str, str]] = []
        for row in protein_rows:
            protein_node = f"protein:{row['id']}"
            node_count += _insert_node(
                target,
                node_id=protein_node,
                node_type="protein",
                label=row["protein_id"],
                properties={
                    "protein_id": row["protein_id"],
                    "source_id": row["id"],
                },
            )
            edge_buffer.append(
                (
                    f"enzyme:{row['ec_number']}",
                    "has_protein",
                    protein_node,
                    json.dumps({}, ensure_ascii=True),
                )
            )

            if row["organism"]:
                organism_key = _slugify(row["organism"])
                organism_node = f"organism:{organism_key}"
                node_count += _insert_node(
                    target,
                    node_id=organism_node,
                    node_type="organism",
                    label=row["organism"],
                    properties={"organism": row["organism"]},
                )
                edge_buffer.append(
                    (
                        protein_node,
                        "from_organism",
                        organism_node,
                        json.dumps({}, ensure_ascii=True),
                    )
                )

            edge_count = _flush_edges(target, edge_buffer, edge_count)

        fact_rows = _iter_rows(
            source,
            """
            SELECT id, ec_number, category, value, value_numeric_low, value_numeric_high, unit, context
            FROM enzyme_facts
            """,
            limit=limit,
        )
        for row in fact_rows:
            category = row["category"]
            ec_node = f"enzyme:{row['ec_number']}"
            if category in LIGAND_CATEGORIES and row["value"]:
                ligand_key = _slugify(row["value"])
                ligand_node = f"compound:{ligand_key}"
                node_count += _insert_node(
                    target,
                    node_id=ligand_node,
                    node_type="compound",
                    label=row["value"],
                    properties={"value": row["value"]},
                )
                edge_buffer.append(
                    (
                        ec_node,
                        f"has_{category}",
                        ligand_node,
                        json.dumps({}, ensure_ascii=True),
                    )
                )
            elif category in KINETIC_CATEGORIES:
                kinetic_node = f"kinetic:{row['id']}"
                node_count += _insert_node(
                    target,
                    node_id=kinetic_node,
                    node_type="kinetic_measurement",
                    label=category,
                    properties={
                        "category": category,
                        "value": row["value"],
                        "low": row["value_numeric_low"],
                        "high": row["value_numeric_high"],
                        "unit": row["unit"],
                        "context": row["context"],
                    },
                )
                edge_buffer.append(
                    (
                        ec_node,
                        "has_kinetic_measurement",
                        kinetic_node,
                        json.dumps({"category": category}, ensure_ascii=True),
                    )
                )
            edge_count = _flush_edges(target, edge_buffer, edge_count)

        if include_text:
            text_rows = _iter_rows(
                source,
                """
                SELECT id, ec_number, field_code, field_name, value_raw, value_text, reference_tokens
                FROM text_facts
                """,
                limit=limit,
            )
            for row in text_rows:
                text_node = f"text:{row['id']}"
                node_count += _insert_node(
                    target,
                    node_id=text_node,
                    node_type="text_fact",
                    label=row["field_code"],
                    properties={
                        "field_code": row["field_code"],
                        "field_name": row["field_name"],
                        "value_raw": row["value_raw"],
                        "value_text": row["value_text"],
                    },
                )
                edge_buffer.append(
                    (
                        f"enzyme:{row['ec_number']}",
                        "has_text_fact",
                        text_node,
                        json.dumps({}, ensure_ascii=True),
                    )
                )

                if row["reference_tokens"]:
                    for ref in str(row["reference_tokens"]).split(";"):
                        ref_value = ref.strip()
                        if not ref_value:
                            continue
                        ref_key = _slugify(ref_value)
                        ref_node = f"reference:{ref_key}"
                        node_count += _insert_node(
                            target,
                            node_id=ref_node,
                            node_type="reference",
                            label=ref_value,
                            properties={"reference": ref_value},
                        )
                        edge_buffer.append(
                            (
                                text_node,
                                "cites_reference",
                                ref_node,
                                json.dumps({}, ensure_ascii=True),
                            )
                        )
                edge_count = _flush_edges(target, edge_buffer, edge_count)

        edge_count = _flush_edges(target, edge_buffer, edge_count, force=True)
        return KGStats(nodes=node_count, edges=edge_count)
    finally:
        source.close()
        target.commit()
        target.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS kg_nodes (
            node_id TEXT PRIMARY KEY,
            node_type TEXT NOT NULL,
            label TEXT,
            properties_json TEXT
        );

        CREATE TABLE IF NOT EXISTS kg_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            target_id TEXT NOT NULL,
            properties_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_kg_nodes_type ON kg_nodes (node_type);
        CREATE INDEX IF NOT EXISTS idx_kg_edges_source ON kg_edges (source_id);
        CREATE INDEX IF NOT EXISTS idx_kg_edges_relation ON kg_edges (relation);
        CREATE INDEX IF NOT EXISTS idx_kg_edges_target ON kg_edges (target_id);
        """
    )


def _insert_node(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    node_type: str,
    label: Optional[str],
    properties: Dict[str, Any],
) -> int:
    payload = json.dumps(properties, ensure_ascii=True)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO kg_nodes (node_id, node_type, label, properties_json)
        VALUES (?, ?, ?, ?)
        """,
        (node_id, node_type, label, payload),
    )
    return 1 if cursor.rowcount else 0


def _flush_edges(
    conn: sqlite3.Connection,
    buffer: List[Tuple[str, str, str, str]],
    count: int,
    *,
    force: bool = False,
) -> int:
    if not buffer:
        return count
    if len(buffer) < BATCH_SIZE and not force:
        return count
    conn.executemany(
        """
        INSERT INTO kg_edges (source_id, relation, target_id, properties_json)
        VALUES (?, ?, ?, ?)
        """,
        buffer,
    )
    count += len(buffer)
    buffer.clear()
    return count


def _iter_rows(
    conn: sqlite3.Connection, query: str, *, limit: Optional[int] = None, batch: int = 5000
) -> Iterator[sqlite3.Row]:
    if limit is not None:
        query = f"{query} LIMIT {int(limit)}"
    cursor = conn.execute(query)
    while True:
        rows = cursor.fetchmany(batch)
        if not rows:
            break
        for row in rows:
            yield row


def _slugify(value: str, *, max_len: int = 64) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        normalized = "unknown"
    if len(normalized) > max_len:
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
        normalized = f"{normalized[: max_len - 9]}_{digest}"
    return normalized
