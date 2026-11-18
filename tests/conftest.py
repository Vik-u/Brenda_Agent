import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.brenda_ingestion import ingest


@pytest.fixture()
def fixture_paths(tmp_path: Path) -> tuple[Path, Path]:
    json_src = PROJECT_ROOT / "tests" / "fixtures" / "brenda_fixture.json"
    txt_src = PROJECT_ROOT / "tests" / "fixtures" / "brenda_fixture.txt"
    json_dst = tmp_path / "brenda_fixture.json"
    txt_dst = tmp_path / "brenda_fixture.txt"
    shutil.copyfile(json_src, json_dst)
    shutil.copyfile(txt_src, txt_dst)
    return json_dst, txt_dst


@pytest.fixture()
def ingested_db(tmp_path: Path, fixture_paths: tuple[Path, Path]) -> Path:
    json_path, txt_path = fixture_paths
    db_path = tmp_path / "brenda_fixture.db"
    ingest(json_path, db_path, txt_path)
    return db_path
