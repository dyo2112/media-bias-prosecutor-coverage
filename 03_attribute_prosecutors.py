"""
Step 3: Detect prosecutor mentions and attribute each article to a prosecutor.

For each relevant article:
  1. Search for named prosecutor mentions (regex on name variants)
  2. Handle "Price" disambiguation (common word)
  3. Detect generic DA references and assign by date + county
  4. Determine primary prosecutor (most mentions; headline = 3x weight)

Input:  output/02_relevant.parquet
Output: output/03_attributed.parquet

Adds columns:
    mentions_* (count per prosecutor), headline_mention_*,
    primary_prosecutor, prosecutor_type, total_prosecutor_mentions,
    has_prosecutor_mention, assigned_via_generic_da_fallback
"""

import re
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import (
    RELEVANT_PARQUET,
    ATTRIBUTED_PARQUET,
    PROSECUTORS,
    PUBLICATION_COUNTY,
    OUTPUT_DIR,
)
from utils import setup_logging, load_parquet, save_parquet, timer, logger


# ── Prosecutor name matching ──────────────────────────────────────────────

def build_name_patterns() -> dict[str, re.Pattern]:
    """Build compiled regex patterns for each prosecutor's name variants."""
    patterns = {}
    for p in PROSECUTORS:
        # Build alternation of all variants, longest first
        variants = sorted(p.name_variants, key=len, reverse=True)
        escaped = [re.escape(v) for v in variants]
        pattern_str = r"\b(?:" + "|".join(escaped) + r")\b"
        patterns[p.name] = re.compile(pattern_str, re.IGNORECASE)
    return patterns


# Special handling for "Price" — only count as Pamela Price in context
PRICE_CONTEXT_WORDS = re.compile(
    r"\b(?:da|district\s+attorney|prosecutor|alameda|pamela)\b",
    re.IGNORECASE,
)

GENERIC_DA_REFS = re.compile(
    r"\b(?:the\s+(?:district\s+attorney|da|d\.a\.|prosecutor)|"
    r"district\s+attorney(?:'s)?\s+office)\b",
    re.IGNORECASE,
)


def count_mentions(
    text: str,
    headline: str,
    name_patterns: dict[str, re.Pattern],
) -> dict[str, dict]:
    """Count prosecutor mentions in text and headline.

    Returns dict of {prosecutor_name: {"body": int, "headline": int}}.
    """
    counts = {}
    for pname, pattern in name_patterns.items():
        body_matches = len(pattern.findall(text))
        headline_matches = len(pattern.findall(headline))
        counts[pname] = {
            "body": body_matches,
            "headline": headline_matches,
        }

    # Special "Price" disambiguation
    # Only add bare "price" matches if contextual conditions are met
    price_pattern = re.compile(r"\bprice\b", re.IGNORECASE)
    pamela_price = next(p for p in PROSECUTORS if p.name == "Pamela Price")

    # Check bare "price" in body
    for m in price_pattern.finditer(text):
        # Get 50-word window around the match
        start = max(0, m.start() - 300)
        end = min(len(text), m.end() + 300)
        window = text[start:end]
        if PRICE_CONTEXT_WORDS.search(window):
            # Only count if not already matched by "pamela price"
            if "pamela price" not in text[max(0, m.start()-20):m.end()].lower():
                counts["Pamela Price"]["body"] += 1

    # Check bare "price" in headline
    for m in price_pattern.finditer(headline):
        start = max(0, m.start() - 100)
        end = min(len(headline), m.end() + 100)
        window = headline[start:end]
        if PRICE_CONTEXT_WORDS.search(window):
            if "pamela price" not in headline[max(0, m.start()-20):m.end()].lower():
                counts["Pamela Price"]["headline"] += 1

    return counts


def get_publication_county(pub_lower: str) -> str | None:
    """Map a publication name to its primary county."""
    for key, county in PUBLICATION_COUNTY.items():
        if key in pub_lower:
            return county
    return None


