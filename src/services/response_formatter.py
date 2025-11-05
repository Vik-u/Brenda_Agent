"""Human-friendly answer formatting using DSPy when available."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

try:  # Optional dependency: gracefully degrade when dspy is absent
    import dspy  # type: ignore
except ImportError:  # pragma: no cover - executed only when dspy missing
    dspy = None  # type: ignore

if dspy is not None:  # pragma: no branch - simple availability guard
    class FriendlyAnswerSignature(dspy.Signature):
        """Turn query + evidence into a warm, structured response."""

        question: str = dspy.InputField(desc="Original user question")
        sql_used: str = dspy.InputField(desc="SQL statements executed")
        evidence: str = dspy.InputField(desc="Tabular and reference highlights")
        draft: str = dspy.InputField(desc="Initial draft response")
        answer: str = dspy.OutputField(desc="Polished, human-friendly answer")
else:  # pragma: no cover - defined only when dspy missing
    FriendlyAnswerSignature = None  # type: ignore


@dataclass
class ResponseFormatter:
    model: str = "gpt-oss:20b"
    api_base: str = "http://localhost:11434"

    def __post_init__(self) -> None:
        if dspy is None or FriendlyAnswerSignature is None:
            # dspy not installed – skip formatter and fall back to raw draft text
            self._lm = None
            self._predictor = None
            return

        model_name = self.model
        if not model_name.startswith("ollama/"):
            model_name = f"ollama/{model_name}"
        self._lm = dspy.LM(model_name, api_base=self.api_base)
        dspy.configure(lm=self._lm)
        self._predictor = dspy.Predict(FriendlyAnswerSignature)

    def _build_evidence(self, rows: Iterable[dict], references: Iterable[dict]) -> str:
        row_lines: List[str] = []
        for row in list(rows)[:5]:
            pieces = []
            for key, value in row.items():
                if value in (None, "", "unknown"):
                    continue
                pieces.append(f"{key}: {value}")
            if pieces:
                row_lines.append("; ".join(pieces))
        ref_lines: List[str] = []
        for ref in list(references)[:5]:
            parts = [ref.get("reference") or ""]
            if ref.get("pubmed"):
                parts.append(f"PubMed:{ref['pubmed']}")
            entry = " — ".join(part for part in parts if part)
            if entry:
                ref_lines.append(entry)
        evidence_sections = []
        if row_lines:
            evidence_sections.append("Top rows:\n" + "\n".join(f"- {line}" for line in row_lines))
        if ref_lines:
            evidence_sections.append("References:\n" + "\n".join(f"- {line}" for line in ref_lines))
        return "\n\n".join(evidence_sections) if evidence_sections else "No tabular rows returned."

    def format(
        self,
        *,
        question: str,
        sql: List[str],
        rows: List[dict],
        references: List[dict],
        draft: str,
    ) -> Optional[str]:
        if not draft:
            return None
        if self._predictor is None:  # dspy unavailable – use raw draft
            return draft.strip() if draft else None

        sql_text = "\n".join(sql)
        evidence = self._build_evidence(rows, references)
        result = self._predictor(
            question=question,
            sql_used=sql_text,
            evidence=evidence,
            draft=draft,
        )
        answer = getattr(result, "answer", "")
        return answer.strip() if answer else None
