"""
Step 4: Multi-method bias detection on prosecutor-attributed articles.

Four methods, combined into a composite score:
  A. Aspect-based sentiment — sentiment toward prosecutor in context windows (0.35)
  B. Zero-shot stance — classify stance toward prosecutor in paragraphs (0.30)
  C. Enhanced keywords — theme dictionary within 3-sentence windows (0.20)
  D. Document-level sentiment — baseline control (0.15)

Input:  output/03_attributed.parquet
Output: output/04_bias_scores.parquet

Adds columns:
    score_aspect_sentiment, score_stance, score_keywords, score_doc_sentiment,
    composite_bias_score, n_methods_negative,
    theme_* (per-theme keyword flags)
"""

import argparse
import re
from collections import defaultdict

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import (
    ATTRIBUTED_PARQUET,
    BIAS_PARQUET,
    PROSECUTORS,
    ZEROSHOT_MODEL,
    ZEROSHOT_MODEL_LIGHT,
    SENTIMENT_MODEL,
    THEME_KEYWORDS,
    NEGATION_WORDS,
    BATCH_SIZE,
    MAX_TOKENS_SENTIMENT,
    OUTPUT_DIR,
)
from utils import (
    setup_logging,
    load_parquet,
    save_parquet,
    get_sentence_windows,
    split_sentences,
    truncate_words,
    timer,
    logger,
)


# ── Method A: Aspect-Based Sentiment ──────────────────────────────────────

def method_a_aspect_sentiment(
    df: pd.DataFrame,
    sentiment_pipeline,
) -> pd.Series:
    """Score sentiment in 3-sentence windows around prosecutor mentions.

    Returns a Series of scores in [-1, +1] where negative = negative sentiment.
    """
    logger.info("Method A: Aspect-based sentiment analysis")
    scores = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method A"):
        primary = row["primary_prosecutor"]
        if pd.isna(primary):
            scores.append(np.nan)
            continue

        # Get name variants for the primary prosecutor
        p = next((p for p in PROSECUTORS if p.name == primary), None)
        if p is None:
            scores.append(np.nan)
            continue

        # Collect context windows around mentions
        windows = []
        for variant in p.name_variants:
            ws = get_sentence_windows(row["body"], variant, window_size=3)
            windows.extend(ws)

        # Also check for the full name
        ws = get_sentence_windows(row["body"], p.name, window_size=3)
        windows.extend(ws)

        # Deduplicate windows (some overlap)
        windows = list(set(windows))

        if not windows:
            # No windows found; try generic "DA" / "district attorney"
            for term in ["the da", "the district attorney", "the prosecutor"]:
                ws = get_sentence_windows(row["body"], term, window_size=3)
                windows.extend(ws)
            windows = list(set(windows))

        if not windows:
            scores.append(np.nan)
            continue

        # Truncate each window and run sentiment
        truncated = [truncate_words(w, MAX_TOKENS_SENTIMENT) for w in windows[:10]]
        try:
            results = sentiment_pipeline(truncated)
            # Convert to numeric: negative=-1, neutral=0, positive=+1
            window_scores = []
            for r in results:
                label = r["label"].lower()
                confidence = r["score"]
                if "negative" in label:
                    window_scores.append(-confidence)
                elif "positive" in label:
                    window_scores.append(confidence)
                else:
                    window_scores.append(0.0)
            scores.append(float(np.mean(window_scores)))
        except Exception as e:
            logger.warning(f"Sentiment error for article {row['article_id']}: {e}")
            scores.append(np.nan)

    return pd.Series(scores, index=df.index, name="score_aspect_sentiment")


# ── Method B: Zero-Shot Stance Classification ─────────────────────────────

STANCE_LABELS = [
    "This text criticizes the prosecutor's handling of crime",
    "This text defends or supports the prosecutor's approach",
    "This text is neutral reporting about the prosecutor",
]
STANCE_BATCH_SIZE = max(BATCH_SIZE, 64)
DOC_SENT_BATCH_SIZE = max(BATCH_SIZE, 64)


