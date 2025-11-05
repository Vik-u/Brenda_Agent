"""Analyst agent responsible for validating and transforming enzyme datasets."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from src.agents.base import AgentContext, BaseAgent


class AnalystAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="analyst",
            description=(
                "Normalises the researcher payload so the rest of the system can reason over it. "
                "Deduplicates rows, highlights dominant categories and units, surfaces numeric "
                "ranges (KM, Ki, turnover, etc.), and flags missing values that may require "
                "follow-up searches."
            ),
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

        missing_counts = frame.isna().sum().to_dict()

        numeric_candidates = [
            col
            for col in ("value_numeric_low", "value_numeric_high", "value")
            if col in frame.columns
        ]
        for col in numeric_candidates:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")

        numeric_cols = frame.select_dtypes(include="number").columns.tolist()
        numeric_summary = (
            frame[numeric_cols].describe().to_dict()
            if numeric_cols
            else {}
        )

        category_counts = (
            frame["category"].value_counts().head(10).to_dict()
            if "category" in frame.columns
            else {}
        )
        unit_counts = (
            frame["unit"].value_counts().head(10).to_dict()
            if "unit" in frame.columns
            else {}
        )

        frame = frame.fillna({col: "unknown" for col in frame.columns if frame[col].isna().any()})

        return {
            "validated_records": frame.to_dict(orient="records"),
            "summary": {
                "record_count": len(frame),
                "categories": category_counts,
                "units": unit_counts,
                "numeric_summary": numeric_summary,
                "missing_counts": missing_counts,
            },
        }


__all__ = ["AnalystAgent"]
