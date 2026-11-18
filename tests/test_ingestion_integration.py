import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_ingestion_builds_expected_tables(ingested_db: Path) -> None:
    conn = sqlite3.connect(ingested_db)
    cur = conn.cursor()
    tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"enzymes", "proteins", "enzyme_facts", "text_facts"}.issubset(tables)

    enzyme_count = cur.execute("SELECT COUNT(*) FROM enzymes").fetchone()[0]
    protein_count = cur.execute("SELECT COUNT(*) FROM proteins").fetchone()[0]
    fact_count = cur.execute("SELECT COUNT(*) FROM enzyme_facts").fetchone()[0]
    text_count = cur.execute("SELECT COUNT(*) FROM text_facts").fetchone()[0]

    assert enzyme_count == 2
    assert protein_count == 1
    assert fact_count == 7
    assert text_count == 4

    row = cur.execute(
        "SELECT recommended_name FROM enzymes WHERE ec_number = '1.1.1.1'"
    ).fetchone()
    assert row[0] == "alcohol dehydrogenase"

    conn.close()
