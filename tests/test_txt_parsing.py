import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.brenda_ingestion import _iter_text_records


def test_iter_text_records_extracts_fields(tmp_path: Path) -> None:
    content = (
        "ID\t1.1.1.1\n"
        "KM\t0.12 mM {glucose} <1>\n"
        "IN\t#P12345# EDTA <2>\n"
        "///\n"
    )
    path = tmp_path / "brenda.txt"
    path.write_text(content)

    records = list(_iter_text_records(path))
    assert len(records) == 2

    km_record = records[0]
    assert km_record[0] == "1.1.1.1"
    assert km_record[1] == "KM"
    assert km_record[2] == "Km value"
    assert km_record[3] == "0.12 mM {glucose} <1>"
    assert km_record[4] == "0.12 mM glucose"
    assert km_record[5] is None
    assert km_record[6] == "1"
    assert km_record[7] == "glucose"

    in_record = records[1]
    assert in_record[1] == "IN"
    assert in_record[2] == "inhibitor"
    assert in_record[4] == "P12345 EDTA"
    assert in_record[5] == "P12345"
    assert in_record[6] == "2"
