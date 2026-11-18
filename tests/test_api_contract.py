import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import src.interfaces.api as api_module


def test_health_endpoint() -> None:
    client = TestClient(api_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_enzymes_endpoint(ingested_db: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "DB_PATH", ingested_db)
    client = TestClient(api_module.app)
    response = client.get("/enzymes/1.1.1.1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ec_number"] == "1.1.1.1"
    assert "facts" in payload
    assert "proteins" in payload


def test_search_endpoint(ingested_db: Path, monkeypatch) -> None:
    monkeypatch.setattr(api_module, "DB_PATH", ingested_db)
    client = TestClient(api_module.app)
    response = client.get("/search", params={"q": "alcohol"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "alcohol"
    assert payload["enzymes"]
