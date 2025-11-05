"""Generate statistics and visualisations for PubMed-linked BRENDA references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Dict, List

import matplotlib.pyplot as plt

REFERENCES_DEFAULT = Path("artifacts/pubmed_references.json")
LINKS_DEFAULT = Path("artifacts/pubmed_links.json")
OUTPUT_DIR_DEFAULT = Path("artifacts/figures")
SUMMARY_PATH_DEFAULT = Path("artifacts/figures/pubmed_stats_summary.json")


def load_json(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text())


def compute_reference_stats(data: Dict) -> Dict:
    counts: List[int] = [len(enzyme.get("references", [])) for enzyme in data.get("enzymes", [])]
    counts = [c for c in counts if c is not None]
    if not counts:
        return {
            "reference_counts": counts,
            "total_enzymes": 0,
            "total_references": 0,
        }
    counts_sorted = sorted(counts)
    return {
        "reference_counts": counts,
        "total_enzymes": len(counts),
        "total_references": sum(counts),
        "min": counts_sorted[0],
        "median": median(counts_sorted),
        "mean": mean(counts_sorted),
        "p90": counts_sorted[int(0.9 * (len(counts_sorted) - 1))],
        "p99": counts_sorted[int(0.99 * (len(counts_sorted) - 1))],
        "max": counts_sorted[-1],
    }


def compute_pubmed_stats(data: Dict) -> Dict:
    articles = data.get("articles", [])
    ec_counts = [len(article.get("linked_ec_numbers", [])) for article in articles]
    doi_flags = [bool(article.get("doi")) for article in articles]

    ec_counts_sorted = sorted(ec_counts)
    total = len(ec_counts)
    with_doi = sum(doi_flags)

    return {
        "ec_counts": ec_counts,
        "total_articles": total,
        "min_ec": ec_counts_sorted[0] if ec_counts_sorted else 0,
        "median_ec": median(ec_counts_sorted) if ec_counts_sorted else 0,
        "mean_ec": mean(ec_counts_sorted) if ec_counts_sorted else 0,
        "p90_ec": ec_counts_sorted[int(0.9 * (len(ec_counts_sorted) - 1))] if ec_counts_sorted else 0,
        "p99_ec": ec_counts_sorted[int(0.99 * (len(ec_counts_sorted) - 1))] if ec_counts_sorted else 0,
        "max_ec": ec_counts_sorted[-1] if ec_counts_sorted else 0,
        "with_doi": with_doi,
        "doi_fraction": (with_doi / total) if total else 0,
    }


def plot_histogram(data: List[int], *, title: str, xlabel: str, output_path: Path, bins: int = 50, logy: bool = True, xlim: int | None = None) -> None:
    if not data:
        return
    plt.figure(figsize=(10, 6))
    display_data = data
    if xlim is not None:
        display_data = [value for value in data if value <= xlim]
    plt.hist(display_data, bins=bins)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Count")
    if logy:
        plt.yscale("log")
    if xlim is not None:
        plt.xlim(0, xlim)
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute stats and plots for PubMed references")
    parser.add_argument("--references", type=Path, default=REFERENCES_DEFAULT)
    parser.add_argument("--links", type=Path, default=LINKS_DEFAULT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR_DEFAULT)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH_DEFAULT)
    args = parser.parse_args()

    references_data = load_json(args.references)
    links_data = load_json(args.links)

    ref_stats = compute_reference_stats(references_data)
    pubmed_stats = compute_pubmed_stats(links_data)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_histogram(
        ref_stats.get("reference_counts", []),
        title="Distribution of references per EC number",
        xlabel="Number of reference records",
        output_path=output_dir / "references_per_ec_hist_log.png",
        bins=50,
        logy=True,
    )

    plot_histogram(
        ref_stats.get("reference_counts", []),
        title="Distribution of references per EC number (<=200)",
        xlabel="Number of reference records",
        output_path=output_dir / "references_per_ec_hist_linear.png",
        bins=50,
        logy=False,
        xlim=200,
    )

    plot_histogram(
        pubmed_stats.get("ec_counts", []),
        title="Distribution of EC numbers linked per PubMed ID",
        xlabel="Number of EC numbers",
        output_path=output_dir / "ec_per_pubmed_hist_log.png",
        bins=50,
        logy=True,
    )

    plot_histogram(
        pubmed_stats.get("ec_counts", []),
        title="Distribution of EC numbers linked per PubMed ID (<=25)",
        xlabel="Number of EC numbers",
        output_path=output_dir / "ec_per_pubmed_hist_linear.png",
        bins=25,
        logy=False,
        xlim=25,
    )

    summary = {
        "references": {k: v for k, v in ref_stats.items() if k != "reference_counts"},
        "pubmed": {k: v for k, v in pubmed_stats.items() if k != "ec_counts"},
        "figure_dir": str(output_dir.resolve()),
    }

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
