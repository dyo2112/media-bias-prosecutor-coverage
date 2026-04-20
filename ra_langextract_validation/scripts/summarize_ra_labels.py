"""
Summarize completed RA coding sheets for the Step 08 validation workflow.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT / "ra_langextract_validation"
COMPLETED_DIR = BASE_DIR / "completed"
SUMMARY_DIR = BASE_DIR / "summary"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-dir", type=Path, default=COMPLETED_DIR)
    parser.add_argument("--summary-dir", type=Path, default=SUMMARY_DIR)
    return parser.parse_args()


def article_summary(df: pd.DataFrame) -> list[str]:
    lines = []
    lines.append("## 1. Article Validation")
    lines.append(f"- Rows: {len(df):,}")
    coded = df["ra_article_stance"].fillna("").ne("").sum()
    lines.append(f"- Rows with human stance labels: {coded:,}")

    if coded:
        stance_counts = df["ra_article_stance"].fillna("").value_counts()
        for label, count in stance_counts.items():
            if label:
                lines.append(f"- Human stance `{label}`: {count:,}")

    frame_coded = df["ra_dominant_frame"].fillna("").ne("").sum()
    lines.append(f"- Rows with human frame labels: {frame_coded:,}")
    return lines


def article_confusions(df: pd.DataFrame, outdir: Path) -> list[str]:
    lines = []
    valid = df[
        df["ra_article_stance"].fillna("").ne("")
        & df["model_stance_bucket"].fillna("").ne("")
    ].copy()
    if not valid.empty:
        valid["human_stance_for_compare"] = valid["ra_article_stance"].replace(
            {"neutral": "neutral_or_mixed", "mixed": "neutral_or_mixed"}
        )
        confusion = pd.crosstab(valid["human_stance_for_compare"], valid["model_stance_bucket"])
        confusion.to_csv(outdir / "01_article_stance_confusion.csv")
        match_rate = (
            valid["human_stance_for_compare"].eq(valid["model_stance_bucket"]).mean()
        )
        lines.append(f"- Article stance agreement after neutral/mixed collapse: {match_rate:.1%}")

    frame_valid = df[
        df["ra_dominant_frame"].fillna("").ne("")
        & df["dominant_frame"].fillna("").ne("")
    ].copy()
    if not frame_valid.empty:
        frame_confusion = pd.crosstab(frame_valid["ra_dominant_frame"], frame_valid["dominant_frame"])
        frame_confusion.to_csv(outdir / "01_article_frame_confusion.csv")
        frame_match = frame_valid["ra_dominant_frame"].eq(frame_valid["dominant_frame"]).mean()
        lines.append(f"- Dominant-frame exact match rate: {frame_match:.1%}")
    return lines


def extraction_summary(df: pd.DataFrame) -> list[str]:
    lines = []
    lines.append("## 2. Extraction Review")
    lines.append(f"- Rows: {len(df):,}")
    for col, label in [
        ("ra_present_in_text", "present-in-text"),
        ("ra_class_correct", "class-correct"),
        ("ra_attribute_correct", "attribute-correct"),
    ]:
        coded = df[col].fillna("").ne("").sum()
        lines.append(f"- Rows with `{label}` coding: {coded:,}")
        if coded:
            counts = df[col].fillna("").value_counts()
            for value, count in counts.items():
                if value:
                    lines.append(f"- `{col} = {value}`: {count:,}")

    if "ra_ambiguity_type" in df.columns:
        ambiguity = df["ra_ambiguity_type"].fillna("")
        ambiguity = ambiguity[ambiguity.ne("")]
        if not ambiguity.empty:
            lines.append("- Top ambiguity types:")
            for label, count in ambiguity.value_counts().head(10).items():
                lines.append(f"- `{label}`: {count:,}")
    return lines


def extraction_tables(df: pd.DataFrame, outdir: Path) -> None:
    for col in ["ra_present_in_text", "ra_class_correct", "ra_attribute_correct"]:
        sub = df[df[col].fillna("").ne("")]
        if sub.empty:
            continue
        table = pd.crosstab(sub["sample_bucket"], sub[col])
        table.to_csv(outdir / f"02_{col}_by_bucket.csv")


def case_summary(df: pd.DataFrame, outdir: Path) -> list[str]:
    lines = []
    lines.append("## 3. Case-Type Coding")
    lines.append(f"- Rows: {len(df):,}")
    coded = df["ra_case_type_binary"].fillna("").ne("").sum()
    lines.append(f"- Rows with binary case-type coding: {coded:,}")

    if coded:
        counts = df["ra_case_type_binary"].fillna("").value_counts()
        for label, count in counts.items():
            if label:
                lines.append(f"- Binary case type `{label}`: {count:,}")

        ctab = pd.crosstab(df["prosecutor_type"], df["ra_case_type_binary"])
        ctab.to_csv(outdir / "03_case_type_by_prosecutor_type.csv")
    return lines


def load_optional(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def main() -> None:
    args = parse_args()
    args.summary_dir.mkdir(parents=True, exist_ok=True)

    article_path = args.completed_dir / "01_article_validation_completed.csv"
    extraction_path = args.completed_dir / "02_extraction_review_completed.csv"
    case_path = args.completed_dir / "03_case_type_coding_completed.csv"

    report_lines = ["# RA Validation Summary", ""]

    article_df = load_optional(article_path)
    if article_df is not None:
        report_lines.extend(article_summary(article_df))
        report_lines.extend(article_confusions(article_df, args.summary_dir))
        report_lines.append("")

    extraction_df = load_optional(extraction_path)
    if extraction_df is not None:
        report_lines.extend(extraction_summary(extraction_df))
        extraction_tables(extraction_df, args.summary_dir)
        report_lines.append("")

    case_df = load_optional(case_path)
    if case_df is not None:
        report_lines.extend(case_summary(case_df, args.summary_dir))
        report_lines.append("")

    if len(report_lines) == 2:
        report_lines.append("No completed coding files were found in `completed/`.")

    out_path = args.summary_dir / "ra_validation_summary.md"
    out_path.write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote summary to {out_path}")


if __name__ == "__main__":
    main()
