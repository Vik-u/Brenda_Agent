"""Utilities for fetching PubMed article metadata and generating clean HTML snippets."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, List, Optional

import httpx


class PubMedFetchError(RuntimeError):
    """Raised when repeated attempts to fetch a batch fail."""

PUBMED_BASE_URL = "https://pubmed.ncbi.nlm.nih.gov"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BATCH_SIZE = 200
REQUEST_DELAY_SECONDS = 0.2  # within NCBI recommendation (<=3 requests/sec)
HTTP_TIMEOUT_SECONDS = 30


@dataclass
class PubMedArticle:
    pubmed_id: str
    title: str
    abstract: str
    journal: str | None
    publication_date: str | None
    doi: str | None
    authors: List[str]
    clean_html: str

    @property
    def pubmed_url(self) -> str:
        return f"{PUBMED_BASE_URL}/{self.pubmed_id}/"

    @property
    def doi_url(self) -> Optional[str]:
        if not self.doi:
            return None
        doi = self.doi.lower().removeprefix("doi:").strip()
        if not doi:
            return None
        return f"https://doi.org/{doi}"


def chunked(iterable: Iterable[str], size: int) -> Iterable[List[str]]:
    batch: List[str] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def fetch_batch(pmids: List[str], *, timeout: int = HTTP_TIMEOUT_SECONDS) -> List[PubMedArticle]:
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    response = httpx.get(EFETCH_URL, params=params, timeout=timeout)
    response.raise_for_status()
    return parse_articles(response.text)


def parse_articles(xml_payload: str) -> List[PubMedArticle]:
    root = ET.fromstring(xml_payload)
    articles: List[PubMedArticle] = []

    for article in root.findall(".//PubmedArticle"):
        pmid = _extract_text(article, ".//PMID")
        title = _coalesce_whitespace(_extract_text(article, ".//ArticleTitle"))
        abstract = _extract_abstract(article)
        journal = _coalesce_whitespace(_extract_text(article, ".//Journal/Title"))
        publication_date = _extract_publication_date(article)
        doi = _extract_doi(article)
        authors = _extract_authors(article)

        clean_html = _build_clean_html(
            pmid=pmid,
            title=title,
            abstract=abstract,
            journal=journal,
            publication_date=publication_date,
            doi=doi,
            authors=authors,
        )

        articles.append(
            PubMedArticle(
                pubmed_id=pmid,
                title=title,
                abstract=abstract,
                journal=journal,
                publication_date=publication_date,
                doi=doi,
                authors=authors,
                clean_html=clean_html,
            )
        )

    return articles


def _extract_text(node: ET.Element, xpath: str) -> str:
    element = node.find(xpath)
    return element.text if element is not None and element.text else ""


def _coalesce_whitespace(value: str) -> str:
    return " ".join(value.split()) if value else ""


def _extract_abstract(article: ET.Element) -> str:
    abstract_texts = []
    for block in article.findall(".//Abstract/AbstractText"):
        label = block.attrib.get("Label")
        text_parts = [block.text or ""] + [child.text or "" for child in block]
        text = " ".join(part.strip() for part in text_parts if part)
        if not text:
            continue
        if label:
            abstract_texts.append(f"{label}: {text}")
        else:
            abstract_texts.append(text)
    return "\n\n".join(abstract_texts)


def _extract_publication_date(article: ET.Element) -> str:
    date_node = article.find(".//PubDate")
    if date_node is None:
        return ""
    year = _coalesce_whitespace(_extract_text(date_node, "Year"))
    month = _coalesce_whitespace(_extract_text(date_node, "Month"))
    day = _coalesce_whitespace(_extract_text(date_node, "Day"))
    components = [comp for comp in (year, month, day) if comp]
    return "-".join(components)


def _extract_doi(article: ET.Element) -> str | None:
    # Prefer explicit ArticleId entries
    for elem in article.findall(".//ArticleId"):
        if elem.attrib.get("IdType", "").lower() == "doi" and elem.text:
            return elem.text.strip()
    # Fallback to ELocationID when DOI stored there
    for elem in article.findall(".//ELocationID"):
        if elem.attrib.get("EIdType", "").lower() == "doi" and elem.text:
            return elem.text.strip()
    return None


def _extract_authors(article: ET.Element) -> List[str]:
    authors: List[str] = []
    for author in article.findall(".//Author"):
        last = _coalesce_whitespace(_extract_text(author, "LastName"))
        fore = _coalesce_whitespace(_extract_text(author, "ForeName"))
        collective = _coalesce_whitespace(_extract_text(author, "CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        if last or fore:
            authors.append(
                ", ".join(part for part in (last, fore) if part)
            )
    return authors


def _build_clean_html(
    *,
    pmid: str,
    title: str,
    abstract: str,
    journal: str | None,
    publication_date: str | None,
    doi: str | None,
    authors: List[str],
) -> str:
    citation_parts = [part for part in (journal, publication_date) if part]
    citation = " — ".join(citation_parts)
    authors_html = "" if not authors else "<p class=\"authors\">" + "; ".join(authors) + "</p>"
    doi_html = ""
    if doi:
        doi_clean = doi.lower().removeprefix("doi:").strip()
        doi_html = (
            f"<p class=\"doi\"><a href=\"https://doi.org/{doi_clean}\">DOI: {doi_clean}</a></p>"
        )
    abstract_html = "" if not abstract else f"<section class=\"abstract\"><h2>Abstract</h2><p>{abstract}</p></section>"

    return (
        f"<article data-pmid=\"{pmid}\">"
        f"<h1>{title}</h1>"
        f"<p class=\"citation\">{citation}</p>"
        f"{authors_html}"
        f"{doi_html}"
        f"{abstract_html}"
        f"</article>"
    )


def fetch_all(pmids: Iterable[str]) -> List[PubMedArticle]:
    articles: List[PubMedArticle] = []
    processed = 0
    pmid_list = list(pmids)
    total_batches = (len(pmid_list) + BATCH_SIZE - 1) // BATCH_SIZE
    for idx, batch in enumerate(chunked(pmid_list, BATCH_SIZE), start=1):
        for attempt in range(3):
            try:
                articles.extend(fetch_batch(batch))
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (429, 500, 502, 503, 504):
                    sleep_time = REQUEST_DELAY_SECONDS * (attempt + 1) * 5
                    print(
                        f"Retrying batch {idx}/{total_batches} after HTTP {status} (attempt {attempt + 1})"
                    )
                    time.sleep(sleep_time)
                    continue
                raise
            except httpx.TimeoutException:
                sleep_time = REQUEST_DELAY_SECONDS * (attempt + 1) * 5
                print(
                    f"Timeout fetching batch {idx}/{total_batches}; retrying (attempt {attempt + 1})"
                )
                time.sleep(sleep_time)
                continue
            else:
                break
        else:
            raise PubMedFetchError(f"Failed to fetch batch after retries: {batch[:5]}...")
        processed += len(batch)
        if idx % 10 == 0 or idx == total_batches:
            print(f"Fetched batches {idx}/{total_batches} ({processed} articles)")
        time.sleep(REQUEST_DELAY_SECONDS)
    return articles
