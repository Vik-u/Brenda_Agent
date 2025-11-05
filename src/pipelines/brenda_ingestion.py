"""Structured ingestion pipeline for the BRENDA JSON release."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import ijson

NUMERIC_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
HASH_TOKEN_RE = re.compile(r"#([^#]+)#")
ANGLE_TOKEN_RE = re.compile(r"<([^<>]+)>")
BRACE_TOKEN_RE = re.compile(r"\{([^{}]+)\}")
PAREN_TOKEN_RE = re.compile(r"\(([^()]+)\)")

BASE_FIELDS = {"id", "recommended_name", "systematic_name"}
SPECIAL_KEYS = {"protein"}
BATCH_SIZE = 500

TEXT_FIELD_LABELS: Dict[str, str] = {
    "AC": "activating compound",
    "AP": "application",
    "CF": "cofactor",
    "CL": "cloned",
    "CR": "crystallization",
    "EN": "engineering",
    "EXP": "expression",
    "GI": "general information",
    "GS": "general stability",
    "IC50": "IC50 value",
    "ID": "EC class",
    "IN": "inhibitor",
    "KKM": "kcat/KM value",
    "KI": "Ki value",
    "KM": "Km value",
    "LO": "localization",
    "ME": "metals/ions",
    "MW": "molecular weight",
    "NSP": "natural substrates/products",
    "OS": "oxygen stability",
    "OSS": "organic solvent stability",
    "PHO": "pH optimum",
    "PHR": "pH range",
    "PHS": "pH stability",
    "PI": "isoelectric point",
    "PM": "post translational modification",
    "PR": "protein",
    "PU": "purification",
    "RE": "reaction",
    "RF": "reference",
    "REN": "renatured",
    "RN": "recommended name",
    "RT": "reaction type",
    "SA": "specific activity",
    "SN": "synonym",
    "SP": "substrate/product",
    "SS": "storage stability",
    "ST": "source tissue",
    "SU": "subunits",
    "SY": "systematic name",
    "TN": "turnover number",
    "TO": "temperature optimum",
    "TR": "temperature range",
    "TS": "temperature stability",
    "BR": "BRENDA release",
}


@dataclass
class IngestionStats:
    enzyme_count: int
    fact_count: int
    protein_count: int
    category_counts: Dict[str, int]
    text_fact_count: int = 0
    text_field_counts: Dict[str, int] = field(default_factory=dict)


def ingest(json_path: Path, db_path: Path, txt_path: Optional[Path] = None) -> IngestionStats:
    """Transform the raw BRENDA JSON dump into a structured SQLite database."""
    json_path = json_path.expanduser().resolve()
    db_path = db_path.expanduser().resolve()
    text_path = txt_path.expanduser().resolve() if txt_path else None

    if not json_path.exists():
        raise FileNotFoundError(json_path)
    if text_path is not None and not text_path.exists():
        raise FileNotFoundError(text_path)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=OFF;")
    conn.execute("PRAGMA temp_store=MEMORY;")

    _init_schema(conn)

    enzyme_rows: List[Tuple[Any, ...]] = []
    protein_rows: List[Tuple[Any, ...]] = []
    fact_rows: List[Tuple[Any, ...]] = []
    text_rows: List[Tuple[Any, ...]] = []

    stats = Counter()
    text_stats = Counter()
    enzyme_count = 0
    protein_count = 0

    with json_path.open("rb") as handle:
        for ec_number, entry in _iter_entries(handle):
            enzyme_count += 1
            enzyme_rows.append(_build_enzyme_row(ec_number, entry))

            proteins = entry.get("protein") or {}
            for protein_id, detail in proteins.items():
                protein_rows.append(
                    (
                        ec_number,
                        protein_id,
                        detail.get("organism"),
                        detail.get("comment"),
                        _join(detail.get("references")),
                        json.dumps(detail, ensure_ascii=False),
                    )
                )
                protein_count += 1

            for key, items in entry.items():
                if key in BASE_FIELDS or key in SPECIAL_KEYS:
                    continue
                if not items:
                    continue

                if isinstance(items, (str, int, float)):
                    fact_rows.append(
                        _build_fact_row(
                            ec_number,
                            category=key,
                            payload={"value": str(items)},
                        )
                    )
                    stats[key] += 1
                    continue

                if isinstance(items, dict):
                    fact_rows.append(
                        _build_fact_row(
                            ec_number,
                            category=key,
                            payload=items,
                        )
                    )
                    stats[key] += 1
                    continue

                if isinstance(items, Iterable):
                    for item in items:  # type: ignore[assignment]
                        payload: Dict[str, Any]
                        if isinstance(item, (str, int, float)):
                            payload = {"value": str(item)}
                        elif isinstance(item, dict):
                            payload = item
                        else:
                            payload = {"value": json.dumps(item, ensure_ascii=False)}
                        fact_rows.append(
                            _build_fact_row(
                                ec_number,
                                category=key,
                                payload=payload,
                            )
                        )
                        stats[key] += 1
                else:
                    fact_rows.append(
                        _build_fact_row(
                            ec_number,
                            category=key,
                            payload={"value": json.dumps(items, ensure_ascii=False)},
                        )
                    )
                    stats[key] += 1

            if len(enzyme_rows) >= BATCH_SIZE:
                _flush(conn, enzyme_rows, _insert_enzyme)
            if len(protein_rows) >= BATCH_SIZE:
                _flush(conn, protein_rows, _insert_protein)
            if len(fact_rows) >= BATCH_SIZE:
                _flush(conn, fact_rows, _insert_fact)

    _flush(conn, enzyme_rows, _insert_enzyme)
    _flush(conn, protein_rows, _insert_protein)
    _flush(conn, fact_rows, _insert_fact)

    text_fact_count = 0
    if text_path is not None:
        for record in _iter_text_records(text_path):
            text_rows.append(record)
            text_stats[record[1]] += 1
            text_fact_count += 1
            if len(text_rows) >= BATCH_SIZE:
                _flush(conn, text_rows, _insert_text_fact)
        _flush(conn, text_rows, _insert_text_fact)

    _create_indexes(conn)
    conn.close()

    return IngestionStats(
        enzyme_count=enzyme_count,
        fact_count=sum(stats.values()),
        protein_count=protein_count,
        category_counts=dict(stats),
        text_fact_count=text_fact_count,
        text_field_counts=dict(text_stats),
    )


def _iter_entries(handle: Any) -> Iterator[Tuple[str, Dict[str, Any]]]:
    for ec_number, payload in ijson.kvitems(handle, "data"):
        yield ec_number, payload


def _build_enzyme_row(ec_number: str, entry: Dict[str, Any]) -> Tuple[Any, ...]:
    proteins = entry.get("protein") or {}
    synonyms = entry.get("synonyms") or []
    reactions = entry.get("reaction") or []

    reaction_summary = None
    if reactions:
        first = reactions[0]
        if isinstance(first, dict):
            reaction_summary = first.get("value")
        elif isinstance(first, str):
            reaction_summary = first

    return (
        ec_number,
        entry.get("id"),
        entry.get("recommended_name"),
        entry.get("systematic_name"),
        reaction_summary,
        len(proteins),
        len(synonyms),
        len(reactions),
        len(entry.get("km_value") or []),
        len(entry.get("turnover_number") or []),
        len(entry.get("inhibitor") or []),
    )


def _build_fact_row(
    ec_number: str,
    *,
    category: str,
    payload: Dict[str, Any],
) -> Tuple[Any, ...]:
    value = payload.get("value")
    comment = payload.get("comment")

    value_low = None
    value_high = None
    unit = None
    context = None

    if isinstance(value, str):
        value_low, value_high, unit, context = _parse_value(value)
    raw_json = json.dumps(payload, ensure_ascii=False)

    proteins = _join(payload.get("proteins"))
    references = _join(payload.get("references"))

    if context is None:
        for key in ("organism", "substrate", "ligand", "tissue"):
            if payload.get(key):
                context = str(payload[key])
                break

    return (
        ec_number,
        category,
        value,
        value_low,
        value_high,
        unit,
        context,
        comment,
        proteins,
        references,
        raw_json,
    )


def _parse_value(value: str) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    value = value.strip()
    context = None

    match = re.match(r"^(?P<body>.*?)(?:\s*\{(?P<context>[^}]*)\})?$", value)
    body = value
    if match:
        body = match.group("body").strip()
        context = match.group("context")

    numbers = NUMERIC_RE.findall(body)
    low = high = None
    if numbers:
        try:
            low = float(numbers[0])
            high = float(numbers[-1])
        except ValueError:
            low = high = None

    unit = None
    if numbers:
        unit_candidate = NUMERIC_RE.sub("", body)
        unit_candidate = unit_candidate.replace("-", " ")
        unit_candidate = re.sub(r"\s+", " ", unit_candidate).strip()
        if unit_candidate:
            unit = unit_candidate

    return low, high, unit, context


def _join(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return ";".join(str(v) for v in value if v is not None)
    return str(value)


def _flush(conn: sqlite3.Connection, rows: List[Tuple[Any, ...]], inserter) -> None:
    if not rows:
        return
    inserter(conn, rows)
    rows.clear()


def _iter_text_records(path: Path) -> Iterator[Tuple[Any, ...]]:
    current_ec: Optional[str] = None
    current_code: Optional[str] = None
    buffer: List[str] = []

    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            if line.startswith("///"):
                yield from _flush_text_record(current_ec, current_code, buffer)
                current_code = None
                buffer = []
                current_ec = None
                continue
            if line.startswith("ID\t"):
                yield from _flush_text_record(current_ec, current_code, buffer)
                current_code = None
                buffer = []
                current_ec = line.split("\t", 1)[1].strip()
                continue
            if current_ec is None:
                continue
            if line.startswith("*"):
                continue
            if line.startswith(("\t", " ")):
                if current_code is not None:
                    buffer.append(line.strip())
                continue
            if "\t" in line:
                code, value = line.split("\t", 1)
                code = code.strip()
                value = value.strip()
                if not code:
                    continue
                if current_code is not None:
                    yield from _flush_text_record(current_ec, current_code, buffer)
                current_code = code
                buffer = [value] if value else []
                continue
            # section headings (e.g. PROTEIN) reset current field
            yield from _flush_text_record(current_ec, current_code, buffer)
            current_code = None
            buffer = []

        yield from _flush_text_record(current_ec, current_code, buffer)


def _flush_text_record(
    ec_number: Optional[str],
    code: Optional[str],
    buffer: List[str],
) -> Iterator[Tuple[Any, ...]]:
    if ec_number is None or code is None or not buffer:
        buffer.clear()
        return iter(())

    value = " ".join(part.strip() for part in buffer if part).strip()
    if not value:
        buffer.clear()
        return iter(())

    proteins = HASH_TOKEN_RE.findall(value)
    references = ANGLE_TOKEN_RE.findall(value)
    qualifiers = BRACE_TOKEN_RE.findall(value) + PAREN_TOKEN_RE.findall(value)
    cleaned = _strip_markup(value)

    record = (
        ec_number,
        code,
        TEXT_FIELD_LABELS.get(code),
        value,
        cleaned,
        _join(proteins),
        _join(references),
        _join(qualifiers),
    )
    buffer.clear()
    return iter((record,))


def _strip_markup(value: str) -> str:
    result = HASH_TOKEN_RE.sub(lambda m: m.group(1), value)
    result = ANGLE_TOKEN_RE.sub("", result)
    result = BRACE_TOKEN_RE.sub(lambda m: m.group(1), result)
    result = PAREN_TOKEN_RE.sub(lambda m: m.group(1), result)
    result = re.sub(r"\s+", " ", result)
    return result.strip()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
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
        );

        CREATE TABLE IF NOT EXISTS proteins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            protein_id TEXT,
            organism TEXT,
            comment TEXT,
            reference_ids TEXT,
            raw_json TEXT,
            FOREIGN KEY (ec_number) REFERENCES enzymes(ec_number)
        );

        CREATE TABLE IF NOT EXISTS enzyme_facts (
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
            raw_json TEXT,
            FOREIGN KEY (ec_number) REFERENCES enzymes(ec_number)
        );

        CREATE TABLE IF NOT EXISTS text_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ec_number TEXT NOT NULL,
            field_code TEXT NOT NULL,
            field_name TEXT,
            value_raw TEXT,
            value_text TEXT,
            protein_tokens TEXT,
            reference_tokens TEXT,
            qualifiers TEXT,
            FOREIGN KEY (ec_number) REFERENCES enzymes(ec_number)
        );
        """
    )


