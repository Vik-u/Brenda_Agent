"""Download and parse open-access PDFs based on Unpaywall log."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List, Optional

import httpx
from pypdf import PdfReader

STATUS_LOG_DEFAULT = Path("artifacts/unpaywall_status.jsonl")
OUTPUT_DIR_DEFAULT = Path("artifacts/oa_pdfs")
SUMMARY_DEFAULT = Path("artifacts/oa_pdf_summary.json")

TIMEOUT = 60
MAX_WORKERS = 4
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PDF_CONTENT = "application/pdf"


def iter_candidate_records(path: Path) -> Iterable[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Unpaywall status log not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            url = record.get("best_oa_url")
            if not (record.get("is_oa") and url):
                continue
            if ".pdf" in url.lower():
                yield record


def fetch_url(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response


def extract_pdf_from_html(html: str) -> Optional[str]:
    match = re.search(r"citation_pdf_url\"\s+content=\"([^\"]+)\"", html, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"href=\"([^\"]+\.pdf)\"", html, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def obtain_pdf_bytes(client: httpx.Client, url: str) -> bytes:
    response = fetch_url(client, url)
    content_type = response.headers.get("content-type", "").lower()
    if PDF_CONTENT in content_type:
        return response.content
    if "text/html" in content_type:
        pdf_url = extract_pdf_from_html(response.text)
        if pdf_url:
            response = fetch_url(client, pdf_url)
            if PDF_CONTENT in response.headers.get("content-type", "").lower():
                return response.content
    raise ValueError("No PDF available at provided URL")


def extract_text_snippet(pdf_bytes: bytes, max_chars: int = 800) -> str:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)
        reader = PdfReader(str(tmp_path))
        text_parts: List[str] = []
        for page in reader.pages[:3]:
            text = page.extract_text() or ""
            if text:
                text_parts.append(text)
            if sum(len(part) for part in text_parts) >= max_chars:
                break
        snippet = " ".join("\n".join(text_parts).split())
        tmp_path.unlink(missing_ok=True)
        return snippet[:max_chars] if snippet else ""
    except Exception as exc:  # pragma: no cover
        return f"[parse-error] {exc}"


def download_and_parse(record: dict, output_dir: Path) -> dict:
    doi = record["doi"]
    url = record["best_oa_url"]
    filename = doi.replace("/", "_")
    pdf_path = output_dir / f"{filename}.pdf"
    text_path = output_dir / f"{filename}.txt"

    with httpx.Client(follow_redirects=True, timeout=TIMEOUT) as client:
        try:
            pdf_bytes = obtain_pdf_bytes(client, url)
            pdf_path.write_bytes(pdf_bytes)
            snippet = extract_text_snippet(pdf_bytes)
            text_path.write_text(snippet, encoding="utf-8")
            status = "success"
        except Exception as exc:
            pdf_path.unlink(missing_ok=True)
            text_path.unlink(missing_ok=True)
            status = f"error: {exc}"

    return {
        "doi": doi,
        "source_url": url,
        "pdf_path": str(pdf_path) if pdf_path.exists() else None,
        "text_path": str(text_path) if text_path.exists() else None,
        "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Download sample OA PDFs and extract snippets")
    parser.add_argument("--status-log", type=Path, default=STATUS_LOG_DEFAULT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR_DEFAULT)
    parser.add_argument("--summary", type=Path, default=SUMMARY_DEFAULT)
    parser.add_argument("--count", type=int, default=5, help="Number of PDFs to fetch")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = list(iter_candidate_records(args.status_log))
    if not candidates:
        raise RuntimeError("No OA entries with download URLs available; run unpaywall_coverage first.")

    selected = candidates[: args.count]

    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(download_and_parse, record, output_dir): record for record in selected}
        for future in as_completed(future_map):
            result = future.result()
            results.append(result)
            print(f"[{result['status']}] {result['doi']}")

    summary = {
        "requested": args.count,
        "attempted": len(selected),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": [r for r in results if r["status"] != "success"],
        "results": results,
    }

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
