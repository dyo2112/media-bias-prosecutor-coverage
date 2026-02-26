"""
Step 09: Bias indicator extraction using langextract + Gemini.

Extracts structured bias indicators from prosecutor-attributed articles —
ungrounded claims, source prominence imbalances, loaded language, and
missing context. Complements Step 08's content extraction by focusing
specifically on HOW coverage is biased rather than WHAT is covered.

Input:  output/03_attributed.parquet
Output: output/09_bias_extractions.jsonl       (raw langextract results)
        output/09_bias_summary.parquet         (per-article bias summary)
        output/09_bias_stats.json              (aggregate stats by group)
        output/09_bias_visualization.html      (interactive viewer)

Usage:
    python 09_bias_extraction.py                     # full run
    python 09_bias_extraction.py --sample 5          # smoke test
    python 09_bias_extraction.py --sample 200        # pilot
    python 09_bias_extraction.py --resume            # resume from checkpoint
    python 09_bias_extraction.py --analyze-only      # skip extraction, just stats
"""

import argparse
import json
import os
import sys
import textwrap
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu, pearsonr, spearmanr, ttest_ind
from tqdm import tqdm

import langextract as lx

from config import (
    ATTRIBUTED_PARQUET,
    GEMINI_MODEL,
    OUTPUT_DIR,
    PROSECUTORS,
    RANDOM_SEED,
)
from utils import setup_logging, load_parquet, save_parquet, timer, logger

# ── Step 09 output paths (defined here until config.py is updated) ──────
BIAS_EXTRACTIONS_JSONL = OUTPUT_DIR / "09_bias_extractions.jsonl"
BIAS_SUMMARY_PARQUET = OUTPUT_DIR / "09_bias_summary.parquet"
BIAS_STATS_JSON = OUTPUT_DIR / "09_bias_stats.json"
BIAS_VIZ_HTML = OUTPUT_DIR / "09_bias_visualization.html"


# ── Prompt and examples ──────────────────────────────────────────────────

BIAS_EXTRACTION_PROMPT = textwrap.dedent("""\
    Analyze this news article about a district attorney / prosecutor for
    BIAS INDICATORS — patterns of coverage that reveal systematic slant
    rather than fair reporting. Use exact text spans from the article.

    Only extract genuine bias indicators. Legitimate critical reporting
    with evidence is NOT bias. Balanced articles may have zero extractions.

    1. ungrounded_negative_claim: A negative assertion about the prosecutor
       that lacks adequate supporting evidence within the article.
       Attributes:
         claim_content (performance|policy|character|competence)
         evidence_quality (none|anonymous_source|single_anecdote|stats_without_baseline|adequately_sourced)
         systemic_blame (true|false) — does the article blame the prosecutor
           for systemic issues beyond their direct control?

    2. source_prominence_imbalance: A source given disproportionate
       prominence relative to other viewpoints in the article, creating
       an imbalanced picture.
       Attributes:
         source_stance (critical|supportive)
         prominence_mechanism (placement_lede|placement_closing|extended_quote|sole_named_source|no_counterbalance|headline_framing)
         counterbalance_present (true|false)

    3. loaded_language: Emotionally charged, non-neutral word choices
       that go beyond factual reporting. Look for editorializing,
       pejorative labels, scare quotes, and hyperbole.
       Attributes:
         language_type (pejorative_label|scare_quotes|presuppositional_verb|hyperbole|ideological_framing|dehumanizing)
         target (prosecutor|prosecutor_policy|prosecutor_supporters|other)
         position (headline_or_lede|body|closing)

    4. missing_context: Important context that is conspicuously absent
       from the article, making the coverage misleading. Only extract if
       the omission materially distorts the story.
       Attributes:
         what_is_missing (trend_context|comparison_baseline|policy_rationale|systemic_factors|legal_constraints|prosecutor_response|alternative_explanation)
         claim_it_supports (free text — what narrative does the omission serve?)

    CALIBRATION GUIDANCE:
    - A well-sourced article that is critical of a prosecutor is NOT biased
      if the criticism is grounded in evidence and the prosecutor's
      perspective is included. Do not extract bias indicators from such articles.
    - An article that is favorable to a prosecutor IS biased if it
      cherry-picks achievements, omits failures, or relies on uncritical
      source selection.
    - Apply the same standard regardless of which prosecutor is covered.

    Only extract items that are clearly present. Do not fabricate or infer.
    Extract text spans in order of appearance. Do not paraphrase.""")


