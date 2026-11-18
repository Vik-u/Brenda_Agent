"""Sync the SQLite BRENDA mirror into PostgreSQL."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url

BATCH_SIZE = 5000


def _build_engine(postgres_url: str) -> Engine:
    url = make_url(postgres_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url)


def _init_schema(conn: Connection, *, drop_existing: bool) -> None:
    statements = []
    if drop_existing:
        statements.extend(
            [
                "DROP TABLE IF EXISTS text_facts",
                "DROP TABLE IF EXISTS enzyme_facts",
                "DROP TABLE IF EXISTS proteins",
                "DROP TABLE IF EXISTS enzymes",
            ]
        )

    statements.extend(
        [
            """
            CREATE TABLE IF NOT EXISTS enzymes (
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
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS proteins (
                id BIGINT PRIMARY KEY,
                ec_number TEXT NOT NULL,
                protein_id TEXT,
                organism TEXT,
                comment TEXT,
                reference_ids TEXT,
                raw_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS enzyme_facts (
                id BIGINT PRIMARY KEY,
                ec_number TEXT NOT NULL,
                category TEXT NOT NULL,
                value TEXT,
                value_numeric_low DOUBLE PRECISION,
                value_numeric_high DOUBLE PRECISION,
                unit TEXT,
                context TEXT,
                comment TEXT,
                proteins TEXT,
                reference_ids TEXT,
                raw_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS text_facts (
                id BIGINT PRIMARY KEY,
                ec_number TEXT NOT NULL,
                field_code TEXT NOT NULL,
                field_name TEXT,
                value_raw TEXT,
                value_text TEXT,
                protein_tokens TEXT,
                reference_tokens TEXT,
                qualifiers TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_proteins_ec ON proteins (ec_number)",
            "CREATE INDEX IF NOT EXISTS idx_facts_ec ON enzyme_facts (ec_number)",
            "CREATE INDEX IF NOT EXISTS idx_facts_category ON enzyme_facts (category)",
            "CREATE INDEX IF NOT EXISTS idx_facts_value ON enzyme_facts (value)",
            "CREATE INDEX IF NOT EXISTS idx_text_ec ON text_facts (ec_number)",
            "CREATE INDEX IF NOT EXISTS idx_text_code ON text_facts (field_code)",
        ]
    )

    for stmt in statements:
        conn.execute(text(stmt))


def _copy_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: Connection,
    *,
    table: str,
    columns: Sequence[str],
) -> int:
    select_sql = f"SELECT {', '.join(columns)} FROM {table}"
    cursor = sqlite_conn.execute(select_sql)
    insert_sql = text(
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(f':{col}' for col in columns)})"
    )

    total = 0
    while True:
        rows = cursor.fetchmany(BATCH_SIZE)
        if not rows:
            break
        payload = [dict(zip(columns, row)) for row in rows]
        pg_conn.execute(insert_sql, payload)
        total += len(payload)
    return total


def sync_sqlite_to_postgres(
    sqlite_path: Path, postgres_url: str, *, drop_existing: bool
) -> Dict[str, Any]:
    sqlite_path = sqlite_path.expanduser().resolve()
    if not sqlite_path.exists():
        raise FileNotFoundError(sqlite_path)

    engine = _build_engine(postgres_url)
    with sqlite3.connect(sqlite_path) as sqlite_conn, engine.begin() as pg_conn:
        _init_schema(pg_conn, drop_existing=drop_existing)

        totals = {}
        totals["enzymes"] = _copy_table(
            sqlite_conn,
            pg_conn,
            table="enzymes",
            columns=[
                "ec_number",
                "enzyme_id",
                "recommended_name",
                "systematic_name",
                "reaction_summary",
                "protein_count",
                "synonym_count",
                "reaction_count",
                "km_count",
                "turnover_count",
                "inhibitor_count",
            ],
        )
        totals["proteins"] = _copy_table(
            sqlite_conn,
            pg_conn,
            table="proteins",
            columns=[
                "id",
                "ec_number",
                "protein_id",
                "organism",
                "comment",
                "reference_ids",
                "raw_json",
            ],
        )
        totals["enzyme_facts"] = _copy_table(
            sqlite_conn,
            pg_conn,
            table="enzyme_facts",
            columns=[
                "id",
                "ec_number",
                "category",
                "value",
                "value_numeric_low",
                "value_numeric_high",
                "unit",
                "context",
                "comment",
                "proteins",
                "reference_ids",
                "raw_json",
            ],
        )
        totals["text_facts"] = _copy_table(
            sqlite_conn,
            pg_conn,
            table="text_facts",
            columns=[
                "id",
                "ec_number",
                "field_code",
                "field_name",
                "value_raw",
                "value_text",
                "protein_tokens",
                "reference_tokens",
                "qualifiers",
            ],
        )
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync the SQLite mirror into PostgreSQL."
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path("data/processed/brenda.db"),
        help="Source SQLite database.",
    )
    parser.add_argument(
        "--postgres-url",
        required=True,
        help="Target Postgres connection string.",
    )
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop existing tables before sync.",
    )
    args = parser.parse_args()

    totals = sync_sqlite_to_postgres(
        args.sqlite,
        args.postgres_url,
        drop_existing=args.drop_existing,
    )
    print(totals)


if __name__ == "__main__":
    main()
