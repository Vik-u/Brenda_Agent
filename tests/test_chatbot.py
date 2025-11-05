import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.chatbot import BrendaChatbot


class _StubResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLM:
    """Minimal stand-in for ChatOllama used in tests."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.model = "stub-model"

    def invoke(self, prompt: str, **_: object) -> _StubResponse:
        if not self._responses:
            raise RuntimeError("StubLLM ran out of scripted responses")
        return _StubResponse(self._responses.pop(0))


@pytest.fixture()
def tiny_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "brenda.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE enzymes (
            ec_number TEXT PRIMARY KEY,
            enzyme_id TEXT,
            recommended_name TEXT,
            systematic_name TEXT,
            reaction_summary TEXT,
            protein_count INTEGER,
            synonym_count INTEGER,
            reaction_count INTEGER,
            km_count INTEGER,
            turnover_count INTEGER,
            inhibitor_count INTEGER
        );

        CREATE TABLE enzyme_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            category TEXT NOT NULL,
            value TEXT,
            value_numeric_low REAL,
            value_numeric_high REAL,
            unit TEXT,
            context TEXT,
            comment TEXT,
            proteins TEXT,
            reference_ids TEXT,
            raw_json TEXT
        );

        CREATE TABLE proteins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            protein_id TEXT,
            organism TEXT,
            comment TEXT,
            reference_ids TEXT,
            raw_json TEXT
        );

        CREATE TABLE text_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            field_code TEXT NOT NULL,
            field_name TEXT,
            value_raw TEXT,
            value_text TEXT,
            protein_tokens TEXT,
            reference_tokens TEXT,
            qualifiers TEXT
        );
        """
    )

    cur.execute(
        """
        INSERT INTO enzymes (
            ec_number, enzyme_id, recommended_name, systematic_name,
            reaction_summary, protein_count, synonym_count, reaction_count,
            km_count, turnover_count, inhibitor_count
        )
        VALUES (?, ?, ?, ?, ?, 2, 0, 1, 0, 0, 1)
        """,
        (
            "2.1.1.247",
            "ENZ1",
            "sample enzyme",
            "sample systematic",
            "substrate A + cofactor -> product",
        ),
    )

    cur.execute(
        """
        INSERT INTO enzyme_facts (
            ec_number, category, value, value_numeric_low,
            value_numeric_high, unit, context, comment, proteins,
            reference_ids, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2.1.1.247",
            "inhibitor",
            "EDTA",
            None,
            None,
            None,
            None,
            "chelates metal cofactors",
            "1",
            "42",
            "{}",
        ),
    )

    conn.commit()
    conn.close()
    return db_path


def test_chatbot_returns_human_summary(tiny_database: Path) -> None:
    responses = [
        "SELECT value, comment FROM enzyme_facts WHERE ec_number = '2.1.1.247' AND category = 'inhibitor' LIMIT 5;",
        "EDTA shows up as the main inhibitor for EC 2.1.1.247 in this mock dataset.",
    ]
    llm = _StubLLM(responses)
    bot = BrendaChatbot(database_path=tiny_database, llm=llm)

    result = bot.ask("Tell me about inhibitors for EC 2.1.1.247")

    assert "EDTA" in result.answer
    assert result.sql[0].lower().startswith("select")
    assert llm._responses == []