# Few-shot examples — three diverse examples calibrating the model
BIAS_FEW_SHOT_EXAMPLES = [
    # Example 1: Heavily biased anti-Boudin article (8 extractions)
    # Teaches the full range of bias indicators
    lx.data.ExampleData(
        text=(
            "San Francisco's failed experiment: How Chesa Boudin let criminals "
            "run wild. Since the radical progressive prosecutor took office, "
            "residents say the city has become unrecognizable. Car break-ins "
            "are rampant, shoplifters brazenly clear shelves with impunity, "
            "and violent offenders walk free hours after arrest. 'He cares "
            "more about criminals than victims,' said retired officer Jim "
            "Walsh, who spent 30 years on the force. Walsh described case "
            "after case of suspects released without charges. A business "
            "owner on Market Street, who asked not to be named for fear of "
            "retaliation, said Boudin's policies have destroyed the neighborhood. "
            "Critics point to a 12% rise in property crime, though experts "
            "note similar trends across major cities regardless of prosecutor "
            "ideology. Boudin's office did not respond to requests for comment."
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="loaded_language",
                extraction_text="San Francisco's failed experiment",
                attributes={
                    "language_type": "presuppositional_verb",
                    "target": "prosecutor_policy",
                    "position": "headline_or_lede",
                },
            ),
            lx.data.Extraction(
                extraction_class="loaded_language",
                extraction_text="let criminals run wild",
                attributes={
                    "language_type": "hyperbole",
                    "target": "prosecutor",
                    "position": "headline_or_lede",
                },
            ),
            lx.data.Extraction(
                extraction_class="loaded_language",
                extraction_text="the radical progressive prosecutor",
                attributes={
                    "language_type": "pejorative_label",
                    "target": "prosecutor",
                    "position": "body",
                },
            ),
            lx.data.Extraction(
                extraction_class="ungrounded_negative_claim",
                extraction_text="shoplifters brazenly clear shelves with impunity, and violent offenders walk free hours after arrest",
                attributes={
                    "claim_content": "performance",
                    "evidence_quality": "none",
                    "systemic_blame": "true",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_prominence_imbalance",
                extraction_text="retired officer Jim Walsh, who spent 30 years on the force. Walsh described case after case of suspects released without charges",
                attributes={
                    "source_stance": "critical",
                    "prominence_mechanism": "extended_quote",
                    "counterbalance_present": "false",
                },
            ),
            lx.data.Extraction(
                extraction_class="ungrounded_negative_claim",
                extraction_text="A business owner on Market Street, who asked not to be named for fear of retaliation, said Boudin's policies have destroyed the neighborhood",
                attributes={
                    "claim_content": "policy",
                    "evidence_quality": "anonymous_source",
                    "systemic_blame": "false",
                },
            ),
            lx.data.Extraction(
                extraction_class="missing_context",
                extraction_text="Critics point to a 12% rise in property crime",
                attributes={
                    "what_is_missing": "comparison_baseline",
                    "claim_it_supports": "Prosecutor uniquely responsible for crime increase when similar trends exist nationally",
                },
            ),
            lx.data.Extraction(
                extraction_class="missing_context",
                extraction_text="Boudin's office did not respond to requests for comment",
                attributes={
                    "what_is_missing": "prosecutor_response",
                    "claim_it_supports": "Prosecutor is hiding or unable to defend record",
                },
            ),
        ],
    ),
    # Example 2: Well-constructed critical article about Price (1 extraction)
    # Teaches that legitimate criticism with evidence is NOT bias
    lx.data.ExampleData(
        text=(
            "Alameda County DA Pamela Price's first year in office has drawn "
            "sharp scrutiny. An East Bay Times analysis of court records found "
            "that Price's office offered plea deals in 73% of violent felony "
            "cases, compared to 58% under predecessor Nancy O'Malley. The "
            "analysis examined 412 cases filed between January and September "
            "2023. Victims' rights advocate Maria Chen said the plea rates "
            "concern families who expected tougher prosecution. Price defended "
            "the approach in a press conference, saying her office prioritizes "
            "cases with the strongest evidence and that conviction rates on "
            "cases taken to trial have actually increased to 89%. Criminal "
            "justice professor David Lang at UC Berkeley noted that higher "
            "plea rates do not necessarily indicate leniency, as they may "
            "reflect more realistic case assessment. The recall campaign "
            "against Price has seized on the plea statistics."
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="missing_context",
                extraction_text="The recall campaign against Price has seized on the plea statistics",
                attributes={
                    "what_is_missing": "systemic_factors",
                    "claim_it_supports": "Plea rates are uniquely attributable to prosecutor ideology rather than case composition or resource constraints",
                },
            ),
        ],
    ),
    # Example 3: Pro-Jenkins puff piece (5 extractions)
    # Teaches that bias can favor any prosecutor
    lx.data.ExampleData(
        text=(
            "New DA Brooke Jenkins is restoring order to San Francisco. In her "
            "first six months, the tough-on-crime prosecutor has brought a "
            "sense of accountability that residents desperately needed. Jenkins "
            "announced felony charges against a prolific shoplifter, drawing "
            "praise from the business community. 'Finally, someone who takes "
            "our concerns seriously,' said Union Square Alliance director "
            "Tom Richards, who described Jenkins as a breath of fresh air "
            "after the chaos of the Boudin era. Police Chief Bill Scott lauded "
            "the improved cooperation between his department and the DA's office. "
            "Crime data for the period is not yet available from official sources."
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="loaded_language",
                extraction_text="restoring order to San Francisco",
                attributes={
                    "language_type": "presuppositional_verb",
                    "target": "prosecutor",
                    "position": "headline_or_lede",
                },
            ),
            lx.data.Extraction(
                extraction_class="loaded_language",
                extraction_text="the tough-on-crime prosecutor has brought a sense of accountability that residents desperately needed",
                attributes={
                    "language_type": "ideological_framing",
                    "target": "prosecutor",
                    "position": "body",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_prominence_imbalance",
                extraction_text="Tom Richards, who described Jenkins as a breath of fresh air after the chaos of the Boudin era",
                attributes={
                    "source_stance": "supportive",
                    "prominence_mechanism": "extended_quote",
                    "counterbalance_present": "false",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_prominence_imbalance",
                extraction_text="Police Chief Bill Scott lauded the improved cooperation between his department and the DA's office",
                attributes={
                    "source_stance": "supportive",
                    "prominence_mechanism": "no_counterbalance",
                    "counterbalance_present": "false",
                },
            ),
            lx.data.Extraction(
                extraction_class="missing_context",
                extraction_text="Crime data for the period is not yet available from official sources",
                attributes={
                    "what_is_missing": "trend_context",
                    "claim_it_supports": "Prosecutor is effective despite no evidence of measurable impact",
                },
            ),
        ],
    ),
]


