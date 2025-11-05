"""Orchestrator agent supervising the multi-agent workflow."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from src.agents.analyst import AnalystAgent
from src.agents.base import AgentContext, BaseAgent
from src.agents.researcher import ResearcherAgent


class OrchestratorAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="orchestrator",
            description="Coordinates researcher and analyst agents to deliver final reports.",
        )
        self._researcher = ResearcherAgent()
        self._analyst = AnalystAgent()

    async def handle_task(self, context: AgentContext) -> Dict[str, Any]:
        work_spec = context.payload
        ec_number = work_spec.get("ec_number")
        if not ec_number:
            raise ValueError("Orchestrator requires an 'ec_number' in the work specification")

        organism = work_spec.get("organism")

        researcher_context = AgentContext(
            task_id=_child_task_id(context.task_id, suffix="research"),
            payload={"ec_number": ec_number, "organism": organism},
        )
        researcher_output = await self._researcher.run(researcher_context)

        records: List[Dict[str, Any]] = researcher_output.get("brenda_data", {}).get("data", [])
        analyst_context = AgentContext(
            task_id=_child_task_id(context.task_id, suffix="analysis"),
            payload={"records": records},
        )
        analyst_output = await self._analyst.run(analyst_context)

        report = {
            "ec_number": ec_number,
            "organism": organism,
            "record_count": len(records),
            "analysis_summary": analyst_output.get("summary"),
        }

        return {
            "brenda_payload": researcher_output,
            "analysis": analyst_output,
            "report": report,
        }


def _child_task_id(task_id: str, *, suffix: str) -> str:
    return f"{task_id}:{suffix}:{uuid.uuid4().hex[:8]}"


__all__ = ["OrchestratorAgent"]
