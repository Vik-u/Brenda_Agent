"""Researcher agent responsible for interacting with BRENDA and knowledge sources."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.agents.base import AgentContext, BaseAgent
from src.services.brenda_client import BrendaClient
from src.core.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResearcherAgent(BaseAgent):
    _DEFAULT_CANDIDATE_LIMIT = 3

    def __init__(self) -> None:
        super().__init__(
            name="researcher",
            description=(
                "Investigative agent that discovers enzyme knowledge for the rest of the crew. "
                "It accepts EC numbers, common enzyme names, protein identifiers, or free-form "
                "search strings, resolves them to candidate EC entries, and then retrieves the "
                "richest structured payload available from BRENDA or the local SQLite mirror."
            ),
        )
        self._client = BrendaClient()
        settings = get_settings()
        self._local_db_path = self._resolve_local_db_path(settings)

    async def handle_task(self, context: AgentContext) -> Dict[str, Any]:
        task = context.payload or {}
        organism = task.get("organism")
        ec_number = task.get("ec_number")

        resolved_ec_numbers: List[str] = []
        if ec_number:
            resolved_ec_numbers = [ec_number]
        else:
            resolved_ec_numbers = self._resolve_ec_numbers(task, organism=organism)
            if not resolved_ec_numbers:
                raise ValueError(
                    "Researcher agent could not determine an EC number from the provided query. "
                    "Supply `ec_number` directly or include properties such as `query`, "
                    "`protein_id`, or `uniprot_id`."
                )
            ec_number = resolved_ec_numbers[0]

        brenda_data = await self._fetch_with_fallback(ec_number=ec_number, organism=organism)

        return {
            "ec_number": ec_number,
            "resolved_ec_numbers": resolved_ec_numbers,
            "organism": organism,
            "search_terms": self._extract_search_terms(task),
            "brenda_data": brenda_data,
        }

    async def _fetch_with_fallback(
        self, *, ec_number: str, organism: Optional[str]
    ) -> Dict[str, Any]:
        try:
            payload = await self._client.fetch_enzyme_data(ec_number=ec_number, organism=organism)
            if payload.get("data"):
                return payload
            logger.warning(
                "researcher.empty_remote_payload",
                ec_number=ec_number,
                organism=organism,
            )
        except Exception as exc:  # pragma: no cover - depends on remote availability
            logger.warning(
                "researcher.remote_failed_falling_back",
                ec_number=ec_number,
                organism=organism,
                error=str(exc),
            )

        return self._load_local_records(ec_number=ec_number, organism=organism)

    def _extract_search_terms(self, task: Dict[str, Any]) -> Dict[str, Any]:
        keys = ("ec_number", "query", "name", "enzyme_name", "protein_id", "uniprot_id", "enzyme_id")
        return {key: task[key] for key in keys if task.get(key)}

    def _resolve_local_db_path(self, settings) -> Optional[Path]:
        candidates: List[Optional[str]] = [
            settings.services.database.url,
            getattr(settings.chatbot, "database_path", None),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            if candidate.startswith("sqlite:///"):
                candidate = candidate.replace("sqlite:///", "", 1)
            path = Path(candidate).expanduser().resolve()
            if path.exists():
                return path
        return None

    def _resolve_ec_numbers(
        self, task: Dict[str, Any], *, organism: Optional[str]
    ) -> List[str]:
        if not self._local_db_path:
            logger.warning("researcher.local_db_missing_resolution")
            return []

        query_terms: List[str] = [
            task.get("query") or "",
            task.get("name") or "",
            task.get("enzyme_name") or "",
        ]
        identifiers: List[str] = [
            task.get("protein_id") or "",
            task.get("uniprot_id") or "",
            task.get("enzyme_id") or "",
        ]
        identifiers = [identifier.strip() for identifier in identifiers if identifier]

        conn = sqlite3.connect(self._local_db_path)
        conn.row_factory = sqlite3.Row
        matches: Set[str] = set()
        try:
            like_fragment = (
                f"%{organism.lower()}%" if organism else None
            )

            for identifier in identifiers:
                lower_identifier = identifier.lower()
                rows = conn.execute(
                    "SELECT DISTINCT ec_number FROM proteins WHERE LOWER(protein_id) = ?",
                    (lower_identifier,),
                ).fetchall()
                matches.update(row["ec_number"] for row in rows)

                rows = conn.execute(
                    "SELECT DISTINCT ec_number FROM enzymes WHERE LOWER(enzyme_id) = ?",
                    (lower_identifier,),
                ).fetchall()
                matches.update(row["ec_number"] for row in rows)

            for query in (term.strip() for term in query_terms if term.strip()):
                like_query = f"%{query.lower()}%"
                rows = conn.execute(
                    """
                    SELECT DISTINCT ec_number
                    FROM enzymes
                    WHERE LOWER(recommended_name) LIKE ?
                       OR LOWER(systematic_name) LIKE ?
                       OR LOWER(enzyme_id) LIKE ?
                    """,
                    (like_query, like_query, like_query),
                ).fetchall()
                matches.update(row["ec_number"] for row in rows)

                rows = conn.execute(
                    """
                    SELECT DISTINCT ec_number
                    FROM enzyme_facts
                    WHERE category = 'synonyms'
                      AND LOWER(COALESCE(value, '')) LIKE ?
                    """,
                    (like_query,),
                ).fetchall()
                matches.update(row["ec_number"] for row in rows)

                rows = conn.execute(
                    """
                    SELECT DISTINCT ec_number
                    FROM text_facts
                    WHERE LOWER(COALESCE(value_text, '')) LIKE ?
                       OR LOWER(COALESCE(value_raw, '')) LIKE ?
                    """,
                    (like_query, like_query),
                ).fetchall()
                matches.update(row["ec_number"] for row in rows)

            if organism and matches:
                filtered_matches: Set[str] = set()
                organism_like = f"%{organism.lower()}%"
                rows = conn.execute(
                    """
                    SELECT DISTINCT ec_number
                    FROM proteins
                    WHERE LOWER(COALESCE(organism, '')) LIKE ?
                """,
                    (organism_like,),
                ).fetchall()
                allowed_numbers = {row["ec_number"] for row in rows}
                if allowed_numbers:
                    filtered_matches = matches & allowed_numbers
                    if filtered_matches:
                        matches = filtered_matches
        finally:
            conn.close()

        candidates = sorted(matches)
        limit = int(task.get("max_ec_candidates", self._DEFAULT_CANDIDATE_LIMIT) or self._DEFAULT_CANDIDATE_LIMIT)
        return candidates[:limit] if limit > 0 else candidates

    def _load_local_records(
        self, *, ec_number: str, organism: Optional[str]
    ) -> Dict[str, Any]:
        if not self._local_db_path:
            logger.warning("researcher.local_db_missing", ec_number=ec_number)
            return {"source": "local_sqlite", "data": []}

        conn = sqlite3.connect(self._local_db_path)
        conn.row_factory = sqlite3.Row
        try:
            enzyme_meta = conn.execute(
                "SELECT * FROM enzymes WHERE ec_number = ?",
                (ec_number,),
            ).fetchone()

            fact_query = (
                "SELECT category, value, value_numeric_low, value_numeric_high, unit, context, "
                "comment, proteins, reference_ids, raw_json FROM enzyme_facts WHERE ec_number = ?"
            )
            params: List[Any] = [ec_number]
            if organism:
                like_fragment = f"%{organism.lower()}%"
                fact_query += (
                    " AND (LOWER(COALESCE(context, '')) LIKE ? "
                    "OR LOWER(COALESCE(proteins, '')) LIKE ?)"
                )
                params.extend([like_fragment, like_fragment])

            fact_query += " ORDER BY category, id LIMIT 2000"
            fact_rows = conn.execute(fact_query, tuple(params)).fetchall()

            protein_rows = conn.execute(
                "SELECT protein_id, organism, comment, reference_ids, raw_json FROM proteins WHERE ec_number = ?",
                (ec_number,),
            ).fetchall()

            text_params: List[Any] = [ec_number]
            text_query = (
                "SELECT field_code, field_name, value_text, value_raw, protein_tokens, reference_tokens, qualifiers "
                "FROM text_facts WHERE ec_number = ?"
            )
            if organism:
                like_fragment = f"%{organism.lower()}%"
                text_query += (
                    " AND (LOWER(COALESCE(value_text, '')) LIKE ? "
                    "OR LOWER(COALESCE(reference_tokens, '')) LIKE ?)"
                )
                text_params.extend([like_fragment, like_fragment])
            text_query += " ORDER BY id LIMIT 2000"
            text_rows = conn.execute(text_query, tuple(text_params)).fetchall()
        finally:
            conn.close()

        payload = {
            "source": "local_sqlite",
            "data": [dict(row) for row in fact_rows],
            "record_count": len(fact_rows),
            "metadata": {
                "enzyme": dict(enzyme_meta) if enzyme_meta else None,
                "proteins": [dict(row) for row in protein_rows],
                "text_facts": [dict(row) for row in text_rows],
            },
        }
        logger.info(
            "researcher.local_payload",
            ec_number=ec_number,
            organism=organism,
            record_count=payload["record_count"],
            db=str(self._local_db_path),
        )
        return payload


__all__ = ["ResearcherAgent"]
