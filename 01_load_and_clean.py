"""
Step 1: Load the raw TSV corpus, clean, deduplicate, and save as Parquet.

Input:  24.07.29_complete_corpus_api_lexis_combined.tsv
Output: output/01_clean.parquet

Columns produced:
    article_id, date, headline, body, full_text, clean_text,
    byline, publication, publication_lower, source_file
"""

import pandas as pd
import numpy as np

from config import RAW_TSV, CLEAN_PARQUET, OUTPUT_DIR
from utils import setup_logging, save_parquet, clean_text, timer, logger


def main() -> None:
    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load raw TSV ───────────────────────────────────────────────────────
    with timer("Loading raw TSV"):
        # The TSV has an unnamed index column as column 0.
        # Body text is quoted and can span multiple lines, so use default
        # quoting (QUOTE_MINIMAL) to correctly parse multiline fields.
        df = pd.read_csv(
            RAW_TSV,
            sep="\t",
            dtype=str,
            on_bad_lines="skip",
        )
        logger.info(f"Raw rows loaded: {len(df):,}")
        logger.info(f"Columns: {list(df.columns)}")

    # ── Standardize column names ───────────────────────────────────────────
    # The first column is an unnamed row index from the original export
    cols = df.columns.tolist()
    if cols[0] == "" or cols[0].startswith("Unnamed"):
        df = df.drop(columns=[cols[0]])

    # Normalize to lowercase column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Ensure expected columns exist
    expected = {"date", "headline", "body", "publication"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected columns: {missing}. Got: {list(df.columns)}")

    logger.info(f"Columns after cleanup: {list(df.columns)}")

    # ── Drop rows with empty body ──────────────────────────────────────────
    n_before = len(df)
    df = df.dropna(subset=["body"])
    df = df[df["body"].str.strip().astype(bool)]
    logger.info(f"Dropped {n_before - len(df):,} rows with empty body")

    # ── Parse dates ────────────────────────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    n_bad_dates = df["date"].isna().sum()
    if n_bad_dates > 0:
        logger.warning(f"Dropping {n_bad_dates:,} rows with unparseable dates")
        df = df.dropna(subset=["date"])

    # ── Deduplicate ────────────────────────────────────────────────────────
    n_before = len(df)
    df = df.drop_duplicates(subset=["date", "headline", "publication"], keep="first")
    logger.info(f"Removed {n_before - len(df):,} duplicates")

    # ── Create text fields ─────────────────────────────────────────────────
    df["headline"] = df["headline"].fillna("").astype(str).str.strip()
    df["body"] = df["body"].fillna("").astype(str).str.strip()
    df["full_text"] = df["headline"] + " " + df["body"]
    df["clean_text"] = df["full_text"].apply(clean_text)

    # ── Normalize publication names ────────────────────────────────────────
    df["publication"] = df["publication"].fillna("unknown").astype(str).str.strip()
    df["publication_lower"] = df["publication"].str.lower()

    # ── Rename source column if present ────────────────────────────────────
    if "file" in df.columns:
        df = df.rename(columns={"file": "source_file"})
    else:
        df["source_file"] = "unknown"

    # Fill optional columns
    if "byline" not in df.columns:
        df["byline"] = ""
    df["byline"] = df["byline"].fillna("")

    # Drop section column if present (always empty)
    if "section" in df.columns:
        df = df.drop(columns=["section"])

    # ── Assign stable article IDs ──────────────────────────────────────────
    df = df.reset_index(drop=True)
    df["article_id"] = df.index

    # ── Select final columns ───────────────────────────────────────────────
    keep_cols = [
        "article_id", "date", "headline", "body", "full_text", "clean_text",
        "byline", "publication", "publication_lower", "source_file",
    ]
    df = df[keep_cols]

    # ── Summary stats ──────────────────────────────────────────────────────
    logger.info(f"Final article count: {len(df):,}")
    logger.info(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    logger.info(f"Publications: {df['publication'].nunique()}")
    logger.info(f"Top 10 publications:\n{df['publication'].value_counts().head(10)}")
    logger.info(f"Articles per year:\n{df['date'].dt.year.value_counts().sort_index()}")

    # ── Save ───────────────────────────────────────────────────────────────
    save_parquet(df, CLEAN_PARQUET)
    logger.info("Done.")


if __name__ == "__main__":
    main()
