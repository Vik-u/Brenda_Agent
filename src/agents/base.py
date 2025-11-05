"""Agent abstractions for the multi-agent workflow."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentContext:
    task_id: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any] | None = None


class BaseAgent(abc.ABC):
    name: str
    description: str

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    async def run(self, context: AgentContext) -> Dict[str, Any]:
        logger.info("agent.run.start", agent=self.name, task_id=context.task_id)
        result = await self.handle_task(context)
        logger.info("agent.run.end", agent=self.name, task_id=context.task_id)
        return result

    @abc.abstractmethod
    async def handle_task(self, context: AgentContext) -> Dict[str, Any]:
        """Implement agent-specific logic."""


__all__ = ["AgentContext", "BaseAgent"]