# ── Extraction logic ─────────────────────────────────────────────────────

CHECKPOINT_INTERVAL = 50  # save after every N articles


def load_checkpoint(jsonl_path: Path) -> set[str]:
    """Return set of article_ids already processed (always as strings)."""
    done = set()
    if jsonl_path.exists():
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if "article_id" in obj:
                        done.add(str(obj["article_id"]))
                except json.JSONDecodeError:
                    continue
    return done


def extract_article(
    article_id: str,
    text: str,
    model_id: str,
    api_key: str | None = None,
    max_workers: int = 2,
) -> dict:
    """Run langextract on a single article. Returns dict with extractions."""
    try:
        result = lx.extract(
            text_or_documents=text,
            prompt_description=BIAS_EXTRACTION_PROMPT,
            examples=BIAS_FEW_SHOT_EXAMPLES,
            model_id=model_id,
            api_key=api_key,
            max_workers=max_workers,
        )

        extractions = []
        if result and hasattr(result, "extractions"):
            for ext in result.extractions:
                extractions.append({
                    "extraction_class": ext.extraction_class,
                    "extraction_text": ext.extraction_text,
                    "attributes": ext.attributes if hasattr(ext, "attributes") else {},
                })

        return {
            "article_id": article_id,
            "n_extractions": len(extractions),
            "extractions": extractions,
            "error": None,
        }

    except Exception as e:
        return {
            "article_id": article_id,
            "n_extractions": 0,
            "extractions": [],
            "error": str(e),
        }


def run_extraction(
    df: pd.DataFrame,
    model_id: str,
    api_key: str | None,
    max_workers: int,
    delay: float,
    resume: bool,
) -> list[dict]:
    """Process all articles, with checkpointing and progress bar."""

    # Load checkpoint
    done_ids = load_checkpoint(BIAS_EXTRACTIONS_JSONL) if resume else set()
    if done_ids:
        logger.info(f"Resuming: {len(done_ids)} articles already processed")

    # Filter to remaining (convert to str for type-safe comparison)
    df["article_id_str"] = df["article_id"].astype(str)
    remaining = df[~df["article_id_str"].isin(done_ids)]
    remaining = remaining.drop(columns=["article_id_str"])
    df.drop(columns=["article_id_str"], inplace=True)
    logger.info(f"Processing {len(remaining)} articles ({len(done_ids)} already done, {len(df)-len(remaining)} matched)")

    results = []
    jsonl_f = open(BIAS_EXTRACTIONS_JSONL, "a" if resume else "w", encoding="utf-8")

    try:
        for i, (_, row) in enumerate(tqdm(remaining.iterrows(),
                                          total=len(remaining),
                                          desc="Extracting bias indicators")):
            article_id = str(row["article_id"])
            text = str(row.get("full_text", row.get("body", "")))

            # Truncate very long articles to ~3000 words
            words = text.split()
            if len(words) > 3000:
                text = " ".join(words[:3000])

            result = extract_article(
                article_id=article_id,
                text=text,
                model_id=model_id,
                api_key=api_key,
                max_workers=1,
            )
            results.append(result)

            # Write to JSONL incrementally
            jsonl_f.write(json.dumps(result, ensure_ascii=False) + "\n")

            # Checkpoint flush
            if (i + 1) % CHECKPOINT_INTERVAL == 0:
                jsonl_f.flush()
                logger.info(f"  Checkpoint: {i + 1}/{len(remaining)} articles saved")

            # Rate limiting
            if delay > 0:
                time.sleep(delay)

    finally:
        jsonl_f.close()

    return results


# ── Analysis logic ───────────────────────────────────────────────────────

def load_all_extractions(jsonl_path: Path) -> list[dict]:
    """Load all extraction results from JSONL."""
    results = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def flatten_extractions(results: list[dict], df: pd.DataFrame) -> pd.DataFrame:
    """Flatten extraction results into a per-extraction DataFrame."""
    rows = []
    # Build lookup for prosecutor info (convert to str keys for consistent matching)
    lookup_df = df.copy()
    lookup_df["article_id"] = lookup_df["article_id"].astype(str)
    article_info = lookup_df.set_index("article_id")[
        ["primary_prosecutor", "prosecutor_type", "publication", "date"]
    ].to_dict("index")

    for res in results:
        aid = str(res["article_id"])
        info = article_info.get(aid, {})

        for ext in res.get("extractions", []):
            attrs = ext.get("attributes") or {}
            row = {
                "article_id": aid,
                "primary_prosecutor": info.get("primary_prosecutor"),
                "prosecutor_type": info.get("prosecutor_type"),
                "publication": info.get("publication"),
                "date": info.get("date"),
                "extraction_class": ext.get("extraction_class"),
                "extraction_text": ext.get("extraction_text", ""),
            }
            # Flatten attributes into columns
            for k, v in attrs.items():
                row[f"attr_{k}"] = v
            rows.append(row)

    return pd.DataFrame(rows)


