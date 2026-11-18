"""Benchmark SQLite vs Postgres query latency on the BRENDA schema."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url


@dataclass
class QuerySpec:
    name: str
    sqlite_sql: str
    sqlite_params: Tuple[Any, ...]
    pg_sql: str
    pg_params: Dict[str, Any]


QUERY_SPECS = [
    QuerySpec(
        name="count_enzymes",
        sqlite_sql="SELECT COUNT(*) FROM enzymes",
        sqlite_params=(),
        pg_sql="SELECT COUNT(*) FROM enzymes",
        pg_params={},
    ),
    QuerySpec(
        name="facts_by_ec",
        sqlite_sql="SELECT * FROM enzyme_facts WHERE ec_number = ? LIMIT 200",
        sqlite_params=("1.1.1.1",),
        pg_sql="SELECT * FROM enzyme_facts WHERE ec_number = :ec LIMIT 200",
        pg_params={"ec": "1.1.1.1"},
    ),
    QuerySpec(
        name="facts_by_category",
        sqlite_sql="SELECT * FROM enzyme_facts WHERE category = ? LIMIT 200",
        sqlite_params=("inhibitor",),
        pg_sql="SELECT * FROM enzyme_facts WHERE category = :category LIMIT 200",
        pg_params={"category": "inhibitor"},
    ),
    QuerySpec(
        name="text_fields_by_code",
        sqlite_sql="SELECT * FROM text_facts WHERE field_code = ? LIMIT 200",
        sqlite_params=("KM",),
        pg_sql="SELECT * FROM text_facts WHERE field_code = :code LIMIT 200",
        pg_params={"code": "KM"},
    ),
    QuerySpec(
        name="join_enzyme_facts",
        sqlite_sql=(
            "SELECT e.ec_number, e.recommended_name, f.category "
            "FROM enzymes e JOIN enzyme_facts f ON e.ec_number = f.ec_number "
            "ORDER BY f.id LIMIT 200"
        ),
        sqlite_params=(),
        pg_sql=(
            "SELECT e.ec_number, e.recommended_name, f.category "
            "FROM enzymes e JOIN enzyme_facts f ON e.ec_number = f.ec_number "
            "ORDER BY f.id LIMIT 200"
        ),
        pg_params={},
    ),
]


def _timed_sqlite(
    conn: sqlite3.Connection, query: str, params: Tuple[Any, ...], runs: int
) -> Dict[str, Any]:
    timings: List[float] = []
    row_count = 0
    for _ in range(runs):
        start = time.perf_counter()
        rows = conn.execute(query, params).fetchall()
        elapsed = time.perf_counter() - start
        timings.append(elapsed)
        row_count = len(rows)
    return _summarize_timings(timings, row_count)


def _timed_postgres(
    conn: Connection, query: str, params: Dict[str, Any], runs: int
) -> Dict[str, Any]:
    timings: List[float] = []
    row_count = 0
    for _ in range(runs):
        start = time.perf_counter()
        rows = conn.execute(text(query), params).fetchall()
        elapsed = time.perf_counter() - start
        timings.append(elapsed)
        row_count = len(rows)
    return _summarize_timings(timings, row_count)


def _summarize_timings(timings: Iterable[float], row_count: int) -> Dict[str, Any]:
    timings = list(timings)
    if not timings:
        return {"rows": row_count, "avg_ms": None, "min_ms": None}
    avg_ms = sum(timings) / len(timings) * 1000
    min_ms = min(timings) * 1000
    return {"rows": row_count, "avg_ms": round(avg_ms, 3), "min_ms": round(min_ms, 3)}


def _sqlite_file_size(db_path: Path) -> Optional[int]:
    try:
        return os.path.getsize(db_path)
    except OSError:
        return None


def _postgres_db_size(conn: Connection) -> Optional[int]:
    try:
        result = conn.execute(text("SELECT pg_database_size(current_database())")).fetchone()
        if result:
            return int(result[0])
    except Exception:
        return None
    return None


def _build_pg_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    return create_engine(parsed)


def benchmark(
    sqlite_path: Path, postgres_url: Optional[str], runs: int
) -> Dict[str, Any]:
    results: Dict[str, Any] = {"sqlite": {}, "postgres": {}}

    sqlite_path = sqlite_path.expanduser().resolve()
    with sqlite3.connect(sqlite_path) as conn:
        for spec in QUERY_SPECS:
            results["sqlite"][spec.name] = _timed_sqlite(
                conn, spec.sqlite_sql, spec.sqlite_params, runs
            )
        results["sqlite"]["db_size_bytes"] = _sqlite_file_size(sqlite_path)

    if postgres_url:
        try:
            engine = _build_pg_engine(postgres_url)
            with engine.connect() as conn:
                for spec in QUERY_SPECS:
                    results["postgres"][spec.name] = _timed_postgres(
                        conn, spec.pg_sql, spec.pg_params, runs
                    )
                results["postgres"]["db_size_bytes"] = _postgres_db_size(conn)
        except Exception as exc:
            results["postgres"]["error"] = str(exc)
    else:
        results["postgres"]["status"] = "skipped_no_url"

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark SQLite vs Postgres query latency for BRENDA."
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path("data/processed/brenda.db"),
        help="Path to the SQLite database.",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("POSTGRES_URL"),
        help="Postgres connection URL.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of iterations per query.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/db_benchmark.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    results = benchmark(args.sqlite, args.postgres_url, args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
