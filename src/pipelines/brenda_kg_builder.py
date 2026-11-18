"""CLI wrapper to build a lightweight KG from the BRENDA SQLite mirror."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.kg.builder import build_kg


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a BRENDA knowledge graph (SQLite).")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/processed/brenda.db"),
        help="Source SQLite database.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("data/processed/brenda_kg.db"),
        help="Target SQLite database for KG nodes/edges.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional row limit for fast iteration.",
    )
    parser.add_argument(
        "--include-text",
        action="store_true",
        help="Include text_facts nodes and reference edges.",
    )
    args = parser.parse_args()

    stats = build_kg(
        args.source,
        args.target,
        include_text=args.include_text,
        limit=args.limit,
    )
    print(f"KG build complete: nodes={stats.nodes}, edges={stats.edges}")


if __name__ == "__main__":
    main()
