"""Analyst agent responsible for validating and transforming enzyme datasets."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from src.agents.base import AgentContext, BaseAgent


class AnalystAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="analyst",
            description="Cleans, validates, and summarizes enzyme kinetic data for downstream use.",
        )

    async def handle_task(self, context: AgentContext) -> Dict[str, Any]:
        payload = context.payload
        records: List[Dict[str, Any]] = payload.get("records", [])
        if not records:
            return {
                "validated_records": [],
                "summary": {"record_count": 0},
            }

        frame = pd.DataFrame(records)
        frame = frame.drop_duplicates()
        frame = frame.fillna({col: "unknown" for col in frame.columns if frame[col].isna().any()})

        summary = frame.describe(include="all").to_dict()
        summary["record_count"] = len(frame)

        return {
            "validated_records": frame.to_dict(orient="records"),
            "summary": summary,
        }


__all__ = ["AnalystAgent"]
