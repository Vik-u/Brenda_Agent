"""Configuration management for the BRENDA multi-agent workflow."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"


class BrendaServiceSettings(BaseModel):
    base_url: str = Field(default="https://www.brenda-enzymes.org/api")
    api_key: Optional[str] = None


class OpenAISettings(BaseModel):
    api_key: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.2


class RedisSettings(BaseModel):
    url: str = Field(default="redis://localhost:6379/0")


class DatabaseSettings(BaseModel):
    url: str = Field(default="sqlite:///data/processed/brenda.db")


class OllamaSettings(BaseModel):
    base_url: str = Field(default="http://localhost:11434")
    model: str = Field(default="gpt:oss")
    temperature: float = Field(default=0.1)
    top_p: float = Field(default=0.95)


class ServiceSettings(BaseModel):
    brenda: BrendaServiceSettings = BrendaServiceSettings()
    openai: OpenAISettings = OpenAISettings()
    redis: RedisSettings = RedisSettings()
    database: DatabaseSettings = DatabaseSettings()
    ollama: OllamaSettings = OllamaSettings()


class WorkflowSettings(BaseModel):
    default_timeout_seconds: int = Field(default=180)
    max_retries: int = Field(default=3)


class AppSettings(BaseModel):
    name: str = Field(default="brenda-agentic-workflow")
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")


class ChatbotSettings(BaseModel):
    database_path: str = Field(default="data/processed/brenda.db")
    top_k: int = Field(default=5)
    max_iterations: int = Field(default=12)
    max_rows: int = Field(default=25)


class Settings(BaseModel):
    app: AppSettings = AppSettings()
    services: ServiceSettings = ServiceSettings()
    workflows: WorkflowSettings = WorkflowSettings()
    chatbot: ChatbotSettings = ChatbotSettings()
    raw: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        data = _load_yaml(SETTINGS_FILE)
        merged = _interpolate_env(data)
        app_cfg = merged.get("app", {})
        services_cfg = merged.get("services", {})
        workflows_cfg = merged.get("workflows", {})
        chatbot_cfg = merged.get("chatbot", {})
        return cls(
            app=AppSettings(**app_cfg),
            services=ServiceSettings(**services_cfg),
            workflows=WorkflowSettings(**workflows_cfg),
            chatbot=ChatbotSettings(**chatbot_cfg),
            raw=merged,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    return yaml.safe_load(path.read_text()) or {}


def _interpolate_env(data: Dict[str, Any]) -> Dict[str, Any]:
    def resolve(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            expression = value[2:-1]
            env_key = expression
            default = ""
            if ':-' in expression:
                env_key, default = expression.split(':-', 1)
            elif '-' in expression:
                env_key, default = expression.split('-', 1)
            env_key = env_key.strip()
            return os.getenv(env_key, default)
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    return {key: resolve(val) for key, val in data.items()}


__all__ = ["Settings", "get_settings"]
