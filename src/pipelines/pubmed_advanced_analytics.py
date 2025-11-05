"""Advanced analytics and visualisations for PubMed-linked enzyme data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

REFERENCES_DEFAULT = Path("artifacts/pubmed_references.json")
OUTPUT_DIR_DEFAULT = Path("artifacts/figures/advanced")
SUMMARY_DEFAULT = Path("artifacts/figures/advanced/pubmed_advanced_summary.json")

sns.set_theme(style="whitegrid")


def load_references(path: Path) -> pd.DataFrame:
    raw = json.loads(path.read_text())
    records = []
    for enzyme in raw.get("enzymes", []):
        refs = enzyme.get("references", [])
        pubmed_ids = set()
        for ref in refs:
            pubmed_ids.update(ref.get("pubmed_ids", []))
        reference_records = len(refs)
        unique_pubmed = len(pubmed_ids)
        protein_count = enzyme.get("protein_count") or 0
        synonym_count = enzyme.get("synonym_count") or 0
        refs_per_pubmed = reference_records / unique_pubmed if unique_pubmed else 0
        pubmed_per_protein = unique_pubmed / protein_count if protein_count else 0
        records.append(
            {
                "ec_number": enzyme.get("ec_number"),
                "reference_records": reference_records,
                "unique_pubmed_ids": unique_pubmed,
                "protein_count": protein_count,
                "synonym_count": synonym_count,
                "refs_per_pubmed": refs_per_pubmed,
                "pubmed_per_protein": pubmed_per_protein,
            }
        )
    df = pd.DataFrame.from_records(records)
    return df


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def scatter_reference_vs_protein(df: pd.DataFrame, output: Path) -> None:
    plt.figure(figsize=(10, 7))
    scatter = sns.scatterplot(
        data=df,
        x="protein_count",
        y="reference_records",
        hue="refs_per_pubmed",
        size="unique_pubmed_ids",
        palette="viridis",
        sizes=(20, 200),
        alpha=0.7,
        edgecolor="none",
    )
    scatter.set_xscale("log")
    scatter.set_yscale("log")
    scatter.set_xlabel("Protein annotations (log scale)")
    scatter.set_ylabel("Reference records per EC (log scale)")
    scatter.set_title("Reference depth vs protein annotations per EC")
    plt.legend(loc="upper left", bbox_to_anchor=(1.05, 1))
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def kde_pubmed_reference(df: pd.DataFrame, output: Path) -> None:
    plt.figure(figsize=(9, 7))
    sns.kdeplot(
        data=df,
        x="unique_pubmed_ids",
        y="reference_records",
        cmap="mako",
        fill=True,
        thresh=0.05,
    )
    plt.xlabel("Unique PubMed IDs per EC")
    plt.ylabel("Reference records per EC")
    plt.title("Density of references vs unique PubMed IDs")
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def pairplot_features(df: pd.DataFrame, output: Path) -> None:
    subset = df[[
        "reference_records",
        "unique_pubmed_ids",
        "protein_count",
        "synonym_count",
        "refs_per_pubmed",
    ]]
    sns.pairplot(subset, corner=True, diag_kind="kde", plot_kws={"alpha": 0.3, "s": 20})
    plt.suptitle("Pairwise relationships across enzyme reference features", y=1.02)
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def correlation_heatmap(df: pd.DataFrame, output: Path) -> None:
    numeric_df = df[[
        "reference_records",
        "unique_pubmed_ids",
        "protein_count",
        "synonym_count",
        "refs_per_pubmed",
        "pubmed_per_protein",
    ]]
    corr = numeric_df.corr(method="spearman")
    plt.figure(figsize=(8, 6))
    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        vmin=-1,
        vmax=1,
        linewidths=0.5,
    )
    plt.title("Spearman correlation across enzyme reference features")
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def compute_summary(df: pd.DataFrame) -> dict:
    return {
        "rows": int(df.shape[0]),
        "reference_records": {
            "min": float(df["reference_records"].min()),
            "median": float(df["reference_records"].median()),
            "mean": float(df["reference_records"].mean()),
            "max": float(df["reference_records"].max()),
        },
        "unique_pubmed_ids": {
            "min": float(df["unique_pubmed_ids"].min()),
            "median": float(df["unique_pubmed_ids"].median()),
            "mean": float(df["unique_pubmed_ids"].mean()),
            "max": float(df["unique_pubmed_ids"].max()),
        },
        "protein_count": {
            "min": float(df["protein_count"].min()),
            "median": float(df["protein_count"].median()),
            "mean": float(df["protein_count"].mean()),
            "max": float(df["protein_count"].max()),
        },
        "synonym_count": {
            "min": float(df["synonym_count"].min()),
            "median": float(df["synonym_count"].median()),
            "mean": float(df["synonym_count"].mean()),
            "max": float(df["synonym_count"].max()),
        },
        "refs_per_pubmed": {
            "min": float(df["refs_per_pubmed"].min()),
            "median": float(df["refs_per_pubmed"].median()),
            "mean": float(df["refs_per_pubmed"].mean()),
            "max": float(df["refs_per_pubmed"].max()),
        },
        "pubmed_per_protein": {
            "min": float(df["pubmed_per_protein"].min()),
            "median": float(df["pubmed_per_protein"].median()),
            "mean": float(df["pubmed_per_protein"].mean()),
            "max": float(df["pubmed_per_protein"].max()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Advanced analytics for PubMed references")
    parser.add_argument("--references", type=Path, default=REFERENCES_DEFAULT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR_DEFAULT)
    parser.add_argument("--summary", type=Path, default=SUMMARY_DEFAULT)
    args = parser.parse_args()

    df = load_references(args.references)
    ensure_output_dir(args.output_dir)

    scatter_reference_vs_protein(df, args.output_dir / "scatter_refs_vs_protein.png")
    kde_pubmed_reference(df, args.output_dir / "kde_refs_vs_pubmed.png")
    pairplot_features(df, args.output_dir / "pairplot_reference_features.png")
    correlation_heatmap(df, args.output_dir / "correlation_heatmap.png")

    summary = compute_summary(df)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
