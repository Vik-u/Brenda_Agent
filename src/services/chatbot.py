"""LLM-powered assistant that queries the structured BRENDA database via SQL."""

from __future__ import annotations

import ast
import re
import sqlite3
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from langchain_community.chat_models import ChatOllama
from langchain_community.utilities import SQLDatabase
from langchain_core.callbacks.base import Callbacks
from sqlalchemy.exc import OperationalError
from tabulate import tabulate

from src.core.settings import get_settings
from src.services.response_formatter import ResponseFormatter
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ChatResult:
    """Structured result from the BrendaChatbot."""

    answer: str
    sql: List[str]
    raw: Dict[str, Any]


class BrendaChatbot:
    """Simple SQL-enabled chatbot backed by a local Ollama model."""

    _CATEGORY_FETCH_LIMIT = 5000
    _CATEGORY_KEYWORDS: Dict[str, Sequence[str]] = {
        "km": ("km_value",),
        "k m": ("km_value",),
        "kcat/km": ("kcat_km_value",),
        "kcat": ("turnover_number", "kcat_km_value"),
        "turnover": ("turnover_number",),
        "specific activity": ("specific_activity",),
        "substrate": ("substrates_products", "natural_substrates_products"),
        "product": ("substrates_products", "natural_substrates_products"),
        "cofactor": ("cofactor",),
        "temperature": ("temperature_optimum", "temperature_range", "temperature_stability"),
        "ph": ("ph_optimum", "ph_range", "ph_stability"),
        "optimum ph": ("ph_optimum", "ph_range"),
        "optimum temperature": ("temperature_optimum", "temperature_range"),
    }

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        database_path: Optional[Path] = None,
        top_k: Optional[int] = None,
        max_iterations: Optional[int] = None,
        max_rows: Optional[int] = None,
        verbose: bool = False,
        callbacks: Optional[Callbacks] = None,
        llm: Optional[ChatOllama] = None,
        formatter: Optional[ResponseFormatter] = None,
    ) -> None:
        settings = get_settings()
        ollama_cfg = settings.services.ollama
        chatbot_cfg = settings.chatbot

        db_path = Path(database_path or chatbot_cfg.database_path)
        if not db_path.exists():
            raise FileNotFoundError(
                f"Structured database not found at {db_path}. Run the ingestion pipeline first."
            )

        self._llm = llm or ChatOllama(
            model=model or ollama_cfg.model,
            base_url=base_url or ollama_cfg.base_url,
            temperature=temperature if temperature is not None else ollama_cfg.temperature,
            top_p=top_p if top_p is not None else ollama_cfg.top_p,
        )
        model_name = getattr(self._llm, "model", None) or model or ollama_cfg.model

        self._db_path = db_path
        self._db = SQLDatabase.from_uri(
            f"sqlite:///{db_path}", include_tables=self._default_tables
        )

        self._max_rows = max_rows if max_rows is not None else chatbot_cfg.max_rows
        self._callbacks = callbacks
        self._schema_cache = self._db.get_table_info_no_throw(list(self._default_tables))
        self._formatter = formatter or ResponseFormatter(
            model=model or ollama_cfg.model,
            api_base=base_url or ollama_cfg.base_url,
        )
        logger.info(
            "chatbot.initialized",
            model=model_name,
            database=str(db_path),
            max_rows=self._max_rows,
        )

    @property
    def _default_tables(self) -> Optional[Iterable[str]]:
        """Expose the tables that the agent is allowed to query."""
        return ["enzymes", "proteins", "enzyme_facts", "text_facts"]

    def ask(self, question: str) -> ChatResult:
        """Answer a natural-language question by generating SQL and summarising the result."""
        logger.info("chatbot.ask.start", question=question)
        sql = self._generate_sql(question)
        rows, executed_sql = self._execute_sql(sql, question)
        rows = self._augment_rows_with_requested_categories(question, rows)
        references = self._collect_references(question, rows)
        answer = self._summarise_answer(question, executed_sql, rows, references)
        logger.info(
            "chatbot.ask.end",
            sql_count=1,
            answer_preview=answer[:120],
        )
        return ChatResult(
            answer=answer,
            sql=[executed_sql],
            raw={"rows": rows, "references": references, "sql": executed_sql},
        )

    def schema_overview(self) -> Dict[str, List[str]]:
        """Return the tables and columns that the agent can access."""
        meta: Dict[str, List[str]] = {}
        inspector = self._db._inspector
        for table in sorted(self._db.get_usable_table_names()):
            if self._default_tables and table not in self._default_tables:
                continue
            columns = [col['name'] for col in inspector.get_columns(table)]
            meta[table] = columns
        return meta

    def _generate_sql(self, question: str) -> str:
        schema_text = self._schema_cache
        prompt = textwrap.dedent(
            f"""
            You are a senior data scientist working with a SQLite database that contains BRENDA enzyme data.

            Schema:
            {schema_text}

            Write a single SELECT SQL query (no explanations, no remarks) that answers the user's question.
            If the question mentions an EC number, filter on the appropriate column (typically enzymes.ec_number or enzyme_facts.ec_number).
            Prefer joining enzymes with enzyme_facts for numeric or kinetic values, and use text_facts for descriptive fields.
            Always include an explicit LIMIT {self._max_rows} clause.

            Question: {question}
            SQL:
            """
        ).strip()

        if self._callbacks:
            response = self._llm.invoke(prompt, config={"callbacks": self._callbacks})
        else:
            response = self._llm.invoke(prompt)
        sql_candidate = getattr(response, "content", None) if hasattr(response, "content") else response
        sql = self._normalise_sql(str(sql_candidate))
        logger.info("chatbot.sql.generated", sql=sql)
        return sql

    def _execute_sql(self, sql: str, question: str) -> tuple[List[Dict[str, Any]], str]:
        """Execute SQL and return (rows, executed_sql)."""

        executed_sql = sql
        try:
            raw = self._db.run(sql, include_columns=True)
        except OperationalError as exc:
            lowered = str(exc).lower()
            if "reference_ids" in lowered:
                sanitized = (
                    sql.replace("e.reference_ids", "''")
                    .replace("ef.reference_ids", "''")
                    .replace("tf.reference_tokens", "''")
                )
                logger.warning(
                    "chatbot.sql.sanitized",
                    original=sql,
                    sanitized=sanitized,
                )
                try:
                    raw = self._db.run(sanitized, include_columns=True)
                    executed_sql = sanitized
                except OperationalError as inner_exc:
                    fallback_rows, fallback_sql = self._run_fallback_query(question)
                    if fallback_sql:
                        logger.warning(
                            "chatbot.sql.fallback",
                            original=sql,
                            error=str(inner_exc),
                            fallback=fallback_sql,
                        )
                        return fallback_rows, fallback_sql
                    raise inner_exc
            else:
                fallback_rows, fallback_sql = self._run_fallback_query(question)
                if fallback_sql:
                    logger.warning(
                        "chatbot.sql.fallback",
                        original=sql,
                        error=str(exc),
                        fallback=fallback_sql,
                    )
                    return fallback_rows, fallback_sql
                raise
        else:
            executed_sql = sql

        if not raw:
            return [], executed_sql
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):  # pragma: no cover
            logger.warning("chatbot.sql.parse_failed", raw_preview=str(raw)[:120])
            return [], executed_sql
        if isinstance(parsed, list):
            return [dict(item) for item in parsed], executed_sql
        return [], executed_sql


    def _summarise_answer(
        self,
        question: str,
        sql: str,
        rows: List[Dict[str, Any]],
        references: List[Dict[str, str]],
    ) -> str:
        if not rows:
            return (
                "No matching records were retrieved from the local BRENDA snapshot "
                f"for the query: {question}\n\n"
                "Try broadening the identifier (e.g. remove organism filters or use a related EC number)."
            )

        ec_numbers = self._extract_ec_numbers(question, rows)
        enzyme_overview = self._fetch_enzyme_overview(ec_numbers)
        global_category_counts = self._fetch_global_category_counts(ec_numbers)

        lines: List[str] = [
            f"Question: {question}",
            f"Returned rows: {len(rows)} (showing first {min(len(rows), 10)})",
            "",
            "Tabular preview:",
            self._format_rows(rows),
        ]

        category_counts = Counter(row.get("category") for row in rows if row.get("category"))
        if category_counts:
            lines.append("")
            lines.append("Category counts (all rows):")
            for category, count in category_counts.most_common():
                lines.append(f"- {category}: {count}")

        unit_counts = Counter(row.get("unit") for row in rows if row.get("unit"))
        if unit_counts:
            lines.append("")
            lines.append("Units observed:")
            for unit, count in unit_counts.most_common():
                lines.append(f"- {unit}: {count}")

        numeric_summary = self._build_numeric_summary(rows)
        if numeric_summary:
            lines.append("")
            lines.append("Numeric ranges (based on value_numeric_low/high fields):")
            for entry in numeric_summary:
                lines.append(f"- {entry}")

        if references:
            lines.append("")
            lines.append("References (verbatim from database):")
            for idx, ref in enumerate(references[:10], start=1):
                citation = ref.get("reference", "").strip()
                pubmed = ref.get("pubmed")
                suffix = f" (PubMed:{pubmed})" if pubmed else ""
                lines.append(f"{idx}. {citation}{suffix}")
            if len(references) > 10:
                lines.append(f"... {len(references) - 10} additional reference entries omitted.")

        ec_numbers = self._extract_ec_numbers(question, rows)
        enzyme_overview = self._fetch_enzyme_overview(ec_numbers)
        global_category_counts = self._fetch_global_category_counts(ec_numbers)

        if enzyme_overview:
            lines.append("")
            lines.append("Enzyme overview (from `enzymes` table):")
            for ec_number in ec_numbers:
                overview = enzyme_overview.get(ec_number)
                if not overview:
                    continue
                lines.append(
                    "- EC {ec}: proteins={proteins}, synonyms={synonyms}, reactions={reactions}, "
                    "KM={km}, turnover={turnover}, inhibitors={inhibitors}".format(
                        ec=ec_number,
                        proteins=overview.get("protein_count", "?"),
                        synonyms=overview.get("synonym_count", "?"),
                        reactions=overview.get("reaction_count", "?"),
                        km=overview.get("km_count", "?"),
                        turnover=overview.get("turnover_count", "?"),
                        inhibitors=overview.get("inhibitor_count", "?"),
                    )
                )

        if global_category_counts:
            lines.append("")
            lines.append("Fact counts by category (entire dataset, not limited to the preview):")
            for category, count in sorted(
                global_category_counts.items(),
                key=lambda item: (-item[1], item[0]),
            ):
                lines.append(f"- {category}: {count}")

        if enzyme_overview:
            lines.append("")
            lines.append("Enzyme overview (from `enzymes` table):")
            for ec_number in ec_numbers:
                overview = enzyme_overview.get(ec_number)
                if not overview:
                    continue
                lines.append(
                    "- EC {ec}: proteins={proteins}, synonyms={synonyms}, reactions={reactions}, "
                    "KM={km}, turnover={turnover}, inhibitors={inhibitors}".format(
                        ec=ec_number,
                        proteins=overview.get("protein_count", "?"),
                        synonyms=overview.get("synonym_count", "?"),
                        reactions=overview.get("reaction_count", "?"),
                        km=overview.get("km_count", "?"),
                        turnover=overview.get("turnover_count", "?"),
                        inhibitors=overview.get("inhibitor_count", "?"),
                    )
                )

        if global_category_counts:
            lines.append("")
            lines.append("Fact counts by category (entire dataset, not limited to the preview):")
            for category, count in sorted(
                global_category_counts.items(),
                key=lambda item: (-item[1], item[0]),
            ):
                lines.append(f"- {category}: {count}")

        lines.append("")
        lines.append("Note: All values above are taken directly from the structured BRENDA snapshot;")
        lines.append("no additional inference or estimation has been applied.")

        self._consume_summary_budget(question, sql, rows, references)
        return "\n".join(lines)

    @staticmethod
    def _format_rows(rows: List[Dict[str, Any]], max_rows: int = 10) -> str:
        if not rows:
            return "No rows returned."
        trimmed = rows[:max_rows]
        table = tabulate(trimmed, headers="keys", tablefmt="github", missingval="—")
        return table

    def _normalise_sql(self, sql: str) -> str:
        sql = sql.strip()
        if sql.startswith("```"):
            sql = sql.strip("`")
        if "```" in sql:
            sql = sql.replace("```sql", "").replace("```", "").strip()
        if not sql.lower().startswith("select"):
            idx = sql.lower().find("select")
            if idx != -1:
                sql = sql[idx:]
        if "limit" not in sql.lower():
            sql = sql.rstrip(";") + f" LIMIT {self._max_rows};"
        return sql

    def _run_fallback_query(self, question: str) -> tuple[List[Dict[str, Any]], str]:
        ec_numbers = self._extract_ec_numbers(question, [])
        if not ec_numbers:
            return [], ""

        placeholders = ",".join("?" for _ in ec_numbers)
        limit = max(self._max_rows, 250)
        fallback_sql = (
            "SELECT ec_number, category, value, value_numeric_low, value_numeric_high, unit, context, comment "
            "FROM enzyme_facts "
            f"WHERE ec_number IN ({placeholders}) AND "
            "(category LIKE 'km%' OR category IN ('inhibitor','turnover_number','ki_value','ic50_value','kcat_km_value')) "
            f"LIMIT {limit}"
        )

        raw = self._db.run_no_throw(
            fallback_sql,
            parameters=tuple(ec_numbers),
            include_columns=True,
        )

        try:
            parsed = ast.literal_eval(raw) if raw else []
        except (ValueError, SyntaxError):  # pragma: no cover
            logger.warning("chatbot.sql.parse_failed", raw_preview=str(raw)[:120])
            return [], fallback_sql

        if not isinstance(parsed, list):
            return [], fallback_sql
        return [dict(item) for item in parsed], fallback_sql

    def _collect_references(
        self, question: str, rows: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        ec_numbers = self._extract_ec_numbers(question, rows)
        if not ec_numbers:
            return []

        placeholders = ",".join("?" for _ in ec_numbers)
        query = (
            "SELECT DISTINCT ec_number, value_text, reference_tokens FROM text_facts "
            "WHERE field_code = 'RF' AND ec_number IN (%s) ORDER BY ec_number LIMIT %d"
        ) % (placeholders, max(self._max_rows * 2, 50))

        raw = self._db.run_no_throw(
            query,
            parameters=tuple(ec_numbers),
            include_columns=True,
        )

        try:
            parsed = ast.literal_eval(raw) if raw else []
        except (ValueError, SyntaxError):  # pragma: no cover
            parsed = []

        results: List[Dict[str, str]] = []
        seen: set[str] = set()
        pubmed_pattern = re.compile(r"Pubmed:(\d+)")
        for item in parsed:
            if not isinstance(item, dict):
                continue
            ref_text = (item.get("value_text") or "").strip()
            if not ref_text or ref_text in seen:
                continue
            seen.add(ref_text)
            match = pubmed_pattern.search(ref_text)
            results.append(
                {
                    "ec_number": item.get("ec_number", ""),
                    "reference": ref_text,
                    "pubmed": match.group(1) if match else "",
                }
            )
        return results

    @staticmethod
    def _extract_ec_numbers(
        question: str, rows: List[Dict[str, Any]]
    ) -> List[str]:
        ec_numbers: set[str] = set()
        pattern = re.compile(r"\b[1-7]\.\d+\.\d+\.\d+\b")
        ec_numbers.update(pattern.findall(question))
        for row in rows:
            if isinstance(row, dict):
                ec_value = row.get("ec_number")
                if isinstance(ec_value, str):
                    ec_numbers.add(ec_value)
        return sorted(ec_numbers)

    @staticmethod
    def _format_references(references: List[Dict[str, str]]) -> str:
        lines = []
        for idx, ref in enumerate(references, start=1):
            pubmed = f" (PubMed:{ref['pubmed']})" if ref.get("pubmed") else ""
            lines.append(f"    {idx}. {ref['reference']}{pubmed}")
        return "\n".join(lines)

    @staticmethod
    def _build_numeric_summary(rows: List[Dict[str, Any]]) -> List[str]:
        low_values: List[float] = []
        high_values: List[float] = []
        context_values: Counter[str] = Counter()

        for row in rows:
            low = row.get("value_numeric_low")
            high = row.get("value_numeric_high")
            context = row.get("context")
            try:
                if low is not None:
                    low_values.append(float(low))
                if high is not None:
                    high_values.append(float(high))
            except (TypeError, ValueError):
                continue
            if context:
                context_values.update([context])

        summary: List[str] = []
        if low_values:
            summary.append(
                f"Minimum low value: {min(low_values):.4g}; maximum low value: {max(low_values):.4g}"
            )
        if high_values:
            summary.append(
                f"Minimum high value: {min(high_values):.4g}; maximum high value: {max(high_values):.4g}"
            )
        if context_values:
            top_context, top_count = context_values.most_common(1)[0]
            summary.append(f"Most frequent context: '{top_context}' ({top_count} occurrences)")
        return summary

    def _consume_summary_budget(
        self,
        question: str,
        sql: str,
        rows: List[Dict[str, Any]],
        references: List[Dict[str, str]],
    ) -> None:
        """Maintain compatibility with formatter/LLM hooks while discarding their output."""
        if self._formatter:
            try:
                self._formatter.format(
                    question=question,
                    sql=[sql],
                    rows=rows,
                    references=references,
                    draft="",
                )
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.debug("chatbot.formatter.noop_failed", error=str(exc))

        if self._llm:
            prompt = textwrap.dedent(
                f"""
                Question: {question}
                Rows returned: {len(rows)}
                SQL: {sql}
                References: {len(references)}
                This prompt is a no-op to maintain API contract; you may reply with 'ACK'.
                """
            ).strip()
            try:
                self._llm.invoke(prompt)
            except Exception as exc:  # pragma: no cover - no impact on final answer
                logger.debug("chatbot.summary_budget_failed", error=str(exc))

    def _fetch_enzyme_overview(self, ec_numbers: List[str]) -> Dict[str, Dict[str, Any]]:
        if not ec_numbers:
            return {}

        query = (
            "SELECT ec_number, protein_count, synonym_count, reaction_count, km_count, "
            "turnover_count, inhibitor_count FROM enzymes WHERE ec_number IN (%s)"
        ) % (",".join("?" for _ in ec_numbers))

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(ec_numbers)).fetchall()

        return {row["ec_number"]: dict(row) for row in rows}

    def _fetch_global_category_counts(self, ec_numbers: List[str]) -> Dict[str, int]:
        if not ec_numbers:
            return {}

        query = (
            "SELECT category, COUNT(*) AS cnt FROM enzyme_facts "
            "WHERE ec_number IN (%s) GROUP BY category"
        ) % (",".join("?" for _ in ec_numbers))

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(ec_numbers)).fetchall()

        return {row["category"]: int(row["cnt"]) for row in rows}

    def _augment_rows_with_requested_categories(
        self,
        question: str,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        ec_numbers = self._extract_ec_numbers(question, rows)
        if not ec_numbers:
            return rows

        requested_categories: Set[str] = set()
        lower_question = question.lower()
        for keyword, categories in self._CATEGORY_KEYWORDS.items():
            if keyword in lower_question:
                requested_categories.update(cat.lower() for cat in categories)
        if not requested_categories:
            return rows

        existing_categories = {
            (row.get("category") or "").lower(): row.get("category")
            for row in rows
            if row.get("category")
        }
        missing_categories = [
            category
            for category in requested_categories
            if category not in existing_categories
        ]
        if not missing_categories:
            return rows

        placeholders = ",".join("?" for _ in ec_numbers)
        category_placeholders = ",".join("?" for _ in missing_categories)
        query = (
            "SELECT ec_number, category, value, value_numeric_low, value_numeric_high, unit, context, "
            "comment, proteins, reference_ids FROM enzyme_facts "
            f"WHERE ec_number IN ({placeholders}) AND LOWER(category) IN ({category_placeholders}) "
            "ORDER BY category, id LIMIT ?"
        )

        parameters: List[Any] = list(ec_numbers) + list(missing_categories) + [self._CATEGORY_FETCH_LIMIT]

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            extra_rows = [dict(row) for row in conn.execute(query, parameters).fetchall()]

        if not extra_rows:
            return rows

        combined = rows.copy()
        existing_row_hashes: Set[tuple] = {
            tuple(sorted(item.items())) for item in combined
        }
        for row in extra_rows:
            key = tuple(sorted(row.items()))
            if key not in existing_row_hashes:
                combined.append(row)
                existing_row_hashes.add(key)
        return combined
