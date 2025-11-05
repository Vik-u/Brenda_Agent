"""FastAPI service for interactive exploration of the ingested BRENDA database."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.services import BrendaChatbot

DB_PATH = Path("data/processed/brenda.db")

app = FastAPI(title="BRENDA Agentic API", version="0.2.0")

STATIC_UI = Path(__file__).resolve().parents[2] / "static" / "ui" / "index.html"

_chatbot_instance: Optional[BrendaChatbot] = None


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    sql: List[str]


def get_chatbot() -> BrendaChatbot:
    global _chatbot_instance
    if _chatbot_instance is None:
        try:
            _chatbot_instance = BrendaChatbot()
        except FileNotFoundError as exc:  # pragma: no cover - init guard
            raise HTTPException(status_code=500, detail=str(exc))
    return _chatbot_instance


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def close_connection(conn: sqlite3.Connection) -> None:
    conn.close()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/enzymes/{ec_number}")
def get_enzyme(
    ec_number: str,
    include_facts: bool = Query(True, description="Include grouped fact payloads"),
    include_text: bool = Query(True, description="Include grouped text fields"),
    conn: sqlite3.Connection = Depends(get_connection),
) -> Dict[str, Any]:
    try:
        row = conn.execute(
            """
            SELECT *
            FROM enzymes
            WHERE ec_number = ?
            """,
            (ec_number,),
        ).fetchone()
    finally:
        close_connection(conn)

    if row is None:
        raise HTTPException(status_code=404, detail="EC number not found")

    payload = dict(row)

    if include_facts:
        payload["facts"] = _fetch_facts(ec_number, limit=200)
        payload["proteins"] = _fetch_proteins(ec_number)
    if include_text:
        payload["text_fields"] = _fetch_text_fields(ec_number, limit=200)

    return payload


@app.get("/search")
def search(
    q: str = Query(..., min_length=2, description="Search term"),
    limit: int = Query(25, gt=0, le=100),
) -> Dict[str, Any]:
    pattern = f"%{q}%"
    with get_connection() as conn:
        enzyme_hits = conn.execute(
            """
            SELECT ec_number, recommended_name, systematic_name, synonym_count
            FROM enzymes
            WHERE recommended_name LIKE ? OR systematic_name LIKE ?
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()

        synonym_hits = conn.execute(
            """
            SELECT ec_number, value AS synonym
            FROM enzyme_facts
            WHERE category = 'synonyms' AND value LIKE ?
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()

        text_hits = conn.execute(
            """
            SELECT ec_number, field_code, value_text
            FROM text_facts
            WHERE value_text LIKE ?
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()

    return {
        "query": q,
        "enzymes": [dict(row) for row in enzyme_hits],
        "synonyms": [dict(row) for row in synonym_hits],
        "text_fields": [dict(row) for row in text_hits],
    }


@app.get("/insights/summary")
def insights_summary() -> Dict[str, Any]:
    with get_connection() as conn:
        totals = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM enzymes) AS enzyme_count,
                (SELECT SUM(protein_count) FROM enzymes) AS protein_annotations,
                (SELECT COUNT(*) FROM proteins) AS protein_rows,
                (SELECT COUNT(*) FROM enzyme_facts) AS fact_rows,
                (SELECT COUNT(*) FROM text_facts) AS text_rows
            """
        ).fetchone()

        top_proteins = conn.execute(
            """
            SELECT ec_number, recommended_name, protein_count, synonym_count
            FROM enzymes
            ORDER BY protein_count DESC
            LIMIT 5
            """
        ).fetchall()

        top_references = conn.execute(
            """
            SELECT ec_number, COUNT(*) AS reference_records
            FROM text_facts
            GROUP BY ec_number
            ORDER BY reference_records DESC
            LIMIT 5
            """
        ).fetchall()

        top_inhibitors = conn.execute(
            """
            SELECT value AS inhibitor, COUNT(*) AS entries
            FROM enzyme_facts
            WHERE category = 'inhibitor' AND value IS NOT NULL
            GROUP BY inhibitor
            ORDER BY entries DESC
            LIMIT 10
            """
        ).fetchall()

    return {
        "totals": dict(totals),
        "top_proteins": [dict(row) for row in top_proteins],
        "top_references": [dict(row) for row in top_references],
        "top_inhibitors": [dict(row) for row in top_inhibitors],
    }


@app.get("/enzymes/{ec_number}/facts")
def list_facts(
    ec_number: str,
    category: Optional[str] = Query(None, description="Filter by fact category"),
    limit: int = Query(200, gt=0, le=2000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    query = (
        "SELECT category, value, value_numeric_low, value_numeric_high, unit, context, comment, proteins, reference_ids "
        "FROM enzyme_facts WHERE ec_number = ?"
    )
    params: List[Any] = [ec_number]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY category, id LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return {
        "ec_number": ec_number,
        "category": category,
        "results": [dict(row) for row in rows],
        "count": len(rows),
    }


@app.get("/kinetics")
def get_kinetics(
    ec_number: Optional[str] = Query(None, description="Filter by EC number"),
    parameter: Optional[str] = Query(
        None,
        description="Parameter category (km_value, turnover_number, kcat_km_value, specific_activity)",
    ),
    limit: int = Query(200, gt=0, le=2000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    query = (
        "SELECT ec_number, category, value, value_numeric_low, value_numeric_high, unit, context, comment, proteins, reference_ids "
        "FROM enzyme_facts WHERE category IN ('km_value', 'turnover_number', 'kcat_km_value', 'specific_activity')"
    )
    params: List[Any] = []

    if ec_number:
        query += " AND ec_number = ?"
        params.append(ec_number)
    if parameter:
        query += " AND category = ?"
        params.append(parameter)

    query += " ORDER BY ec_number LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return {
        "count": len(rows),
        "results": [dict(row) for row in rows],
    }


@app.get("/text-fields")
def list_text_fields(
    ec_number: Optional[str] = Query(None, description="Filter by EC number"),
    field_code: Optional[str] = Query(None, description="Filter by text field code"),
    limit: int = Query(200, gt=0, le=2000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    query = (
        "SELECT ec_number, field_code, field_name, value_text, value_raw, protein_tokens, reference_tokens, qualifiers "
        "FROM text_facts WHERE 1 = 1"
    )
    params: List[Any] = []
    if ec_number:
        query += " AND ec_number = ?"
        params.append(ec_number)
    if field_code:
        query += " AND field_code = ?"
        params.append(field_code)
    query += " ORDER BY ec_number, field_code LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return {
        "results": [dict(row) for row in rows],
        "count": len(rows),
    }


def _fetch_facts(ec_number: str, limit: int) -> Dict[str, List[Dict[str, Any]]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT category, value, value_numeric_low, value_numeric_high, unit, context, comment, proteins, reference_ids
            FROM enzyme_facts
            WHERE ec_number = ?
            ORDER BY category, id
            LIMIT ?
            """,
            (ec_number, limit),
        ).fetchall()

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(dict(row))
    return grouped


@app.get("/", response_class=FileResponse)
def serve_ui() -> FileResponse:
    if not STATIC_UI.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(STATIC_UI)


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest) -> ChatResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    chatbot = get_chatbot()
    try:
        result = chatbot.ask(question)
    except Exception as exc:  # pragma: no cover - LLM/runtime issues
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(answer=result.answer, sql=result.sql)


def _fetch_proteins(ec_number: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT protein_id, organism, comment, reference_ids
            FROM proteins
            WHERE ec_number = ?
            ORDER BY organism
            LIMIT 200
            """,
            (ec_number,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_text_fields(ec_number: str, limit: int) -> Dict[str, List[Dict[str, Any]]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT field_code, field_name, value_text, value_raw, protein_tokens, reference_tokens, qualifiers
            FROM text_facts
            WHERE ec_number = ?
            ORDER BY field_code, id
            LIMIT ?
            """,
            (ec_number, limit),
        ).fetchall()

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["field_code"]].append(dict(row))
    return grouped
