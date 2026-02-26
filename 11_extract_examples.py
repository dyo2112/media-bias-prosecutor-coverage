"""
Step 11: Extract illustrative examples for Appendix C.

For each analysis method, find 2-3 extreme-scoring articles and extract
their headlines, first ~200 words of body text, scores, and the specific
features that triggered the detection.

Also extracts cross-method examples: articles scored by ALL methods,
showing how different methods capture different dimensions.

Output: output/11_appendix_c_examples.md
"""

import json
import re
import textwrap

import pandas as pd
import numpy as np

from config import (
    BIAS_PARQUET,
    OUTPUT_DIR,
    THEME_ATTR_PARQUET,
)
from utils import setup_logging, load_parquet, logger


def truncate_body(text: str, max_words: int = 200) -> str:
    """Return the first ~max_words words of text."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " [...]"


def format_example(row, score_col: str, extra_info: str = "") -> str:
    """Format a single article example as markdown."""
    lines = []
    lines.append(f"**Headline**: {row['headline']}")
    lines.append(f"**Date**: {row['date'].strftime('%Y-%m-%d')}")
    lines.append(f"**Publication**: {row['publication']}")
    lines.append(f"**Prosecutor**: {row['primary_prosecutor']} ({row['prosecutor_type']})")
    lines.append(f"**Score ({score_col})**: {row[score_col]:.4f}")
    if extra_info:
        lines.append(f"**Details**: {extra_info}")
    lines.append("")
    body = truncate_body(row.get("clean_text", row.get("body", "")))
    lines.append(f"> {body}")
    lines.append("")
    return "\n".join(lines)


def extract_keyword_themes(row) -> str:
    """List which keyword themes were triggered in an article."""
    theme_cols = [c for c in row.index if c.startswith("theme_") and row[c] == True]
    if not theme_cols:
        return "No themes detected"
    return ", ".join(c.replace("theme_", "") for c in theme_cols)


def extract_ta_themes(row) -> str:
    """List which theme attribution themes were triggered."""
    theme_cols = [c for c in row.index if c.startswith("ta_theme_") and row[c] == True]
    if not theme_cols:
        return "No themes detected"
    methods = int(row.get("ta_methods_detected", 0))
    themes = ", ".join(c.replace("ta_theme_", "") for c in theme_cols)
    return f"{themes} ({methods} detection methods)"


def main():
    setup_logging()

    # Load data
    bs = load_parquet(BIAS_PARQUET)
    ta = load_parquet(THEME_ATTR_PARQUET)

    # Merge theme attribution data
    ta_cols = ["article_id", "ta_composite_score", "ta_methods_detected",
               "ta_any_theme", "ta_confidence"] + \
              [c for c in ta.columns if c.startswith("ta_theme_")]
    df = bs.merge(ta[ta_cols], on="article_id", how="left")

    # Filter to attributed articles
    df = df[df["primary_prosecutor"].notna() & df["composite_bias_score"].notna()].copy()
    logger.info(f"Working with {len(df):,} articles")

    output_lines = []
    output_lines.append("# Appendix C: Illustrative Examples by Method\n")
    output_lines.append("*Auto-extracted from the corpus to illustrate how each method ")
    output_lines.append("captures different dimensions of coverage bias.*\n\n")

    # ── 1. Theme Attribution (d=0.42, study's largest effect) ──
    output_lines.append("## 1. Prosecutor-Attributed Theme Detection (d = 0.43)\n")
    output_lines.append("This method detects anti-prosecutor narrative themes (recall campaigns, ")
    output_lines.append("soft-on-crime framing, etc.) attributed to specific prosecutors.\n\n")

    # High theme score — progressive
    prog_themes = df[(df["prosecutor_type"] == "Progressive") & (df["ta_composite_score"] > 0)]
    prog_themes = prog_themes.sort_values("ta_composite_score", ascending=False)

    output_lines.append("### Example 1a: High theme score (Progressive prosecutor)\n")
    if len(prog_themes) > 0:
        row = prog_themes.iloc[0]
        info = extract_ta_themes(row)
        output_lines.append(format_example(row, "ta_composite_score", info))

    # Recall-themed article
    recall_articles = df[(df["prosecutor_type"] == "Progressive") &
                         (df.get("ta_theme_recall", pd.Series(dtype=bool)) == True)]
    if len(recall_articles) > 0:
        output_lines.append("### Example 1b: Recall campaign theme (Progressive)\n")
        row = recall_articles.sort_values("ta_composite_score", ascending=False).iloc[0]
        if row["article_id"] != prog_themes.iloc[0]["article_id"]:
            info = extract_ta_themes(row)
            output_lines.append(format_example(row, "ta_composite_score", info))

    # Soft-on-crime themed
    soft_articles = df[(df["prosecutor_type"] == "Progressive") &
                       (df.get("ta_theme_soft_on_crime", pd.Series(dtype=bool)) == True)]
    if len(soft_articles) > 0:
        output_lines.append("### Example 1c: Soft-on-crime theme (Progressive)\n")
        row = soft_articles.sort_values("ta_composite_score", ascending=False).iloc[0]
        info = extract_ta_themes(row)
        output_lines.append(format_example(row, "ta_composite_score", info))

    # No themes (showing specificity) — traditional
    no_themes_trad = df[(df["prosecutor_type"] == "Traditional") &
                        (df["ta_composite_score"] == 0)]
    if len(no_themes_trad) > 0:
        output_lines.append("### Example 1d: No themes detected (Traditional prosecutor)\n")
        row = no_themes_trad.sample(1, random_state=42).iloc[0]
        output_lines.append(format_example(row, "ta_composite_score", "No anti-prosecutor themes detected"))

    # ── 2. Keyword Analysis (Method C) ──
    output_lines.append("\n## 2. Keyword Bias Score (Method C, d = -0.22)\n")
    output_lines.append("Weighted keyword scoring based on crime-related terminology, ")
    output_lines.append("negativity markers, and prosecutor-specific framing.\n\n")

    # Most negative keyword score — progressive
    prog_kw = df[df["prosecutor_type"] == "Progressive"].sort_values("score_keywords")
    if len(prog_kw) > 0:
        output_lines.append("### Example 2a: Most negative keyword score (Progressive)\n")
        row = prog_kw.iloc[0]
        themes = extract_keyword_themes(row)
        output_lines.append(format_example(row, "score_keywords", f"Keyword themes: {themes}"))

    # crime_rising themed
    crime_rising = df[(df["prosecutor_type"] == "Progressive") &
                      (df.get("theme_crime_rising", pd.Series(dtype=bool)) == True)]
    if len(crime_rising) > 0:
        output_lines.append("### Example 2b: Crime-rising theme (Progressive)\n")
        row = crime_rising.sort_values("score_keywords").iloc[0]
        themes = extract_keyword_themes(row)
        output_lines.append(format_example(row, "score_keywords", f"Keyword themes: {themes}"))

    # ── 3. Aspect Sentiment (Method A) ──
    if "score_aspect_sentiment" in df.columns and not df["score_aspect_sentiment"].isna().all():
        output_lines.append("\n## 3. Aspect Sentiment (Method A)\n")
        output_lines.append("Sentiment specifically about the prosecutor entity, not overall article tone.\n\n")

        prog_sent = df[df["prosecutor_type"] == "Progressive"].dropna(subset=["score_aspect_sentiment"])
        if len(prog_sent) > 0:
            prog_sent_sorted = prog_sent.sort_values("score_aspect_sentiment")
            output_lines.append("### Example 3a: Most negative aspect sentiment (Progressive)\n")
            row = prog_sent_sorted.iloc[0]
            output_lines.append(format_example(row, "score_aspect_sentiment"))

            # Divergence case: negative sentiment but neutral/positive keywords
            divergent = prog_sent[(prog_sent["score_aspect_sentiment"] < -0.3) &
                                  (prog_sent["score_keywords"] > -0.01)]
            if len(divergent) > 0:
                output_lines.append("### Example 3b: Divergence — negative sentiment, neutral keywords\n")
                row = divergent.iloc[0]
                output_lines.append(format_example(
                    row, "score_aspect_sentiment",
                    f"Keyword score: {row['score_keywords']:.4f} (near zero)"))

    # ── 4. Cross-Method Comparison ──
    output_lines.append("\n## 4. Cross-Method Comparison\n")
    output_lines.append("The same article scored by multiple methods, illustrating how ")
    output_lines.append("different methods capture different dimensions.\n\n")

    score_cols = ["score_keywords", "ta_composite_score"]
    optional_cols = ["score_aspect_sentiment", "score_stance", "score_doc_sentiment"]
    available_scores = score_cols + [c for c in optional_cols if c in df.columns and not df[c].isna().all()]

    # Find articles with extreme scores on multiple dimensions
    # Progressive article that's negative on all methods
    prog_df = df[df["prosecutor_type"] == "Progressive"].copy()
    if len(available_scores) >= 2:
        # Article with most negative composite AND high theme score
        candidates = prog_df[
            (prog_df["composite_bias_score"] < prog_df["composite_bias_score"].quantile(0.05)) &
            (prog_df["ta_composite_score"] > prog_df["ta_composite_score"].quantile(0.90))
        ]
        if len(candidates) > 0:
            output_lines.append("### Example 4a: Multi-method negative (Progressive)\n")
            row = candidates.sort_values("composite_bias_score").iloc[0]
            scores_str = ", ".join(f"{c}={row[c]:.3f}" for c in available_scores if pd.notna(row.get(c)))
            output_lines.append(format_example(row, "composite_bias_score", f"All scores: {scores_str}"))

        # Traditional article with neutral/low scores everywhere
        trad_df = df[df["prosecutor_type"] == "Traditional"].copy()
        neutral = trad_df[
            (trad_df["composite_bias_score"].abs() < 0.005) &
            (trad_df["ta_composite_score"] == 0)
        ]
        if len(neutral) > 0:
            output_lines.append("### Example 4b: Multi-method neutral (Traditional)\n")
            row = neutral.sample(1, random_state=42).iloc[0]
            scores_str = ", ".join(f"{c}={row[c]:.3f}" for c in available_scores if pd.notna(row.get(c)))
            output_lines.append(format_example(row, "composite_bias_score", f"All scores: {scores_str}"))

    # ── Write output ──
    output_path = OUTPUT_DIR / "11_appendix_c_examples.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    logger.info(f"Saved examples to {output_path}")
    logger.info("Done.")


if __name__ == "__main__":
    main()