# ── Bias scoring ─────────────────────────────────────────────────────────

def compute_article_bias_score(summary: dict) -> float:
    """Compute per-article bias score in [-1, +1]. Negative = anti-prosecutor."""
    anti_signal = (
        0.25 * min(summary.get("n_ungrounded_severe", 0) / 3.0, 1.0)
        + 0.15 * min(summary.get("n_systemic_blame", 0) / 2.0, 1.0)
        + 0.20 * min(summary.get("n_source_imbalance_crit", 0) / 2.0, 1.0)
        + 0.15 * min(summary.get("n_loaded_negative", 0) / 3.0, 1.0)
        + 0.10 * (1.0 if summary.get("n_loaded_headline", 0) > 0 else 0.0)
        + 0.15 * min(summary.get("n_missing_context", 0) / 3.0, 1.0)
    )
    pro_signal = (
        0.50 * min(summary.get("n_source_imbalance_supp", 0) / 2.0, 1.0)
    )
    if anti_signal > pro_signal:
        return -anti_signal
    elif pro_signal > anti_signal:
        return pro_signal
    return 0.0


def build_article_summary(results: list[dict], df: pd.DataFrame) -> pd.DataFrame:
    """Build per-article summary of bias indicator counts and composite score."""
    summaries = []
    for res in results:
        aid = res["article_id"]
        exts = res.get("extractions", [])

        summary = {
            "article_id": aid,
            "n_total": len(exts),
            "n_ungrounded_claims": 0,
            "n_ungrounded_severe": 0,
            "n_systemic_blame": 0,
            "n_source_imbalance_crit": 0,
            "n_source_imbalance_supp": 0,
            "n_loaded_language": 0,
            "n_loaded_negative": 0,
            "n_loaded_headline": 0,
            "n_missing_context": 0,
            "error": res.get("error"),
        }

        for ext in exts:
            attrs = ext.get("attributes") or {}
            cls = ext.get("extraction_class")

            if cls == "ungrounded_negative_claim":
                summary["n_ungrounded_claims"] += 1
                ev_quality = attrs.get("evidence_quality", "")
                if ev_quality in ("none", "anonymous_source"):
                    summary["n_ungrounded_severe"] += 1
                if attrs.get("systemic_blame") == "true":
                    summary["n_systemic_blame"] += 1

            elif cls == "source_prominence_imbalance":
                stance = attrs.get("source_stance", "")
                if stance == "critical":
                    summary["n_source_imbalance_crit"] += 1
                elif stance == "supportive":
                    summary["n_source_imbalance_supp"] += 1

            elif cls == "loaded_language":
                summary["n_loaded_language"] += 1
                target = attrs.get("target", "")
                if target in ("prosecutor", "prosecutor_policy"):
                    summary["n_loaded_negative"] += 1
                position = attrs.get("position", "")
                if position == "headline_or_lede":
                    summary["n_loaded_headline"] += 1

            elif cls == "missing_context":
                summary["n_missing_context"] += 1

        # Compute bias score from the counts
        summary["bias_score"] = compute_article_bias_score(summary)
        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)

    # Fill numeric columns with 0, keep error column as-is (string/None)
    error_col = summary_df.pop("error") if "error" in summary_df.columns else None
    summary_df = summary_df.infer_objects(copy=False).fillna(0)
    if error_col is not None:
        summary_df["error"] = error_col

    # Merge with prosecutor info
    info_cols = ["article_id", "primary_prosecutor", "prosecutor_type"]
    merge_df = df[info_cols].copy()
    merge_df["article_id"] = merge_df["article_id"].astype(str)
    summary_df["article_id"] = summary_df["article_id"].astype(str)

    result = summary_df.merge(merge_df, on="article_id", how="left")
    matched = result["prosecutor_type"].notna().sum()
    logger.info(f"Merge: {matched}/{len(result)} articles matched prosecutor metadata")
    if matched < len(result):
        logger.warning(f"{len(result) - matched} articles missing prosecutor_type after merge")
    return result


# ── Statistical helpers ──────────────────────────────────────────────────

def cohens_d(group1, group2):
    """Compute Cohen's d effect size (positive = group1 > group2)."""
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return (np.mean(group1) - np.mean(group2)) / pooled_std


def bootstrap_diff_ci(
    group1, group2, stat_fn=np.mean, n_boot: int = 5000, ci: float = 0.95, seed: int = 42
):
    """Bootstrap confidence interval for the difference stat_fn(g1) - stat_fn(g2)."""
    rng = np.random.default_rng(seed)
    observed = stat_fn(group1) - stat_fn(group2)
    boot_diffs = [
        stat_fn(rng.choice(group1, len(group1), replace=True))
        - stat_fn(rng.choice(group2, len(group2), replace=True))
        for _ in range(n_boot)
    ]
    alpha = (1 - ci) / 2
    return (
        float(observed),
        float(np.percentile(boot_diffs, 100 * alpha)),
        float(np.percentile(boot_diffs, 100 * (1 - alpha))),
    )


# ── Main statistical analysis ───────────────────────────────────────────

