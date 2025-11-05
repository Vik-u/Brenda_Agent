from src.core.settings import get_settings


def test_settings_loads_defaults() -> None:
    settings = get_settings()
    assert settings.app.name == "brenda-agentic-workflow"
    assert settings.workflows.default_timeout_seconds == 180
