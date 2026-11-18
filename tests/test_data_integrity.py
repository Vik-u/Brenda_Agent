import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


EC_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def test_ec_numbers_are_well_formed(ingested_db: Path) -> None:
    conn = sqlite3.connect(ingested_db)
    rows = conn.execute("SELECT ec_number FROM enzymes").fetchall()
    conn.close()
    assert all(EC_RE.match(row[0]) for row in rows)


def test_fact_ec_numbers_exist_in_enzymes(ingested_db: Path) -> None:
    conn = sqlite3.connect(ingested_db)
    missing = conn.execute(
        """
        SELECT COUNT(*)
        FROM enzyme_facts ef
        LEFT JOIN enzymes e ON ef.ec_number = e.ec_number
        WHERE e.ec_number IS NULL
        """
    ).fetchone()[0]
    conn.close()
    assert missing == 0


def test_numeric_ranges_are_ordered(ingested_db: Path) -> None:
    conn = sqlite3.connect(ingested_db)
    bad_rows = conn.execute(
        """
        SELECT COUNT(*)
        FROM enzyme_facts
        WHERE value_numeric_low IS NOT NULL
          AND value_numeric_high IS NOT NULL
          AND value_numeric_low > value_numeric_high
        """
    ).fetchone()[0]
    conn.close()
    assert bad_rows == 0


def test_units_present_for_kinetic_categories(ingested_db: Path) -> None:
    conn = sqlite3.connect(ingested_db)
    rows = conn.execute(
        """
        SELECT COUNT(*)
        FROM enzyme_facts
        WHERE category IN ('km_value','turnover_number','kcat_km_value','ki_value','ic50_value','specific_activity')
          AND value_numeric_low IS NOT NULL
          AND (unit IS NULL OR unit = '')
        """
    ).fetchone()[0]
    conn.close()
    assert rows == 0