def assign_by_date_and_county(
    article_date: date,
    county: str | None,
) -> str | None:
    """Find the prosecutor serving in a county on a given date."""
    if county is None:
        return None
    for p in PROSECUTORS:
        if p.county != county:
            continue
        if p.start_date <= article_date:
            if p.end_date is None or article_date <= p.end_date:
                return p.name
    return None


def _is_false_positive_price(article_date, body_text: str) -> bool:
    """Check if a Price attribution is a false positive.

    "Price" is a common English word (price gouging, stock price, etc.) and a
    common surname.  Before Pamela Price took office (2023-01-03), bare "price"
    matches in a DA/Alameda context often refer to price-gouging enforcement or
    other people named Price.  We require "pamela" to appear somewhere in the
    article to confirm it really is about *Pamela* Price.

    After her start date all Price-attributed articles are accepted (she is the
    sitting DA, so "Price" in DA context is almost certainly her).
    """
    price = next(p for p in PROSECUTORS if p.name == "Pamela Price")
    if isinstance(article_date, date):
        art_date = article_date
    else:
        art_date = article_date.date() if hasattr(article_date, "date") else article_date
    if art_date >= price.start_date:
        return False  # After she took office — always valid
    # Before she took office — require "pamela" to confirm it's really her
    return "pamela" not in body_text.lower()


def _is_false_positive_jenkins(article_date, body_text: str) -> bool:
    """Check if a Jenkins attribution is a false positive.

    Before Brooke Jenkins took office (2022-07-08), bare "Jenkins" matches
    often refer to other people (e.g., a victim, a defendant, a politician).
    We flag these as false positives if "brooke" does NOT appear anywhere in
    the article body or headline.  After her start date, all Jenkins matches
    are legitimate.
    """
    jenkins = next(p for p in PROSECUTORS if p.name == "Brooke Jenkins")
    if isinstance(article_date, date):
        art_date = article_date
    else:
        art_date = article_date.date() if hasattr(article_date, "date") else article_date
    if art_date >= jenkins.start_date:
        return False  # After she took office — always valid
    # Before she took office — require "brooke" to confirm it's really her
    return "brooke" not in body_text.lower()


def determine_primary(
    mention_counts: dict[str, dict],
    article_date,
    pub_county: str | None,
    body_text: str = "",
    headline_text: str = "",
) -> tuple[str | None, str | None]:
    """Determine primary prosecutor for an article.

    Returns (prosecutor_name, ideology) or (None, None).

    Scoring: each body mention = 1 point, each headline mention = 3 points.
    If no named mentions, check for generic DA references and assign by
    date+county.

    Includes false-positive filtering for ambiguous last names (e.g.,
    "Jenkins" before Brooke Jenkins took office).
    """
    scores = {}
    for pname, cnts in mention_counts.items():
        score = cnts["body"] + 3 * cnts["headline"]
        if score > 0:
            scores[pname] = score

    # Filter out false positives before selecting primary
    combined_text = body_text + " " + headline_text
    if "Brooke Jenkins" in scores:
        if _is_false_positive_jenkins(article_date, combined_text):
            del scores["Brooke Jenkins"]
    if "Pamela Price" in scores:
        if _is_false_positive_price(article_date, combined_text):
            del scores["Pamela Price"]

    if scores:
        primary = max(scores, key=scores.get)
        p = next(p for p in PROSECUTORS if p.name == primary)
        return primary, p.ideology

    return None, None


