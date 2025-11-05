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
            description=(
                "Supervises the multi-agent workflow: dispatches discovery requests to the "
                "researcher, routes enriched records through the analyst, and assembles the "
                "final report (including provenance and summary statistics) for downstream "
                "consumers."
            ),
        )
        self._researcher = ResearcherAgent()
        self._analyst = AnalystAgent()

    async def handle_task(self, context: AgentContext) -> Dict[str, Any]:
        work_spec = context.payload or {}

        researcher_context = AgentContext(
            task_id=_child_task_id(context.task_id, suffix="research"),
            payload=dict(work_spec),
        )
        researcher_output = await self._researcher.run(researcher_context)

        records: List[Dict[str, Any]] = (
            researcher_output.get("brenda_data", {}).get("data", [])
        )
        analyst_context = AgentContext(
            task_id=_child_task_id(context.task_id, suffix="analysis"),
            payload={"records": records},
        )
        analyst_output = await self._analyst.run(analyst_context)

        resolved_ec_numbers = researcher_output.get("resolved_ec_numbers", [])
        primary_ec_number = researcher_output.get("ec_number")
        report = {
            "ec_number": primary_ec_number,
            "resolved_ec_numbers": resolved_ec_numbers,
            "organism": work_spec.get("organism"),
            "record_count": len(records),
            "analysis_summary": analyst_output.get("summary"),
            "search_terms": researcher_output.get("search_terms", {}),
        }

        return {
            "brenda_payload": researcher_output,
            "analysis": analyst_output,
            "report": report,
        }


def _child_task_id(task_id: str, *, suffix: str) -> str:
    return f"{task_id}:{suffix}:{uuid.uuid4().hex[:8]}"


__all__ = ["OrchestratorAgent"]