def run_statistical_analysis(ext_df: pd.DataFrame, summary_df: pd.DataFrame) -> dict:
    """Compute group-level statistics on bias indicators."""
    stats = {}

    # Split by prosecutor type
    prog = summary_df[summary_df["prosecutor_type"] == "Progressive"]
    trad = summary_df[summary_df["prosecutor_type"] == "Traditional"]

    prog_scores = prog["bias_score"].values
    trad_scores = trad["bias_score"].values

    # ── 1. Primary test: bias_score group comparison ──────────────────────
    primary = {
        "n_progressive": int(len(prog)),
        "n_traditional": int(len(trad)),
        "mean_progressive": float(np.mean(prog_scores)) if len(prog_scores) > 0 else 0.0,
        "mean_traditional": float(np.mean(trad_scores)) if len(trad_scores) > 0 else 0.0,
        "median_progressive": float(np.median(prog_scores)) if len(prog_scores) > 0 else 0.0,
        "median_traditional": float(np.median(trad_scores)) if len(trad_scores) > 0 else 0.0,
    }

    if len(prog_scores) > 1 and len(trad_scores) > 1:
        # Welch's t-test
        t_stat, t_p = ttest_ind(prog_scores, trad_scores, equal_var=False)
        primary["welch_t_stat"] = float(t_stat)
        primary["welch_t_p"] = float(t_p)

        # Mann-Whitney U
        u_stat, u_p = mannwhitneyu(prog_scores, trad_scores, alternative="two-sided")
        primary["mann_whitney_u"] = float(u_stat)
        primary["mann_whitney_p"] = float(u_p)

        # Cohen's d
        primary["cohens_d"] = float(cohens_d(prog_scores, trad_scores))

        # Bootstrap CI
        obs, ci_lo, ci_hi = bootstrap_diff_ci(
            prog_scores, trad_scores, n_boot=5000, seed=RANDOM_SEED
        )
        primary["bootstrap_diff"] = obs
        primary["bootstrap_ci_low"] = ci_lo
        primary["bootstrap_ci_high"] = ci_hi

        # TOST equivalence test (delta = 0.2, small effect)
        delta = 0.2
        # Use the pooled standard deviation for TOST
        n1, n2 = len(prog_scores), len(trad_scores)
        var1 = np.var(prog_scores, ddof=1)
        var2 = np.var(trad_scores, ddof=1)
        pooled_sd = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
        if pooled_sd > 0:
            bound = delta * pooled_sd
            diff = np.mean(prog_scores) - np.mean(trad_scores)
            se = np.sqrt(var1 / n1 + var2 / n2)
            # Two one-sided t-tests
            t_lower = (diff - (-bound)) / se
            t_upper = (diff - bound) / se
            from scipy.stats import t as t_dist
            df_welch = se**4 / (
                (var1 / n1)**2 / (n1 - 1) + (var2 / n2)**2 / (n2 - 1)
            )
            p_lower = 1 - t_dist.cdf(t_lower, df_welch)
            p_upper = t_dist.cdf(t_upper, df_welch)
            tost_p = max(p_lower, p_upper)
            primary["tost_delta"] = float(delta)
            primary["tost_bound_raw"] = float(bound)
            primary["tost_p"] = float(tost_p)
            primary["tost_equivalent"] = bool(tost_p < 0.05)

    stats["primary_test"] = primary

    # ── 2. Paired county comparisons ─────────────────────────────────────
    paired = {}

    # SF: Boudin vs Jenkins
    boudin = summary_df[summary_df["primary_prosecutor"] == "Chesa Boudin"]["bias_score"].values
    jenkins = summary_df[summary_df["primary_prosecutor"] == "Brooke Jenkins"]["bias_score"].values
    if len(boudin) > 1 and len(jenkins) > 1:
        paired["sf_boudin_vs_jenkins"] = {
            "n_boudin": int(len(boudin)),
            "n_jenkins": int(len(jenkins)),
            "mean_boudin": float(np.mean(boudin)),
            "mean_jenkins": float(np.mean(jenkins)),
            "cohens_d": float(cohens_d(boudin, jenkins)),
        }
        t_stat, t_p = ttest_ind(boudin, jenkins, equal_var=False)
        paired["sf_boudin_vs_jenkins"]["welch_t_p"] = float(t_p)

    # Alameda: Price vs O'Malley
    price = summary_df[summary_df["primary_prosecutor"] == "Pamela Price"]["bias_score"].values
    omalley = summary_df[summary_df["primary_prosecutor"] == "Nancy O'Malley"]["bias_score"].values
    if len(price) > 1 and len(omalley) > 1:
        paired["alameda_price_vs_omalley"] = {
            "n_price": int(len(price)),
            "n_omalley": int(len(omalley)),
            "mean_price": float(np.mean(price)),
            "mean_omalley": float(np.mean(omalley)),
            "cohens_d": float(cohens_d(price, omalley)),
        }
        t_stat, t_p = ttest_ind(price, omalley, equal_var=False)
        paired["alameda_price_vs_omalley"]["welch_t_p"] = float(t_p)

    stats["paired_county"] = paired

    # ── 3. Per-indicator comparisons ─────────────────────────────────────
    indicator_cols = [
        "n_ungrounded_claims", "n_ungrounded_severe", "n_systemic_blame",
        "n_source_imbalance_crit", "n_source_imbalance_supp",
        "n_loaded_language", "n_loaded_negative", "n_loaded_headline",
        "n_missing_context", "n_total",
    ]
    per_indicator = {}
    for col in indicator_cols:
        if col not in summary_df.columns:
            continue
        p_vals = prog[col].values
        t_vals = trad[col].values
        entry = {
            "mean_progressive": float(np.mean(p_vals)) if len(p_vals) > 0 else 0.0,
            "mean_traditional": float(np.mean(t_vals)) if len(t_vals) > 0 else 0.0,
        }
        if len(p_vals) > 1 and len(t_vals) > 1:
            entry["cohens_d"] = float(cohens_d(p_vals, t_vals))
        per_indicator[col] = entry
    stats["per_indicator"] = per_indicator

    # ── 4. Categorical attribute distributions with chi-square ───────────
    categorical = {}

    if not ext_df.empty and "extraction_class" in ext_df.columns:
        # evidence_quality by prosecutor_type
        categorical["evidence_quality"] = _chi_square_on_attribute(
            ext_df, "ungrounded_negative_claim", "attr_evidence_quality",
            ["none", "anonymous_source", "single_anecdote",
             "stats_without_baseline", "adequately_sourced"]
        )

        # language_type by prosecutor_type
        categorical["language_type"] = _chi_square_on_attribute(
            ext_df, "loaded_language", "attr_language_type",
            ["pejorative_label", "scare_quotes", "presuppositional_verb",
             "hyperbole", "ideological_framing", "dehumanizing"]
        )

        # what_is_missing by prosecutor_type
        categorical["what_is_missing"] = _chi_square_on_attribute(
            ext_df, "missing_context", "attr_what_is_missing",
            ["trend_context", "comparison_baseline", "policy_rationale",
             "systemic_factors", "legal_constraints", "prosecutor_response",
             "alternative_explanation"]
        )

        # prominence_mechanism by prosecutor_type
        categorical["prominence_mechanism"] = _chi_square_on_attribute(
            ext_df, "source_prominence_imbalance", "attr_prominence_mechanism",
            ["placement_lede", "placement_closing", "extended_quote",
             "sole_named_source", "no_counterbalance", "headline_framing"]
        )

    stats["categorical_distributions"] = categorical

    # ── 5. Per-prosecutor stats ──────────────────────────────────────────
    per_prosecutor = {}
    for p in PROSECUTORS:
        p_sub = summary_df[summary_df["primary_prosecutor"] == p.name]
        if len(p_sub) == 0:
            continue
        per_prosecutor[p.name] = {
            "n_articles": int(len(p_sub)),
            "mean_bias_score": float(p_sub["bias_score"].mean()),
            "median_bias_score": float(p_sub["bias_score"].median()),
            "mean_n_total": float(p_sub["n_total"].mean()),
            "mean_n_ungrounded_claims": float(p_sub["n_ungrounded_claims"].mean()),
            "mean_n_ungrounded_severe": float(p_sub["n_ungrounded_severe"].mean()),
            "mean_n_source_imbalance_crit": float(p_sub["n_source_imbalance_crit"].mean()),
            "mean_n_source_imbalance_supp": float(p_sub["n_source_imbalance_supp"].mean()),
            "mean_n_loaded_negative": float(p_sub["n_loaded_negative"].mean()),
            "mean_n_loaded_headline": float(p_sub["n_loaded_headline"].mean()),
            "mean_n_missing_context": float(p_sub["n_missing_context"].mean()),
        }
    stats["per_prosecutor"] = per_prosecutor

    # ── 6. Convergent validity with Step 04 ──────────────────────────────
    step04_path = OUTPUT_DIR / "04_bias_scores.parquet"
    convergent = {}
    if step04_path.exists():
        try:
            step04_df = pd.read_parquet(step04_path)
            step04_df["article_id"] = step04_df["article_id"].astype(str)
            merged = summary_df[["article_id", "bias_score"]].merge(
                step04_df[["article_id", "composite_bias_score"]],
                on="article_id",
                how="inner",
            )
            if len(merged) >= 10:
                r_pearson, p_pearson = pearsonr(
                    merged["bias_score"], merged["composite_bias_score"]
                )
                r_spearman, p_spearman = spearmanr(
                    merged["bias_score"], merged["composite_bias_score"]
                )
                convergent = {
                    "n_matched": int(len(merged)),
                    "pearson_r": float(r_pearson),
                    "pearson_p": float(p_pearson),
                    "spearman_r": float(r_spearman),
                    "spearman_p": float(p_spearman),
                }
                logger.info(f"Convergent validity: matched {len(merged)} articles with Step 04")
            else:
                convergent = {"n_matched": int(len(merged)), "note": "Too few matches for correlation"}
        except Exception as e:
            convergent = {"error": str(e)}
    else:
        convergent = {"note": "Step 04 parquet not found; skipping convergent validity"}
    stats["convergent_validity"] = convergent

    return stats