# ── Main pipeline ─────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    df = load_parquet(RELEVANT_PARQUET)
    name_patterns = build_name_patterns()

    # ── Count mentions per article ─────────────────────────────────────
    with timer("Counting prosecutor mentions"):
        results = []
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Attribution"):
            counts = count_mentions(
                row["body"],
                row["headline"],
                name_patterns,
            )
            results.append(counts)

    # Unpack into columns
    for p in PROSECUTORS:
        df[f"mentions_{p.name}"] = [r[p.name]["body"] for r in results]
        df[f"headline_mention_{p.name}"] = [r[p.name]["headline"] for r in results]

    # Total named mentions
    mention_cols = [f"mentions_{p.name}" for p in PROSECUTORS]
    df["total_prosecutor_mentions"] = df[mention_cols].sum(axis=1)

    # ── Check for generic DA references ────────────────────────────────
    with timer("Checking generic DA references"):
        df["generic_da_refs"] = df["body"].apply(
            lambda t: len(GENERIC_DA_REFS.findall(t))
        )

    # ── Assign primary prosecutor ──────────────────────────────────────
    with timer("Determining primary prosecutor"):
        primaries = []
        ideologies = []
        fallback_flags = []

        for _, row in tqdm(df.iterrows(), total=len(df), desc="Primary assignment"):
            counts = {}
            for p in PROSECUTORS:
                counts[p.name] = {
                    "body": row[f"mentions_{p.name}"],
                    "headline": row[f"headline_mention_{p.name}"],
                }

            pub_county = get_publication_county(row["publication_lower"])
            article_date = row["date"].date() if hasattr(row["date"], "date") else row["date"]

            primary, ideology = determine_primary(
                counts, article_date, pub_county,
                body_text=row["body"], headline_text=row["headline"],
            )

            used_fallback = False
            # If no named mention but has generic DA references,
            # try to assign by date+county
            if primary is None and row["generic_da_refs"] > 0:
                primary = assign_by_date_and_county(article_date, pub_county)
                if primary:
                    ideology = next(
                        p.ideology for p in PROSECUTORS if p.name == primary
                    )
                    used_fallback = True

            primaries.append(primary)
            ideologies.append(ideology)
            fallback_flags.append(bool(used_fallback and pd.notna(primary)))

        df["primary_prosecutor"] = primaries
        df["prosecutor_type"] = ideologies
        df["assigned_via_generic_da_fallback"] = fallback_flags

    # ── Flag articles with any prosecutor mention ──────────────────────
    df["has_prosecutor_mention"] = (
        (df["total_prosecutor_mentions"] > 0)
        | (df["primary_prosecutor"].notna())
    )

    # ── Summary statistics ─────────────────────────────────────────────
    n_with_mention = df["has_prosecutor_mention"].sum()
    logger.info(f"\nArticles with prosecutor mentions: {n_with_mention:,} / {len(df):,}")

    if n_with_mention > 0:
        logger.info("\nPrimary prosecutor distribution:")
        logger.info(df["primary_prosecutor"].value_counts(dropna=False).to_string())

        logger.info("\nBy ideology:")
        logger.info(df["prosecutor_type"].value_counts(dropna=False).to_string())

        n_fallback = int(df["assigned_via_generic_da_fallback"].sum())
        logger.info(
            f"\nPrimary assignments via generic-DA fallback: {n_fallback:,} "
            f"/ {int(df['primary_prosecutor'].notna().sum()):,}"
        )

        # Per-prosecutor mention stats
        for p in PROSECUTORS:
            col = f"mentions_{p.name}"
            n_articles = (df[col] > 0).sum()
            logger.info(f"  {p.name}: {n_articles:,} articles, "
                        f"{df[col].sum():,} total mentions")

    # ── Save ───────────────────────────────────────────────────────────
    # Save all relevant articles with attribution columns
    save_parquet(df, OUTPUT_DIR / "03_all_relevant_attributed.parquet")

    # Save only rows resolved to a specific prosecutor for downstream analysis.
    unresolved = df[df["has_prosecutor_mention"] & df["primary_prosecutor"].isna()]
    if len(unresolved) > 0:
        logger.info(
            f"Articles with prosecutor mentions but no resolved primary prosecutor: "
            f"{len(unresolved):,}"
        )

    attributed = df[df["primary_prosecutor"].notna()].copy()
    save_parquet(attributed, ATTRIBUTED_PARQUET)

    logger.info("Done.")


if __name__ == "__main__":
    main()
