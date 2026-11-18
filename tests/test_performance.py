import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_ec_category_query_is_fast(ingested_db: Path) -> None:
    conn = sqlite3.connect(ingested_db)
    start = time.perf_counter()
    rows = conn.execute(
        """
        SELECT category, value
        FROM enzyme_facts
        WHERE ec_number = '1.1.1.1' AND category = 'km_value'
        LIMIT 10
        """
    ).fetchall()
    elapsed = time.perf_counter() - start
    conn.close()

    assert rows
    assert elapsed < 0.25
