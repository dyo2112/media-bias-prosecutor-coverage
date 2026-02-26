"""
Step 2: Filter articles to only those related to crime and criminal justice.

Two-stage approach:
  Stage 1 — Fast keyword pre-filter (eliminates ~50-60% of articles)
  Stage 2 — Zero-shot classification on remaining candidates

Input:  output/01_clean.parquet
Output: output/02_relevant.parquet

Adds columns: keyword_score, zeroshot_crime_score, is_relevant
"""

import argparse
import re
import sys

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import (
    CLEAN_PARQUET,
    RELEVANT_PARQUET,
    CRIME_JUSTICE_KEYWORDS,
    ZEROSHOT_MODEL,
    ZEROSHOT_MODEL_LIGHT,
    BATCH_SIZE,
    MAX_TOKENS_RELEVANCE,
    OUTPUT_DIR,
)
from utils import (
    setup_logging,
    load_parquet,
    save_parquet,
    truncate_words,
    timer,
    logger,
)


# ── Stage 1: keyword pre-filter ───────────────────────────────────────────

def keyword_score(text: str) -> int:
    """Count how many distinct crime/justice keywords appear in text."""
    text_lower = text.lower()
    score = 0
    for kw in CRIME_JUSTICE_KEYWORDS:
        # Use word boundary matching for short keywords to avoid false matches
        if len(kw) <= 3:
            if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                score += 1
        else:
            if kw in text_lower:
                score += 1
    return score


def stage1_keyword_filter(df: pd.DataFrame, threshold: int = 2) -> pd.DataFrame:
    """Score all articles by keyword count; return those >= threshold."""
    with timer("Stage 1: Keyword scoring"):
        tqdm.pandas(desc="Keyword scoring")
        df["keyword_score"] = df["clean_text"].progress_apply(keyword_score)

    n_pass = (df["keyword_score"] >= threshold).sum()
    n_fail = len(df) - n_pass
    logger.info(
        f"Keyword filter: {n_pass:,} pass (>={threshold} keywords), "
        f"{n_fail:,} rejected"
    )
    logger.info(f"Score distribution:\n{df['keyword_score'].describe()}")

    return df


# ── Stage 2: zero-shot classification ─────────────────────────────────────

def stage2_zeroshot(
    df: pd.DataFrame,
    keyword_threshold: int = 2,
    confidence_threshold: float = 0.5,
    use_light_model: bool = False,
    checkpoint_every: int = 5000,
) -> pd.DataFrame:
    """Run zero-shot classification on keyword-passing articles.

    Articles below keyword_threshold skip classification and are marked
    not relevant. Articles above are classified; those with crime confidence
    above confidence_threshold are kept.
    """
    from transformers import pipeline as hf_pipeline

    model_name = ZEROSHOT_MODEL_LIGHT if use_light_model else ZEROSHOT_MODEL

    with timer(f"Loading zero-shot model ({model_name})"):
        classifier = hf_pipeline(
            "zero-shot-classification",
            model=model_name,
            device=-1,  # CPU
        )

    candidate_labels = ["crime and criminal justice", "other news topic"]

    # Initialize score column
    df["zeroshot_crime_score"] = np.nan

    # Only classify articles that passed keyword filter
    mask = df["keyword_score"] >= keyword_threshold
    candidates = df.loc[mask].copy()
    logger.info(f"Running zero-shot on {len(candidates):,} candidate articles")

    # Prepare truncated texts (first ~200 words for speed)
    texts = candidates["full_text"].apply(
        lambda t: truncate_words(t, MAX_TOKENS_RELEVANCE)
    ).tolist()

    # Run in batches with checkpointing
    scores = []
    checkpoint_path = OUTPUT_DIR / "02_zeroshot_checkpoint.parquet"

    # Check for existing checkpoint
    start_idx = 0
    if checkpoint_path.exists():
        ckpt = pd.read_parquet(checkpoint_path)
        if "zeroshot_crime_score" in ckpt.columns:
            existing_scores = ckpt["zeroshot_crime_score"].dropna()
            start_idx = len(existing_scores)
            scores = existing_scores.tolist()
            logger.info(f"Resuming from checkpoint: {start_idx:,} already processed")

    with timer("Stage 2: Zero-shot classification"):
        for i in tqdm(
            range(start_idx, len(texts), BATCH_SIZE),
            desc="Zero-shot",
            initial=start_idx // BATCH_SIZE,
            total=len(texts) // BATCH_SIZE + 1,
        ):
            batch = texts[i : i + BATCH_SIZE]
            try:
                results = classifier(
                    batch,
                    candidate_labels=candidate_labels,
                    multi_label=False,
                )
                if isinstance(results, dict):
                    results = [results]

                for r in results:
                    # Score for "crime and criminal justice"
                    crime_idx = r["labels"].index("crime and criminal justice")
                    scores.append(r["scores"][crime_idx])

            except Exception as e:
                logger.error(f"Error at batch {i}: {e}")
                # Fill with NaN for this batch
                scores.extend([np.nan] * len(batch))

            # Checkpoint periodically
            if (i + BATCH_SIZE) % checkpoint_every < BATCH_SIZE:
                _save_checkpoint(candidates, scores, checkpoint_path)

    # Assign scores back
    df.loc[mask, "zeroshot_crime_score"] = scores[: mask.sum()]

    # Articles that failed keyword filter get score 0
    df.loc[~mask, "zeroshot_crime_score"] = 0.0

    # Mark relevance
    df["is_relevant"] = (
        (df["keyword_score"] >= keyword_threshold)
        & (df["zeroshot_crime_score"] >= confidence_threshold)
    )

    n_relevant = df["is_relevant"].sum()
    logger.info(
        f"Relevant articles: {n_relevant:,} / {len(df):,} "
        f"({100 * n_relevant / len(df):.1f}%)"
    )

    # Clean up checkpoint
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    return df


