"""Workflow orchestration for the BRENDA enzyme insight process."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from src.agents.base import AgentContext
from src.agents.orchestrator import OrchestratorAgent
from src.core.settings import get_settings
from src.utils.logger import configure_logging, get_logger

logger = get_logger(__name__)


class BrendaEnzymeInsightWorkflow:
    def __init__(self, orchestrator: Optional[OrchestratorAgent] = None) -> None:
        settings = get_settings()
        configure_logging(settings.app.log_level)
        self._orchestrator = orchestrator or OrchestratorAgent()

    async def run(self, *, ec_number: str, organism: Optional[str] = None) -> Dict[str, Any]:
        if not ec_number:
            raise ValueError("Workflow requires an EC number to run")

        task_id = uuid.uuid4().hex
        context = AgentContext(
            task_id=task_id,
            payload={"ec_number": ec_number, "organism": organism},
        )
        logger.info(
            "workflow.start",
            workflow="brenda_enzyme_insight",
            ec_number=ec_number,
            organism=organism,
            task_id=task_id,
        )
        result = await self._orchestrator.run(context)
        logger.info("workflow.complete", task_id=task_id)
        return result


__all__ = ["BrendaEnzymeInsightWorkflow"]