def _chi_square_on_attribute(
    ext_df: pd.DataFrame,
    extraction_class: str,
    attr_col: str,
    categories: list[str],
) -> dict:
    """Run chi-square test on an attribute column by prosecutor_type."""
    result = {"Progressive": {}, "Traditional": {}}
    subset = ext_df[ext_df["extraction_class"] == extraction_class]

    for ptype in ["Progressive", "Traditional"]:
        ptype_sub = subset[subset["prosecutor_type"] == ptype]
        for cat in categories:
            n = int((ptype_sub.get(attr_col, pd.Series()) == cat).sum())
            result[ptype][cat] = n

    # Attempt chi-square
    try:
        ct = pd.DataFrame(result).fillna(0)
        # Only run if we have enough data (at least some counts in both columns)
        if ct.sum().sum() > 0 and (ct.sum(axis=1) > 0).sum() >= 2 and (ct.sum(axis=0) > 0).all():
            chi2, p, dof, _ = chi2_contingency(ct.values)
            result["chi2"] = float(chi2)
            result["chi2_p"] = float(p)
            result["chi2_dof"] = int(dof)
    except Exception:
        pass

    return result


# ── Report printing ──────────────────────────────────────────────────────

def print_analysis_report(stats: dict):
    """Log a readable summary of the bias extraction analysis."""
    logger.info("\n" + "=" * 70)
    logger.info("STEP 09: BIAS INDICATOR EXTRACTION REPORT")
    logger.info("=" * 70)

    # Primary test
    primary = stats.get("primary_test", {})
    logger.info("\n-- Primary: Bias Score by Prosecutor Type --")
    logger.info(f"  Progressive (n={primary.get('n_progressive', 0)}): "
                f"mean={primary.get('mean_progressive', 0):.4f}, "
                f"median={primary.get('median_progressive', 0):.4f}")
    logger.info(f"  Traditional (n={primary.get('n_traditional', 0)}): "
                f"mean={primary.get('mean_traditional', 0):.4f}, "
                f"median={primary.get('median_traditional', 0):.4f}")
    if "cohens_d" in primary:
        logger.info(f"  Cohen's d = {primary['cohens_d']:.4f} "
                     f"(negative = Progressive more anti-prosecutor bias)")
    if "welch_t_p" in primary:
        logger.info(f"  Welch's t: t={primary['welch_t_stat']:.3f}, "
                     f"p={primary['welch_t_p']:.6f}")
    if "mann_whitney_p" in primary:
        logger.info(f"  Mann-Whitney U: U={primary['mann_whitney_u']:.1f}, "
                     f"p={primary['mann_whitney_p']:.6f}")
    if "bootstrap_diff" in primary:
        logger.info(f"  Bootstrap diff (Prog - Trad): {primary['bootstrap_diff']:.4f} "
                     f"[{primary['bootstrap_ci_low']:.4f}, {primary['bootstrap_ci_high']:.4f}]")
    if "tost_p" in primary:
        equiv_str = "YES" if primary.get("tost_equivalent") else "NO"
        logger.info(f"  TOST equivalence (delta={primary['tost_delta']}): "
                     f"p={primary['tost_p']:.6f} => Equivalent: {equiv_str}")

    # Paired county comparisons
    paired = stats.get("paired_county", {})
    logger.info("\n-- Paired County Comparisons --")
    sf = paired.get("sf_boudin_vs_jenkins", {})
    if sf:
        logger.info(f"  SF: Boudin (n={sf['n_boudin']}, mean={sf['mean_boudin']:.4f}) "
                     f"vs Jenkins (n={sf['n_jenkins']}, mean={sf['mean_jenkins']:.4f})")
        logger.info(f"       Cohen's d = {sf['cohens_d']:.4f}, "
                     f"p = {sf.get('welch_t_p', float('nan')):.6f}")
    else:
        logger.info("  SF: Insufficient data for Boudin vs Jenkins")

    ala = paired.get("alameda_price_vs_omalley", {})
    if ala:
        logger.info(f"  Alameda: Price (n={ala['n_price']}, mean={ala['mean_price']:.4f}) "
                     f"vs O'Malley (n={ala['n_omalley']}, mean={ala['mean_omalley']:.4f})")
        logger.info(f"           Cohen's d = {ala['cohens_d']:.4f}, "
                     f"p = {ala.get('welch_t_p', float('nan')):.6f}")
    else:
        logger.info("  Alameda: Insufficient data for Price vs O'Malley")

    # Per-indicator breakdown
    logger.info("\n-- Per-Indicator Group Comparison (mean per article) --")
    per_ind = stats.get("per_indicator", {})
    for col, vals in per_ind.items():
        label = col.replace("n_", "").replace("_", " ").title()
        d_str = f"d={vals['cohens_d']:.3f}" if "cohens_d" in vals else "d=N/A"
        logger.info(f"  {label:30s}  Prog: {vals['mean_progressive']:.3f}  "
                     f"Trad: {vals['mean_traditional']:.3f}  {d_str}")

    # Categorical distributions
    logger.info("\n-- Categorical Attribute Distributions --")
    cat_dists = stats.get("categorical_distributions", {})
    for attr_name, dist in cat_dists.items():
        chi2_val = dist.get("chi2")
        chi2_p = dist.get("chi2_p")
        chi2_str = ""
        if chi2_val is not None:
            chi2_str = f"  (chi2={chi2_val:.2f}, p={chi2_p:.6f})"
        logger.info(f"  {attr_name}{chi2_str}")
        for cat in sorted(set(dist.get("Progressive", {}).keys()) | set(dist.get("Traditional", {}).keys())):
            p_n = dist.get("Progressive", {}).get(cat, 0)
            t_n = dist.get("Traditional", {}).get(cat, 0)
            if p_n + t_n > 0:
                logger.info(f"    {cat:35s}  Prog: {p_n:5d}  Trad: {t_n:5d}")

    # Per-prosecutor summary
    logger.info("\n-- Per-Prosecutor Summary --")
    pp = stats.get("per_prosecutor", {})
    for name, vals in pp.items():
        logger.info(f"  {name:20s}  n={vals['n_articles']:5d}  "
                     f"bias={vals['mean_bias_score']:+.4f}  "
                     f"extractions/article={vals['mean_n_total']:.1f}")

    # Convergent validity
    conv = stats.get("convergent_validity", {})
    logger.info("\n-- Convergent Validity (vs Step 04 composite_bias_score) --")
    if "pearson_r" in conv:
        logger.info(f"  Matched articles: {conv['n_matched']}")
        logger.info(f"  Pearson r = {conv['pearson_r']:.4f} (p = {conv['pearson_p']:.6f})")
        logger.info(f"  Spearman r = {conv['spearman_r']:.4f} (p = {conv['spearman_p']:.6f})")
    elif "note" in conv:
        logger.info(f"  {conv['note']}")
    elif "error" in conv:
        logger.info(f"  Error: {conv['error']}")
    else:
        logger.info("  No convergent validity data available")

    logger.info("\nDone.")