def _save_checkpoint(candidates: pd.DataFrame, scores: list, path):
    """Save intermediate zero-shot scores."""
    ckpt = candidates.iloc[: len(scores)].copy()
    ckpt["zeroshot_crime_score"] = scores
    ckpt[["article_id", "zeroshot_crime_score"]].to_parquet(path, index=False)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="Filter articles for crime/justice relevance")
    parser.add_argument(
        "--light-model", action="store_true",
        help="Use lighter/faster distilBART model instead of BART-large",
    )
    parser.add_argument(
        "--keyword-threshold", type=int, default=2,
        help="Minimum keyword score to pass to zero-shot stage (default: 2)",
    )
    parser.add_argument(
        "--confidence-threshold", type=float, default=0.5,
        help="Minimum zero-shot confidence for crime/justice (default: 0.5)",
    )
    parser.add_argument(
        "--keyword-only", action="store_true",
        help="Skip zero-shot classification and use only keyword filter",
    )
    args = parser.parse_args()

    # Load cleaned data
    df = load_parquet(CLEAN_PARQUET)

    # Stage 1: keyword scoring
    df = stage1_keyword_filter(df, threshold=args.keyword_threshold)

    if args.keyword_only:
        # If skipping zero-shot, mark all keyword-passing articles as relevant
        df["zeroshot_crime_score"] = np.nan
        df["is_relevant"] = df["keyword_score"] >= args.keyword_threshold
        n_relevant = df["is_relevant"].sum()
        logger.info(f"Keyword-only mode: {n_relevant:,} relevant articles")
    else:
        # Stage 2: zero-shot classification
        df = stage2_zeroshot(
            df,
            keyword_threshold=args.keyword_threshold,
            confidence_threshold=args.confidence_threshold,
            use_light_model=args.light_model,
        )

    # Save only relevant articles (but keep scores for all in a separate file)
    save_parquet(df, OUTPUT_DIR / "02_all_with_scores.parquet")

    relevant = df[df["is_relevant"]].copy()
    save_parquet(relevant, RELEVANT_PARQUET)

    # Print sample of rejected articles for manual inspection
    rejected = df[~df["is_relevant"]].sample(min(10, (~df["is_relevant"]).sum()), random_state=42)
    logger.info("\n── Sample REJECTED articles ──")
    for _, row in rejected.iterrows():
        logger.info(f"  [{row['keyword_score']:.0f} kw, {row.get('zeroshot_crime_score', 'N/A')} zs] "
                     f"{row['headline'][:100]}")

    # Print sample of accepted articles
    accepted = df[df["is_relevant"]].sample(min(10, df["is_relevant"].sum()), random_state=42)
    logger.info("\n── Sample ACCEPTED articles ──")
    for _, row in accepted.iterrows():
        logger.info(f"  [{row['keyword_score']:.0f} kw, {row['zeroshot_crime_score']:.2f} zs] "
                     f"{row['headline'][:100]}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
