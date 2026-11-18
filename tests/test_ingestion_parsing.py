import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines import brenda_ingestion


def test_parse_value_numeric_cases() -> None:
    cases = [
        ("0.12 mM", (0.12, 0.12, "mM", None)),
        ("0.1-0.2 mM", (0.1, 0.2, "mM", None)),
        ("~0.1 mM", (0.1, 0.1, "mM", None)),
        (">10 mM", (10.0, 10.0, "mM", None)),
        ("ND", (None, None, None, None)),
        ("1e-3 M", (0.001, 0.001, "M", None)),
        ("0.5 mM {glucose}", (0.5, 0.5, "mM", "glucose")),
    ]

    for value, expected in cases:
        assert brenda_ingestion._parse_value(value) == expected
