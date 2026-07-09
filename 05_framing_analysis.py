"""
Step 5: Media frame detection — HOW prosecutors are framed in coverage.

This is novel analysis not attempted in the R code. Detects framing patterns
rather than just sentiment polarity.

Frame taxonomy:
  1. Accountability — "Prosecutor is responsible for [bad outcome]"
  2. Conflict — Disagreement between prosecutor and police/victims/community
  3. Consequences — Focus on policy outcomes (crime rates, case outcomes)
  4. Human interest — Individual victim/criminal stories
  5. Reform/ideology — Frames prosecutor through ideological lens

Input:  output/03_attributed.parquet
Output: output/05_frames.parquet

Adds columns: frame_accountability, frame_conflict, frame_consequences,
              frame_human_interest, frame_reform, dominant_frame
"""

import argparse
import re

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import (
    ATTRIBUTED_PARQUET,
    FRAMES_PARQUET,
    PROSECUTORS,
    ZEROSHOT_MODEL,
    ZEROSHOT_MODEL_LIGHT,
    BATCH_SIZE,
    MAX_TOKENS_SENTIMENT,
    OUTPUT_DIR,
)
from utils import (
    setup_logging,
    load_parquet,
    save_parquet,
    get_sentence_windows,
    truncate_words,
    timer,
    logger,
)

# ── Frame definitions for zero-shot classification ────────────────────────

FRAME_LABELS = {
    "accountability": (
        "The prosecutor is being held responsible or blamed for a negative outcome"
    ),
    "conflict": (
        "There is conflict or disagreement between the prosecutor and police, "
        "victims, or community members"
    ),
    "consequences": (
        "The focus is on the consequences or outcomes of the prosecutor's policies, "
        "such as crime rates or case results"
    ),
    "human_interest": (
        "The story focuses on a specific person's experience as a victim, defendant, "
        "or family member affected by the justice system"
    ),
    "reform": (
        "The prosecutor is described in terms of political ideology, reform agenda, "
        "progressive values, or being tough on crime versus lenient"
    ),
}

FRAME_NAMES = list(FRAME_LABELS.keys())
FRAME_DESCRIPTIONS = list(FRAME_LABELS.values())


# ── Keyword-based frame detection (fast fallback) ─────────────────────────

FRAME_KEYWORD_PATTERNS = {
    "accountability": [
        r"\bblame[ds]?\b", r"\bresponsible\b", r"\bfault\b",
        r"\bfailed?\b.*\bprosecutor", r"\bprosecutor.*\bfailed?\b",
        r"\baccountab", r"\bunder\s+fire\b",
    ],
    "conflict": [
        r"\bclash\b", r"\bdisagree", r"\bpushback\b", r"\boppose[ds]?\b",
        r"\bfrustrat", r"\btension\b", r"\brift\b", r"\bfeud\b",
        r"\bpolice.*\bprosecutor\b.*\b(?:clash|disagree|frustrat)",
        r"\bvictim.*\bprosecutor\b.*\b(?:anger|frustrat|upset)",
    ],
    "consequences": [
        r"\bcrime\s+rate", r"\bcrime\s+(?:up|down|rose|fell|increase|decrease)",
        r"\brecidivism\b", r"\bcase\s+outcome", r"\bresult(?:s|ed)\s+in\b",
        r"\bconsequence", r"\bimpact\b.*\bpolic",
    ],
    "human_interest": [
        r"\bfamily\s+(?:of|says|member)", r"\bvictim\s+(?:says|told|spoke)",
        r"\bmother\b.*\bkill", r"\bfather\b.*\bkill",
        r"\bsurviv(?:or|ed)\b", r"\bgrieving\b",
    ],
    "reform": [
        r"\bprogressive\s+prosecutor", r"\breform\s+prosecutor",
        r"\bprogressive\s+(?:da|district\s+attorney)",
        r"\btough\s+on\s+crime", r"\bsoft\s+on\s+crime",
        r"\bcriminal\s+justice\s+reform", r"\brestorative\s+justice",
        r"\bideolog", r"\bleft-leaning\b", r"\bliberal\s+prosecutor",
    ],
}


def keyword_frame_scores(text: str) -> dict[str, float]:
    """Score frames using keyword patterns. Returns dict of frame: score."""
    text_lower = text.lower()
    scores = {}
    for frame, patterns in FRAME_KEYWORD_PATTERNS.items():
        hits = sum(1 for p in patterns if re.search(p, text_lower))
        scores[frame] = min(hits / len(patterns), 1.0)  # normalize to [0, 1]
    return scores


# ── Zero-shot frame detection ─────────────────────────────────────────────