def method_b_stance(
    df: pd.DataFrame,
    zeroshot_pipeline,
) -> pd.Series:
    """Classify stance toward prosecutor in paragraphs containing mentions.

    Returns a Series of scores in [-1, +1] where negative = critical stance.
    """
    logger.info("Method B: Zero-shot stance classification")
    # Precompute prosecutor lookup for fast access in loop.
    prosecutor_lookup = {p.name: p for p in PROSECUTORS}
    generic_da_re = re.compile(
        r"\b(?:the\s+da|the\s+district\s+attorney|the\s+prosecutor)\b",
        re.IGNORECASE,
    )

    # Build one flat list of paragraphs for batched inference and keep
    # per-article pointers so final scoring matches the original logic.
    all_texts: list[str] = []
    article_para_indices: list[list[int] | None] = []

    for row in tqdm(df.itertuples(index=False), total=len(df), desc="Method B prep"):
        primary = getattr(row, "primary_prosecutor")
        if pd.isna(primary):
            article_para_indices.append(None)
            continue

        p = prosecutor_lookup.get(primary)
        if p is None:
            article_para_indices.append(None)
            continue

        paragraphs = str(getattr(row, "body", "")).split("\n")
        relevant_paras: list[str] = []
        search_terms = p.name_variants + [p.name]

        # Named mentions.
        for para in paragraphs:
            para_lower = para.lower()
            if any(t.lower() in para_lower for t in search_terms):
                if len(para.split()) > 10:
                    relevant_paras.append(para)

        # Generic references, deduplicated.
        for para in paragraphs:
            if generic_da_re.search(para):
                if para not in relevant_paras and len(para.split()) > 10:
                    relevant_paras.append(para)

        if not relevant_paras:
            article_para_indices.append(None)
            continue

        para_idxs: list[int] = []
        for para in relevant_paras[:8]:
            para_idxs.append(len(all_texts))
            all_texts.append(truncate_words(para, MAX_TOKENS_SENTIMENT))
        article_para_indices.append(para_idxs)

    if not all_texts:
        return pd.Series(np.nan, index=df.index, name="score_stance")

    logger.info(
        f"Method B batching: classifying {len(all_texts):,} paragraphs "
        f"across {sum(1 for x in article_para_indices if x):,} articles"
    )

    # Batched zero-shot inference.
    all_results: list[dict | None] = [None] * len(all_texts)
    for i in tqdm(range(0, len(all_texts), STANCE_BATCH_SIZE), desc="Method B infer"):
        batch = all_texts[i : i + STANCE_BATCH_SIZE]
        try:
            results = zeroshot_pipeline(
                batch,
                candidate_labels=STANCE_LABELS,
                multi_label=False,
            )
            if isinstance(results, dict):
                results = [results]
            if len(results) != len(batch):
                logger.warning(
                    f"Stance batch size mismatch at offset {i}: "
                    f"expected {len(batch)}, got {len(results)}"
                )
            for j, r in enumerate(results):
                if i + j < len(all_results):
                    all_results[i + j] = r
        except Exception as e:
            logger.warning(f"Stance batch error at offset {i}: {e}")

    # Aggregate paragraph scores back to article-level stance.
    scores: list[float] = []
    for para_idxs in article_para_indices:
        if not para_idxs:
            scores.append(np.nan)
            continue

        para_scores = []
        for idx in para_idxs:
            r = all_results[idx]
            if not r:
                continue
            label_scores = dict(zip(r.get("labels", []), r.get("scores", [])))
            critical = label_scores.get(STANCE_LABELS[0], 0)
            supportive = label_scores.get(STANCE_LABELS[1], 0)
            para_scores.append(supportive - critical)

        scores.append(float(np.mean(para_scores)) if para_scores else np.nan)

    return pd.Series(scores, index=df.index, name="score_stance")


# ── Method C: Enhanced Keyword Analysis ───────────────────────────────────

def is_negated(text: str, keyword_pos: int) -> bool:
    """Check if a keyword at position keyword_pos is negated.

    Looks for negation words in the 3 words preceding the keyword.
    """
    # Get text before the keyword
    preceding = text[:keyword_pos].lower().split()
    preceding_window = preceding[-4:] if len(preceding) >= 4 else preceding
    return any(neg in " ".join(preceding_window) for neg in NEGATION_WORDS)


