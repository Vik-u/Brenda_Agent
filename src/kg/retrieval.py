"""Read-only utilities for retrieving nodes and edges from the KG store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class KGNeighbor:
    source_id: str
    relation: str
    target_id: str
    target_type: Optional[str]
    target_label: Optional[str]
    target_properties: Dict[str, Any]


class KGReader:
    def __init__(self, db_path: Path) -> None:
        db_path = db_path.expanduser().resolve()
        if not db_path.exists():
            raise FileNotFoundError(db_path)
        self._db_path = db_path

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT node_id, node_type, label, properties_json
                FROM kg_nodes
                WHERE node_id = ?
                """,
                (node_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "node_id": row["node_id"],
            "node_type": row["node_type"],
            "label": row["label"],
            "properties": _load_properties(row["properties_json"]),
        }

    def neighbors(
        self, node_id: str, *, relation: Optional[str] = None, limit: int = 200
    ) -> List[KGNeighbor]:
        query = (
            "SELECT e.source_id, e.relation, e.target_id, n.node_type, n.label, n.properties_json "
            "FROM kg_edges e "
            "LEFT JOIN kg_nodes n ON e.target_id = n.node_id "
            "WHERE e.source_id = ?"
        )
        params: List[Any] = [node_id]
        if relation:
            query += " AND e.relation = ?"
            params.append(relation)
        query += " ORDER BY e.relation, e.id LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(params)).fetchall()

        return [
            KGNeighbor(
                source_id=row["source_id"],
                relation=row["relation"],
                target_id=row["target_id"],
                target_type=row["node_type"],
                target_label=row["label"],
                target_properties=_load_properties(row["properties_json"]),
            )
            for row in rows
        ]


def _load_properties(payload: Optional[str]) -> Dict[str, Any]:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}