def zeroshot_frame_scores(
    df: pd.DataFrame,
    classifier,
) -> pd.DataFrame:
    """Classify frame for prosecutor-containing text excerpts.

    Returns DataFrame with frame_* columns (scores 0-1) and dominant_frame.
    """
    results = {f"frame_{f}": [] for f in FRAME_NAMES}
    results["dominant_frame"] = []
    # Records which instrument produced each row's scores: "zeroshot",
    # "keyword_fallback", or None — mixed-instrument rows were previously
    # indistinguishable downstream.
    results["frame_method"] = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Frame classification"):
        primary = row["primary_prosecutor"]
        if pd.isna(primary):
            for f in FRAME_NAMES:
                results[f"frame_{f}"].append(np.nan)
            results["dominant_frame"].append(None)
            results["frame_method"].append(None)
            continue

        p = next((p for p in PROSECUTORS if p.name == primary), None)
        if p is None:
            for f in FRAME_NAMES:
                results[f"frame_{f}"].append(np.nan)
            results["dominant_frame"].append(None)
            results["frame_method"].append(None)
            continue

        # Get context windows around prosecutor mentions
        windows = []
        for variant in p.name_variants + [p.name]:
            ws = get_sentence_windows(row["body"], variant, window_size=5)
            windows.extend(ws)
        # Order-preserving dedup (set() order varies by process hash seed)
        windows = list(dict.fromkeys(windows))

        if not windows:
            # Fallback to keyword-based scoring
            kw_scores = keyword_frame_scores(row["body"])
            for f in FRAME_NAMES:
                results[f"frame_{f}"].append(kw_scores.get(f, 0.0))
            dominant = max(kw_scores, key=kw_scores.get) if any(kw_scores.values()) else None
            results["dominant_frame"].append(dominant)
            results["frame_method"].append("keyword_fallback")
            continue

        # Combine windows into one text, truncate
        combined = " ".join(windows[:5])
        combined = truncate_words(combined, MAX_TOKENS_SENTIMENT)

        try:
            result = classifier(
                combined,
                candidate_labels=FRAME_DESCRIPTIONS,
                multi_label=True,  # articles can have multiple frames
            )

            # Map scores back to frame names
            frame_scores = {}
            for label, score in zip(result["labels"], result["scores"]):
                idx = FRAME_DESCRIPTIONS.index(label)
                frame_name = FRAME_NAMES[idx]
                frame_scores[frame_name] = score

            for f in FRAME_NAMES:
                results[f"frame_{f}"].append(frame_scores.get(f, 0.0))

            dominant = max(frame_scores, key=frame_scores.get)
            results["dominant_frame"].append(dominant)
            results["frame_method"].append("zeroshot")

        except Exception as e:
            logger.warning(f"Frame error for article {row['article_id']}: {e}")
            # Fallback to keywords
            kw_scores = keyword_frame_scores(row["body"])
            for f in FRAME_NAMES:
                results[f"frame_{f}"].append(kw_scores.get(f, 0.0))
            dominant = max(kw_scores, key=kw_scores.get) if any(kw_scores.values()) else None
            results["dominant_frame"].append(dominant)
            results["frame_method"].append("keyword_fallback")

    n_fallback = sum(1 for m in results["frame_method"] if m == "keyword_fallback")
    logger.info(f"Keyword-fallback rows: {n_fallback:,} of {len(df):,}")
    return pd.DataFrame(results, index=df.index)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="Media frame detection")
    parser.add_argument(
        "--light-model", action="store_true",
        help="Use lighter model for CPU speed",
    )
    parser.add_argument(
        "--keywords-only", action="store_true",
        help="Use only keyword-based frame detection (no transformers)",
    )
    args = parser.parse_args()

    df = load_parquet(ATTRIBUTED_PARQUET)
    logger.info(f"Processing {len(df):,} articles for framing analysis")

    if args.keywords_only:
        # Keyword-only mode
        with timer("Keyword-based frame detection"):
            frame_results = {f"frame_{f}": [] for f in FRAME_NAMES}
            frame_results["dominant_frame"] = []
            frame_results["frame_method"] = []

            for _, row in tqdm(df.iterrows(), total=len(df), desc="Keyword frames"):
                kw_scores = keyword_frame_scores(row["body"])
                for f in FRAME_NAMES:
                    frame_results[f"frame_{f}"].append(kw_scores.get(f, 0.0))
                dominant = max(kw_scores, key=kw_scores.get) if any(kw_scores.values()) else None
                frame_results["dominant_frame"].append(dominant)
                frame_results["frame_method"].append("keyword_only")

            frame_df = pd.DataFrame(frame_results, index=df.index)
    else:
        from transformers import pipeline as hf_pipeline

        model_name = ZEROSHOT_MODEL_LIGHT if args.light_model else ZEROSHOT_MODEL
        with timer(f"Loading zero-shot model ({model_name})"):
            classifier = hf_pipeline(
                "zero-shot-classification",
                model=model_name,
                device=-1,
            )

        with timer("Zero-shot frame classification"):
            frame_df = zeroshot_frame_scores(df, classifier)

    # Merge frame scores into main dataframe
    df = pd.concat([df, frame_df], axis=1)

    # ── Summary ────────────────────────────────────────────────────────
    logger.info("\n── Frame Score Summary ──")
    for f in FRAME_NAMES:
        col = f"frame_{f}"
        if col in df.columns:
            logger.info(f"\n{col}:")
            logger.info(df[col].describe().to_string())

    # Dominant frame distribution
    logger.info("\n── Dominant Frame Distribution ──")
    logger.info(df["dominant_frame"].value_counts(dropna=False).to_string())

    # By prosecutor type
    if "prosecutor_type" in df.columns:
        logger.info("\n── Frame Scores by Prosecutor Type ──")
        for f in FRAME_NAMES:
            col = f"frame_{f}"
            grouped = df.groupby("prosecutor_type")[col].mean()
            logger.info(f"  {f}: {grouped.to_dict()}")

        logger.info("\n── Dominant Frame by Prosecutor Type ──")
        ct = pd.crosstab(df["prosecutor_type"], df["dominant_frame"], normalize="index")
        logger.info(ct.to_string())

    # ── Save ───────────────────────────────────────────────────────────
    save_parquet(df, FRAMES_PARQUET)
    logger.info("Done.")


if __name__ == "__main__":
    main()