# ── Visualization ────────────────────────────────────────────────────────

def generate_visualization(jsonl_path: Path, output_html: Path):
    """Generate interactive HTML visualization from langextract results."""
    import io as _io

    # Temporarily redirect stdout to utf-8 to prevent Windows cp1252 errors
    old_stdout = sys.stdout
    try:
        if sys.platform == "win32":
            sys.stdout = _io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
        html = lx.visualize(str(jsonl_path))
        if html:
            output_html.write_text(html, encoding="utf-8")
            logger.info(f"Visualization saved to {output_html}")
        else:
            logger.warning("langextract.visualize returned empty output")
    except Exception as e:
        logger.warning(f"Could not generate visualization: {e}")
    finally:
        sys.stdout = old_stdout


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    setup_logging()

    # Suppress duplicate logging from langextract/absl internals
    import logging as _logging
    _logging.getLogger("absl").setLevel(_logging.WARNING)
    _logging.getLogger("langextract").setLevel(_logging.WARNING)

    parser = argparse.ArgumentParser(description="Step 09: Bias indicator extraction via langextract")
    parser.add_argument("--sample", type=int, default=0,
                        help="Process only N random articles (0 = all)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Skip extraction, just run analysis on existing JSONL")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="Parallel API calls for langextract")
    parser.add_argument("--model", type=str, default=GEMINI_MODEL,
                        help=f"Gemini model name (default: {GEMINI_MODEL})")
    parser.add_argument("--api-key", type=str, default=None,
                        help="Gemini API key (default: LANGEXTRACT_API_KEY env var)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Seconds between API calls (rate limiting)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load attributed articles
    df = load_parquet(ATTRIBUTED_PARQUET)
    logger.info(f"Loaded {len(df)} attributed articles")

    # Filter to articles with prosecutor mentions
    df = df[df["primary_prosecutor"].notna()].copy()
    logger.info(f"Articles with prosecutor attribution: {len(df)}")

    # Sample if requested
    if args.sample > 0:
        n = min(args.sample, len(df))
        # Stratified sample: equal Progressive/Traditional
        prog = df[df["prosecutor_type"] == "Progressive"]
        trad = df[df["prosecutor_type"] == "Traditional"]
        n_per = n // 2
        sample = pd.concat([
            prog.sample(min(n_per, len(prog)), random_state=RANDOM_SEED),
            trad.sample(min(n - n_per, len(trad)), random_state=RANDOM_SEED),
        ])
        df = sample
        logger.info(f"Sampled {len(df)} articles (stratified by prosecutor type)")

    # Extraction phase
    if not args.analyze_only:
        api_key = args.api_key or os.environ.get("LANGEXTRACT_API_KEY")
        if not api_key:
            logger.error("No API key provided. Set LANGEXTRACT_API_KEY env var or use --api-key")
            sys.exit(1)

        with timer("Bias extraction"):
            results = run_extraction(
                df=df,
                model_id=args.model,
                api_key=api_key,
                max_workers=args.max_workers,
                delay=args.delay,
                resume=args.resume,
            )

        n_success = sum(1 for r in results if r["error"] is None)
        n_errors = sum(1 for r in results if r["error"] is not None)
        n_total_exts = sum(r["n_extractions"] for r in results)
        logger.info(f"Extraction complete: {n_success} succeeded, {n_errors} errors, "
                     f"{n_total_exts} total bias indicators extracted")

    # Analysis phase
    if not BIAS_EXTRACTIONS_JSONL.exists():
        logger.error(f"No extraction results found at {BIAS_EXTRACTIONS_JSONL}")
        sys.exit(1)

    with timer("Analysis"):
        all_results = load_all_extractions(BIAS_EXTRACTIONS_JSONL)
        logger.info(f"Loaded {len(all_results)} extraction results from JSONL")

        # Flatten to per-extraction DataFrame
        ext_df = flatten_extractions(all_results, df)
        logger.info(f"Flattened to {len(ext_df)} individual bias indicators")

        # Build per-article summary with bias scores
        summary_df = build_article_summary(all_results, df)
        save_parquet(summary_df, BIAS_SUMMARY_PARQUET)

        # Run statistical analysis
        stats = run_statistical_analysis(ext_df, summary_df)

        # Save stats
        with open(BIAS_STATS_JSON, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Stats saved to {BIAS_STATS_JSON}")

        # Print report
        print_analysis_report(stats)

    # Visualization
    with timer("Visualization"):
        generate_visualization(BIAS_EXTRACTIONS_JSONL, BIAS_VIZ_HTML)

    logger.info(f"\nAll outputs in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