def method_c_keywords(df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Score articles using theme dictionaries within prosecutor context windows.

    Returns:
        scores: Series of keyword scores in [-1, 0] (negative = more anti-prosecutor themes)
        theme_df: DataFrame with boolean columns for each theme
    """
    logger.info("Method C: Enhanced keyword analysis")
    scores = []
    theme_flags = defaultdict(list)

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method C"):
        primary = row["primary_prosecutor"]
        if pd.isna(primary):
            scores.append(np.nan)
            for theme in THEME_KEYWORDS:
                theme_flags[f"theme_{theme}"].append(False)
            continue

        p = next((p for p in PROSECUTORS if p.name == primary), None)
        if p is None:
            scores.append(np.nan)
            for theme in THEME_KEYWORDS:
                theme_flags[f"theme_{theme}"].append(False)
            continue

        # Get 3-sentence windows around prosecutor mentions
        windows = []
        for variant in p.name_variants + [p.name]:
            ws = get_sentence_windows(row["body"], variant, window_size=3)
            windows.extend(ws)
        windows = list(set(windows))

        if not windows:
            scores.append(0.0)
            for theme in THEME_KEYWORDS:
                theme_flags[f"theme_{theme}"].append(False)
            continue

        combined_window = " ".join(windows).lower()
        article_score = 0
        n_themes_found = 0

        for theme_name, keywords in THEME_KEYWORDS.items():
            theme_found = False
            for kw in keywords:
                # Find keyword in the combined window
                for m in re.finditer(re.escape(kw), combined_window):
                    if not is_negated(combined_window, m.start()):
                        theme_found = True
                        break
                if theme_found:
                    break

            theme_flags[f"theme_{theme_name}"].append(theme_found)
            if theme_found:
                n_themes_found += 1

        # Score: number of anti-prosecutor themes found, normalized to [-1, 0]
        max_themes = len(THEME_KEYWORDS)
        scores.append(-n_themes_found / max_themes)

    score_series = pd.Series(scores, index=df.index, name="score_keywords")
    theme_df = pd.DataFrame(theme_flags, index=df.index)
    return score_series, theme_df


# ── Method D: Document-Level Sentiment ────────────────────────────────────

def method_d_doc_sentiment(
    df: pd.DataFrame,
    sentiment_pipeline,
) -> pd.Series:
    """Score overall article sentiment as a baseline measure.

    Returns Series of scores in [-1, +1].
    """
    logger.info("Method D: Document-level sentiment")
    texts = df["full_text"].apply(lambda t: truncate_words(t, MAX_TOKENS_SENTIMENT)).tolist()
    scores = []

    for i in tqdm(range(0, len(texts), DOC_SENT_BATCH_SIZE), desc="Method D"):
        batch = texts[i : i + DOC_SENT_BATCH_SIZE]
        try:
            results = sentiment_pipeline(batch)
            for r in results:
                label = r["label"].lower()
                confidence = r["score"]
                if "negative" in label:
                    scores.append(-confidence)
                elif "positive" in label:
                    scores.append(confidence)
                else:
                    scores.append(0.0)
        except Exception as e:
            logger.warning(f"Doc sentiment error at batch {i}: {e}")
            scores.extend([np.nan] * len(batch))

    return pd.Series(scores, index=df.index, name="score_doc_sentiment")


# ── Composite scoring ─────────────────────────────────────────────────────

def compute_composite(df: pd.DataFrame) -> pd.Series:
    """Combine method scores into a single composite bias score in [-1, +1].

    Weights: A=0.35, B=0.30, C=0.20, D=0.15
    Missing method scores are excluded and weights renormalized.
    """
    weights = {
        "score_aspect_sentiment": 0.35,
        "score_stance": 0.30,
        "score_keywords": 0.20,
        "score_doc_sentiment": 0.15,
    }

    composites = []
    n_methods = []

    for _, row in df.iterrows():
        total_weight = 0.0
        total_score = 0.0
        methods_used = 0

        for col, w in weights.items():
            val = row.get(col, np.nan)
            if pd.notna(val):
                total_weight += w
                total_score += w * val
                if val < -0.1:  # count as "negative" method
                    methods_used += 1

        if total_weight > 0:
            composites.append(total_score / total_weight)
        else:
            composites.append(np.nan)
        n_methods.append(methods_used)

    df["composite_bias_score"] = composites
    df["n_methods_negative"] = n_methods
    return df


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="Multi-method bias detection")
    parser.add_argument(
        "--light-model", action="store_true",
        help="Use lighter models for CPU speed",
    )
    parser.add_argument(
        "--keywords-only", action="store_true",
        help="Run only keyword analysis (Method C) — no transformer models",
    )
    parser.add_argument(
        "--skip-stance", action="store_true",
        help="Skip stance classification (Method B) to save time",
    )
    args = parser.parse_args()

    df = load_parquet(ATTRIBUTED_PARQUET)
    logger.info(f"Processing {len(df):,} prosecutor-attributed articles")

    # ── Method C: Keywords (always runs, no model needed) ──────────────
    with timer("Method C: Keyword analysis"):
        df["score_keywords"], theme_df = method_c_keywords(df)
        df = pd.concat([df, theme_df], axis=1)

    if not args.keywords_only:
        # Load models
        from transformers import pipeline as hf_pipeline

        model_name = ZEROSHOT_MODEL_LIGHT if args.light_model else ZEROSHOT_MODEL

        with timer("Loading sentiment model"):
            sentiment_pipe = hf_pipeline(
                "sentiment-analysis",
                model=SENTIMENT_MODEL,
                device=-1,
                truncation=True,
                max_length=MAX_TOKENS_SENTIMENT,
            )

        # ── Method A: Aspect-based sentiment ───────────────────────────
        with timer("Method A: Aspect sentiment"):
            df["score_aspect_sentiment"] = method_a_aspect_sentiment(df, sentiment_pipe)

        # ── Method D: Document-level sentiment ─────────────────────────
        with timer("Method D: Document sentiment"):
            df["score_doc_sentiment"] = method_d_doc_sentiment(df, sentiment_pipe)

        # ── Method B: Stance classification ────────────────────────────
        if not args.skip_stance:
            with timer(f"Loading zero-shot model ({model_name})"):
                zeroshot_pipe = hf_pipeline(
                    "zero-shot-classification",
                    model=model_name,
                    device=-1,
                )

            with timer("Method B: Stance classification"):
                df["score_stance"] = method_b_stance(df, zeroshot_pipe)
        else:
            df["score_stance"] = np.nan
            logger.info("Skipping Method B (stance) per --skip-stance flag")
    else:
        df["score_aspect_sentiment"] = np.nan
        df["score_stance"] = np.nan
        df["score_doc_sentiment"] = np.nan
        logger.info("Keywords-only mode: skipping transformer methods")

    # ── Composite score ────────────────────────────────────────────────
    with timer("Computing composite scores"):
        df = compute_composite(df)

    # ── Summary ────────────────────────────────────────────────────────
    logger.info("\n── Bias Score Summary ──")
    for col in ["score_aspect_sentiment", "score_stance", "score_keywords",
                 "score_doc_sentiment", "composite_bias_score"]:
        if col in df.columns and df[col].notna().any():
            logger.info(f"\n{col}:")
            logger.info(df[col].describe().to_string())

    # By prosecutor type
    if "prosecutor_type" in df.columns:
        logger.info("\n── Composite Score by Prosecutor Type ──")
        grouped = df.groupby("prosecutor_type")["composite_bias_score"].agg(
            ["mean", "median", "std", "count"]
        )
        logger.info(grouped.to_string())

        logger.info("\n── Composite Score by Prosecutor ──")
        by_prosecutor = df.groupby("primary_prosecutor")["composite_bias_score"].agg(
            ["mean", "median", "std", "count"]
        )
        logger.info(by_prosecutor.to_string())

    # Theme prevalence
    theme_cols = [c for c in df.columns if c.startswith("theme_")]
    if theme_cols:
        logger.info("\n── Theme Prevalence ──")
        for tc in theme_cols:
            pct = 100 * df[tc].mean()
            logger.info(f"  {tc}: {pct:.1f}%")

    # ── Save ───────────────────────────────────────────────────────────
    save_parquet(df, BIAS_PARQUET)
    logger.info("Done.")


if __name__ == "__main__":
    main()
