
"""Data models shared across agents and workflows."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EnzymeRecord(BaseModel):
    ec_number: str
    organism: Optional[str]
    substrate: Optional[str]
    km_value: Optional[float]
    temperature: Optional[float]


class WorkflowReport(BaseModel):
    ec_number: str
    organism: Optional[str]
    record_count: int
    highlights: List[str] = Field(default_factory=list)


__all__ = ["EnzymeRecord", "WorkflowReport"]
