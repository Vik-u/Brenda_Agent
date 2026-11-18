"""Workflow orchestration that enriches the enzyme insight with KG neighbors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from src.agents.orchestrator import OrchestratorAgent
from src.core.settings import get_settings
from src.kg.retrieval import KGReader
from src.utils.logger import get_logger
from src.workflows.brenda_enzyme_insight import BrendaEnzymeInsightWorkflow

logger = get_logger(__name__)


class BrendaEnzymeInsightKGWorkflow:
    def __init__(self, orchestrator: Optional[OrchestratorAgent] = None) -> None:
        self._base = BrendaEnzymeInsightWorkflow(orchestrator=orchestrator)
        settings = get_settings()
        self._kg_path = Path(settings.kg.database_path)

    async def run(
        self, *, ec_number: str, organism: Optional[str] = None
    ) -> Dict[str, Any]:
        result = await self._base.run(ec_number=ec_number, organism=organism)
        kg_payload: Dict[str, Any] = {"status": "not_configured"}
        if self._kg_path.exists():
            try:
                reader = KGReader(self._kg_path)
                node_id = f"enzyme:{ec_number}"
                neighbors = reader.neighbors(node_id, limit=300)
                kg_payload = {
                    "status": "ok",
                    "node_id": node_id,
                    "neighbor_count": len(neighbors),
                    "neighbors": [
                        {
                            "relation": n.relation,
                            "target_id": n.target_id,
                            "target_type": n.target_type,
                            "target_label": n.target_label,
                            "target_properties": n.target_properties,
                        }
                        for n in neighbors
                    ],
                }
            except Exception as exc:
                logger.warning("kg.enrichment.failed", error=str(exc))
                kg_payload = {"status": "error", "error": str(exc)}
        else:
            logger.info("kg.enrichment.skipped", path=str(self._kg_path))

        result["kg"] = kg_payload
        return result


__all__ = ["BrendaEnzymeInsightKGWorkflow"]
