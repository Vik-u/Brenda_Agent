"""Researcher agent responsible for interacting with BRENDA and knowledge sources."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents.base import AgentContext, BaseAgent
from src.services.brenda_client import BrendaClient
from src.core.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResearcherAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="researcher",
            description=(
                "Queries BRENDA and supporting literature sources to gather enzyme kinetics data."
            ),
        )
        self._client = BrendaClient()
        settings = get_settings()
        self._local_db_path = self._resolve_local_db_path(settings)

    async def handle_task(self, context: AgentContext) -> Dict[str, Any]:
        task = context.payload
        ec_number = task.get("ec_number")
        if not ec_number:
            raise ValueError("Researcher agent requires an 'ec_number' in the payload")

        organism = task.get("organism")
        brenda_data = await self._fetch_with_fallback(ec_number=ec_number, organism=organism)

        return {
            "ec_number": ec_number,
            "organism": organism,
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
                "comment, proteins, reference_ids FROM enzyme_facts WHERE ec_number = ?"
            )
            params: List[Any] = [ec_number]
            if organism:
                like_fragment = f"%{organism.lower()}%"
                fact_query += (
                    " AND (LOWER(COALESCE(context, '')) LIKE ? "
                    "OR LOWER(COALESCE(proteins, '')) LIKE ?)"
                )
                params.extend([like_fragment, like_fragment])

            fact_rows = conn.execute(fact_query, tuple(params)).fetchall()

            protein_rows = conn.execute(
                "SELECT protein_id, organism, comment, reference_ids FROM proteins WHERE ec_number = ?",
                (ec_number,),
            ).fetchall()
        finally:
            conn.close()

        payload = {
            "source": "local_sqlite",
            "data": [dict(row) for row in fact_rows],
            "record_count": len(fact_rows),
            "metadata": {
                "enzyme": dict(enzyme_meta) if enzyme_meta else None,
                "proteins": [dict(row) for row in protein_rows],
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
