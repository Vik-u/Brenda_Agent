"""Async client for interacting with the BRENDA enzyme database."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from src.core.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BrendaClient:
    def __init__(self, *, timeout: float = 30.0) -> None:
        settings = get_settings()
        self._base_url = settings.services.brenda.base_url.rstrip("/")
        self._api_key = settings.services.brenda.api_key
        self._timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if self._api_key:
            self._headers["Authorization"] = f"Bearer {self._api_key}"

    async def fetch_enzyme_data(
        self, *, ec_number: str, organism: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve enzyme data for a given EC number and optional organism filter."""
        params: Dict[str, Any] = {"ecNumber": ec_number}
        if organism:
            params["organism"] = organism

        url = f"{self._base_url}/enzymes"
        logger.info("brenda.fetch_enzyme_data.request", url=url, params=params)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, headers=self._headers, params=params)
            response.raise_for_status()
            payload: Dict[str, Any] = response.json()

        logger.info(
            "brenda.fetch_enzyme_data.success",
            ec_number=ec_number,
            organism=organism,
            record_count=len(payload.get("data", [])),
        )
        return payload


__all__ = ["BrendaClient"]
