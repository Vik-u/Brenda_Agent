#!/usr/bin/env python
"""Generate EC-class analytics, tables, and figures for the BRENDA dataset."""

from __future__ import annotations

import argparse
import json
import socket
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


EC_CLASS_LABELS: Dict[str, str] = {
    "1": "Oxidoreductases",
    "2": "Transferases",
    "3": "Hydrolases",
    "4": "Lyases",
    "5": "Isomerases",
    "6": "Ligases",
    "7": "Translocases",
}

NUMERIC_FACT_CATEGORIES = {
    "km_value": "Km value",
    "turnover_number": "Turnover number (kcat)",
    "specific_activity": "Specific activity",
    "ki_value": "Ki value",
    "ph_optimum": "pH optimum",
    "temperature_optimum": "Temperature optimum (°C)",
}

PLOT_DIR = Path("artifacts/figures/ec_classes")
SUMMARY_PATH = Path("artifacts/ec_class_summary.json")
SUMMARY_TABLE_PATH = Path("artifacts/ec_class_entity_summary.csv")


def _ensure_output_dirs() -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_dataframe(
    conn: sqlite3.Connection,
    query: str,
    params: Iterable = (),
) -> pd.DataFrame:
    return pd.read_sql_query(query, conn, params=list(params))

...