def _insert_enzyme(conn: sqlite3.Connection, rows: List[Tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT INTO enzymes (
            ec_number,
            enzyme_id,
            recommended_name,
            systematic_name,
            reaction_summary,
            protein_count,
            synonym_count,
            reaction_count,
            km_count,
            turnover_count,
            inhibitor_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_protein(conn: sqlite3.Connection, rows: List[Tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT INTO proteins (
            ec_number,
            protein_id,
            organism,
            comment,
            reference_ids,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_fact(conn: sqlite3.Connection, rows: List[Tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT INTO enzyme_facts (
            ec_number,
            category,
            value,
            value_numeric_low,
            value_numeric_high,
            unit,
            context,
            comment,
            proteins,
            reference_ids,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_text_fact(conn: sqlite3.Connection, rows: List[Tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT INTO text_facts (
            ec_number,
            field_code,
            field_name,
            value_raw,
            value_text,
            protein_tokens,
            reference_tokens,
            qualifiers
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_proteins_ec ON proteins (ec_number);
        CREATE INDEX IF NOT EXISTS idx_facts_ec ON enzyme_facts (ec_number);
        CREATE INDEX IF NOT EXISTS idx_facts_category ON enzyme_facts (category);
        CREATE INDEX IF NOT EXISTS idx_facts_value ON enzyme_facts (value);
        CREATE INDEX IF NOT EXISTS idx_text_ec ON text_facts (ec_number);
        CREATE INDEX IF NOT EXISTS idx_text_code ON text_facts (field_code);
        """
    )


def run_cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest BRENDA JSON into SQLite")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/brenda_2025_1.json"),
        help="Path to the BRENDA JSON file",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("data/processed/brenda.db"),
        help="Destination SQLite database",
    )
    parser.add_argument(
        "--text",
        type=Path,
        default=Path("data/raw/brenda_2025_1.txt"),
        help="Optional BRENDA text dump to enrich the database",
    )
    args = parser.parse_args()

    stats = ingest(args.source, args.target, args.text)
    top_categories = sorted(
        stats.category_counts.items(), key=lambda item: item[1], reverse=True
    )[:10]
    top_text = sorted(
        stats.text_field_counts.items(), key=lambda item: item[1], reverse=True
    )[:10]

    print(
        json.dumps(
            {
                "enzymes": stats.enzyme_count,
                "proteins": stats.protein_count,
                "facts": stats.fact_count,
                "text_facts": stats.text_fact_count,
                "top_categories": dict(top_categories),
                "top_text_fields": dict(top_text),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    run_cli()
