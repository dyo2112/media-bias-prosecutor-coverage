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
    is_negated,
    find_quote_spans,
    pos_in_spans,
    fraction_quoted,
    timer,
    logger,
)


# ── Method A: Aspect-Based Sentiment ──────────────────────────────────────

def method_a_aspect_sentiment(
    df: pd.DataFrame,
    sentiment_pipeline,
) -> tuple[pd.Series, pd.Series]:
    """Score sentiment in 3-sentence windows around prosecutor mentions.

    Returns:
        scores: Series in [-1, +1] where negative = negative sentiment.
        quoted_frac: Series with the mean fraction of quoted-speech characters
            in the windows scored (diagnostic — the sentiment model does not
            distinguish the outlet's voice from quoted sources).
    """
    logger.info("Method A: Aspect-based sentiment analysis")
    scores = []
    quoted_fracs = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method A"):
        primary = row["primary_prosecutor"]
        if pd.isna(primary):
            scores.append(np.nan)
            quoted_fracs.append(np.nan)
            continue

        # Get name variants for the primary prosecutor
        p = next((p for p in PROSECUTORS if p.name == primary), None)
        if p is None:
            scores.append(np.nan)
            quoted_fracs.append(np.nan)
            continue

        # Collect context windows around mentions
        windows = []
        for variant in p.name_variants:
            ws = get_sentence_windows(row["body"], variant, window_size=3)
            windows.extend(ws)

        # Also check for the full name
        ws = get_sentence_windows(row["body"], p.name, window_size=3)
        windows.extend(ws)

        # Deduplicate windows, preserving order (set() ordering varies by
        # process hash seed and made scores non-reproducible)
        windows = list(dict.fromkeys(windows))

        if not windows:
            # No windows found; try generic "DA" / "district attorney"
            for term in ["the da", "the district attorney", "the prosecutor"]:
                ws = get_sentence_windows(row["body"], term, window_size=3)
                windows.extend(ws)
            windows = list(dict.fromkeys(windows))

        if not windows:
            scores.append(np.nan)
            quoted_fracs.append(np.nan)
            continue

        used = windows[:10]
        quoted_fracs.append(float(np.mean([fraction_quoted(w) for w in used])))

        # Truncate each window and run sentiment
        truncated = [truncate_words(w, MAX_TOKENS_SENTIMENT) for w in used]
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

    return (
        pd.Series(scores, index=df.index, name="score_aspect_sentiment"),
        pd.Series(quoted_fracs, index=df.index, name="aspect_windows_quoted_frac"),
    )


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
        # Whole-word matching so short variants can't hit inside longer words
        name_re = re.compile(
            r"(?<!\w)(?:"
            + "|".join(re.escape(t.lower()) for t in search_terms)
            + r")(?!\w)"
        )

        # Named mentions.
        for para in paragraphs:
            para_lower = para.lower()
            if name_re.search(para_lower):
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

def method_c_keywords(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Score articles using theme dictionaries within prosecutor context windows.

    Returns:
        scores: Series of keyword scores in [-1, 0] (negative = more anti-prosecutor themes)
        scores_noquote: same score but ignoring keyword matches inside quoted
            speech — separates the outlet's own voice from quoted sources
        theme_df: DataFrame with boolean columns for each theme
    """
    logger.info("Method C: Enhanced keyword analysis")
    scores = []
    scores_noquote = []
    theme_flags = defaultdict(list)
    max_themes = len(THEME_KEYWORDS)

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Method C"):
        primary = row["primary_prosecutor"]
        if pd.isna(primary):
            scores.append(np.nan)
            scores_noquote.append(np.nan)
            for theme in THEME_KEYWORDS:
                theme_flags[f"theme_{theme}"].append(False)
            continue

        p = next((p for p in PROSECUTORS if p.name == primary), None)
        if p is None:
            scores.append(np.nan)
            scores_noquote.append(np.nan)
            for theme in THEME_KEYWORDS:
                theme_flags[f"theme_{theme}"].append(False)
            continue

        # Get 3-sentence windows around prosecutor mentions
        windows = []
        for variant in p.name_variants + [p.name]:
            ws = get_sentence_windows(row["body"], variant, window_size=3)
            windows.extend(ws)
        windows = list(dict.fromkeys(windows))

        if not windows:
            scores.append(0.0)
            scores_noquote.append(0.0)
            for theme in THEME_KEYWORDS:
                theme_flags[f"theme_{theme}"].append(False)
            continue

        combined_window = " ".join(windows).lower()
        quote_spans = find_quote_spans(combined_window)
        n_themes_found = 0
        n_themes_found_noquote = 0

        for theme_name, keywords in THEME_KEYWORDS.items():
            theme_found = False
            theme_found_noquote = False
            for kw in keywords:
                kw_re = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
                for m in re.finditer(kw_re, combined_window):
                    if is_negated(combined_window, m.start(), NEGATION_WORDS):
                        continue
                    theme_found = True
                    if not pos_in_spans(m.start(), quote_spans):
                        theme_found_noquote = True
                        break
                if theme_found_noquote:
                    break

            theme_flags[f"theme_{theme_name}"].append(theme_found)
            if theme_found:
                n_themes_found += 1
            if theme_found_noquote:
                n_themes_found_noquote += 1

        # Score: number of anti-prosecutor themes found, normalized to [-1, 0]
        scores.append(-n_themes_found / max_themes)
        scores_noquote.append(-n_themes_found_noquote / max_themes)

    score_series = pd.Series(scores, index=df.index, name="score_keywords")
    noquote_series = pd.Series(
        scores_noquote, index=df.index, name="score_keywords_noquote"
    )
    theme_df = pd.DataFrame(theme_flags, index=df.index)
    return score_series, noquote_series, theme_df


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

    Also computes composite_bias_score_noquote, a sensitivity variant where
    the keyword channel (Method C) ignores matches inside quoted speech.
    Methods A/B/D are unchanged in that variant (masking them would require
    re-running model inference on modified text).
    """
    weights = {
        "score_aspect_sentiment": 0.35,
        "score_stance": 0.30,
        "score_keywords": 0.20,
        "score_doc_sentiment": 0.15,
    }

    def weighted_composite(row, keyword_col: str) -> tuple[float, int]:
        total_weight = 0.0
        total_score = 0.0
        methods_negative = 0
        for col, w in weights.items():
            use_col = keyword_col if col == "score_keywords" else col
            val = row.get(use_col, np.nan)
            if pd.notna(val):
                total_weight += w
                total_score += w * val
                if val < -0.1:  # count as "negative" method
                    methods_negative += 1
        if total_weight > 0:
            return total_score / total_weight, methods_negative
        return np.nan, methods_negative

    composites = []
    composites_noquote = []
    n_methods = []
    has_noquote = "score_keywords_noquote" in df.columns

    for _, row in df.iterrows():
        comp, n_neg = weighted_composite(row, "score_keywords")
        composites.append(comp)
        n_methods.append(n_neg)
        if has_noquote:
            comp_nq, _ = weighted_composite(row, "score_keywords_noquote")
            composites_noquote.append(comp_nq)

    df["composite_bias_score"] = composites
    df["n_methods_negative"] = n_methods
    if has_noquote:
        df["composite_bias_score_noquote"] = composites_noquote
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
        df["score_keywords"], df["score_keywords_noquote"], theme_df = method_c_keywords(df)
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
            aspect_scores, aspect_quoted = method_a_aspect_sentiment(df, sentiment_pipe)
            df["score_aspect_sentiment"] = aspect_scores
            df["aspect_windows_quoted_frac"] = aspect_quoted

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
