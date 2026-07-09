"""
Step 8: Grounded claim extraction using langextract + Gemini.

Extracts structured, source-grounded information from prosecutor-attributed
articles — specific claims, source attributions, causal assertions, policy
actions, and prosecutor comparisons. Complements the tone/stance analysis
in Steps 04-05 by revealing WHAT is said, by WHOM, with WHAT evidence.

Input:  output/03_attributed.parquet
Output: output/08_extractions.jsonl       (raw langextract results)
        output/08_extractions_summary.parquet  (per-article summary)
        output/08_extraction_stats.json   (aggregate stats by prosecutor type)
        output/08_visualization.html      (interactive viewer)

Usage:
    python 08_langextract_analysis.py                     # full run
    python 08_langextract_analysis.py --sample 5          # smoke test
    python 08_langextract_analysis.py --sample 200        # pilot
    python 08_langextract_analysis.py --resume            # resume from checkpoint
    python 08_langextract_analysis.py --analyze-only      # skip extraction, just stats
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
from scipy.stats import chi2_contingency
from tqdm import tqdm

import langextract as lx

from config import (
    ATTRIBUTED_PARQUET,
    EXTRACTIONS_JSONL,
    EXTRACTIONS_PARQUET,
    EXTRACTION_STATS_JSON,
    EXTRACTION_VIZ_HTML,
    GEMINI_MODEL,
    OUTPUT_DIR,
    PROSECUTORS,
    RANDOM_SEED,
)
from utils import setup_logging, load_parquet, save_parquet, timer, logger


# ── Prompt and examples ──────────────────────────────────────────────────

EXTRACTION_PROMPT = textwrap.dedent("""\
    Extract the following types of information from this news article about
    a district attorney / prosecutor. Use exact text spans from the article.

    1. claim_against_prosecutor: Specific accusations, criticisms, or negative
       claims made about the prosecutor's performance, policies, or character.
       Attributes: claim_type (performance|policy|character|competence),
       specificity (vague|specific|quantified), evidence_cited (none|anecdotal|statistical|official_report)

    2. source_attribution: Identify who is speaking, quoted, or cited as a source.
       Attributes: source_type (police|victim|defense_attorney|prosecutor|politician|
       community_member|journalist|expert|advocacy_group),
       stance_toward_prosecutor (critical|supportive|neutral)

    3. causal_claim: Claims that the prosecutor's actions caused or contributed
       to some outcome (crime increase, safety decline, etc.).
       Attributes: effect (crime_increase|public_safety_decline|case_outcome|
       community_impact|positive_outcome), causal_strength (explicit|implied|speculative),
       direction (prosecutor_caused_harm|prosecutor_helped|ambiguous)

    4. policy_action: Concrete policies, decisions, or actions attributed to
       the prosecutor.
       Attributes: action_type (declined_to_prosecute|reduced_charges|new_policy|
       fired_staff|reversed_predecessor|enhanced_prosecution|other),
       domain (drugs|property_crime|violent_crime|bail|sentencing|staffing|
       juvenile|general), framing (positive|negative|neutral)

    5. comparison: Explicit comparisons between the current prosecutor and a
       predecessor, another prosecutor, or a general standard.
       Attributes: compared_to (predecessor|other_prosecutor|general_standard),
       dimension (toughness|case_outcomes|policy|competence|ideology),
       who_favored (current|predecessor|neither)

    Only extract items that are clearly present. Do not fabricate or infer.
    Extract text spans in order of appearance. Do not paraphrase.""")


# Few-shot examples — diverse coverage types to avoid biasing the model
FEW_SHOT_EXAMPLES = [
    # Example 1: Critical article about a progressive prosecutor
    lx.data.ExampleData(
        text=(
            "San Francisco's District Attorney Chesa Boudin faced renewed criticism "
            "this week after police data showed a 15% increase in car break-ins "
            "since he took office. Police Officers Association president Tony "
            "Montoya said officers are demoralized because suspects they arrest "
            "are quickly released without charges. 'Why bother making arrests when "
            "the DA won't prosecute?' Montoya asked. Boudin defended his record, "
            "saying his office focuses on serious violent crime rather than low-level "
            "offenses. Recall organizers said the crime statistics prove Boudin's "
            "progressive policies have failed San Francisco residents."
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="claim_against_prosecutor",
                extraction_text="a 15% increase in car break-ins since he took office",
                attributes={
                    "claim_type": "performance",
                    "specificity": "quantified",
                    "evidence_cited": "statistical",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_attribution",
                extraction_text="Police Officers Association president Tony Montoya said officers are demoralized",
                attributes={
                    "source_type": "police",
                    "stance_toward_prosecutor": "critical",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_attribution",
                extraction_text="Boudin defended his record, saying his office focuses on serious violent crime",
                attributes={
                    "source_type": "prosecutor",
                    "stance_toward_prosecutor": "supportive",
                },
            ),
            lx.data.Extraction(
                extraction_class="causal_claim",
                extraction_text="the crime statistics prove Boudin's progressive policies have failed",
                attributes={
                    "effect": "crime_increase",
                    "causal_strength": "explicit",
                    "direction": "prosecutor_caused_harm",
                },
            ),
            lx.data.Extraction(
                extraction_class="policy_action",
                extraction_text="suspects they arrest are quickly released without charges",
                attributes={
                    "action_type": "declined_to_prosecute",
                    "domain": "general",
                    "framing": "negative",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_attribution",
                extraction_text="Recall organizers said the crime statistics prove",
                attributes={
                    "source_type": "advocacy_group",
                    "stance_toward_prosecutor": "critical",
                },
            ),
        ],
    ),
    # Example 2: Neutral article about a traditional prosecutor
    lx.data.ExampleData(
        text=(
            "Brooke Jenkins, who replaced Boudin after the recall, announced a "
            "new initiative targeting retail theft rings in the downtown area. "
            "Jenkins said her office would file felony charges against organized "
            "shoplifting groups, reversing Boudin's practice of treating most "
            "retail theft as misdemeanors. Supervisor Matt Dorsey praised the "
            "move. Defense attorney Niki Solis warned that harsher penalties "
            "would disproportionately affect low-income communities without "
            "reducing crime."
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="policy_action",
                extraction_text="file felony charges against organized shoplifting groups",
                attributes={
                    "action_type": "enhanced_prosecution",
                    "domain": "property_crime",
                    "framing": "positive",
                },
            ),
            lx.data.Extraction(
                extraction_class="comparison",
                extraction_text="reversing Boudin's practice of treating most retail theft as misdemeanors",
                attributes={
                    "compared_to": "predecessor",
                    "dimension": "toughness",
                    "who_favored": "current",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_attribution",
                extraction_text="Supervisor Matt Dorsey praised the move",
                attributes={
                    "source_type": "politician",
                    "stance_toward_prosecutor": "supportive",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_attribution",
                extraction_text="Defense attorney Niki Solis warned that harsher penalties would disproportionately affect low-income communities",
                attributes={
                    "source_type": "defense_attorney",
                    "stance_toward_prosecutor": "critical",
                },
            ),
        ],
    ),
    # Example 3: Mixed coverage about Alameda
    lx.data.ExampleData(
        text=(
            "Alameda County DA Pamela Price faces a recall effort barely a year "
            "into her term. Critics say Price has been too lenient, pointing to "
            "cases where violent offenders received reduced sentences. The Save "
            "Alameda for Everyone committee cited three homicide cases where "
            "Price's office offered plea deals. Price responded that her office "
            "has actually increased the conviction rate for violent felonies "
            "compared to her predecessor Nancy O'Malley."
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="claim_against_prosecutor",
                extraction_text="Price has been too lenient",
                attributes={
                    "claim_type": "policy",
                    "specificity": "vague",
                    "evidence_cited": "none",
                },
            ),
            lx.data.Extraction(
                extraction_class="claim_against_prosecutor",
                extraction_text="violent offenders received reduced sentences",
                attributes={
                    "claim_type": "performance",
                    "specificity": "specific",
                    "evidence_cited": "anecdotal",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_attribution",
                extraction_text="The Save Alameda for Everyone committee cited three homicide cases",
                attributes={
                    "source_type": "advocacy_group",
                    "stance_toward_prosecutor": "critical",
                },
            ),
            lx.data.Extraction(
                extraction_class="policy_action",
                extraction_text="Price's office offered plea deals",
                attributes={
                    "action_type": "reduced_charges",
                    "domain": "violent_crime",
                    "framing": "negative",
                },
            ),
            lx.data.Extraction(
                extraction_class="comparison",
                extraction_text="increased the conviction rate for violent felonies compared to her predecessor Nancy O'Malley",
                attributes={
                    "compared_to": "predecessor",
                    "dimension": "case_outcomes",
                    "who_favored": "current",
                },
            ),
            lx.data.Extraction(
                extraction_class="source_attribution",
                extraction_text="Price responded that her office has actually increased the conviction rate",
                attributes={
                    "source_type": "prosecutor",
                    "stance_toward_prosecutor": "supportive",
                },
            ),
        ],
    ),
]


# ── Extraction logic ─────────────────────────────────────────────────────

CHECKPOINT_INTERVAL = 50  # save after every N articles


def load_checkpoint(jsonl_path: Path) -> set[str]:
    """Return set of article_ids already successfully processed."""
    done = set()
    if jsonl_path.exists():
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if "article_id" in obj and obj.get("error") is None:
                        done.add(obj["article_id"])
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
            prompt_description=EXTRACTION_PROMPT,
            examples=FEW_SHOT_EXAMPLES,
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
    max_articles: int = 0,
) -> list[dict]:
    """Process all articles, with checkpointing and progress bar."""

    # Guard against duplicate article_id rows in input.
    df = df.drop_duplicates(subset=["article_id"]).copy()

    # Load checkpoint (IDs are stored as strings in JSONL)
    done_ids_str = load_checkpoint(EXTRACTIONS_JSONL) if resume else set()
    if done_ids_str:
        logger.info(f"Resuming: {len(done_ids_str)} articles already processed")

    # Match checkpoint ID types to DataFrame (parquet stores int64)
    df_id_dtype = df["article_id"].dtype
    if pd.api.types.is_integer_dtype(df_id_dtype):
        done_ids = set()
        for x in done_ids_str:
            try:
                done_ids.add(int(x))
            except (TypeError, ValueError):
                continue
    else:
        done_ids = done_ids_str

    # Filter to remaining
    remaining = df[~df["article_id"].isin(done_ids)]

    # Shuffle for representative partial samples (avoids corpus-order bias)
    remaining = remaining.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

    # Cap per-run article count (for RPD-limited daily runs)
    if max_articles > 0 and len(remaining) > max_articles:
        remaining = remaining.iloc[:max_articles]
        logger.info(f"Capped to {max_articles} articles for this run (RPD limit)")

    logger.info(f"Processing {len(remaining)} articles ({len(done_ids)} already done)")

    results = []
    jsonl_f = open(EXTRACTIONS_JSONL, "a" if resume else "w", encoding="utf-8")

    try:
        for i, (_, row) in enumerate(tqdm(remaining.iterrows(),
                                          total=len(remaining),
                                          desc="Extracting")):
            article_id = str(row["article_id"])
            # row.get(col, default) returns NaN (not the default) when the
            # column exists but the value is null — resolve explicitly so a
            # null full_text falls back to body instead of the string "nan".
            full_text = row.get("full_text")
            body = row.get("body")
            if pd.notna(full_text) and str(full_text).strip():
                text = str(full_text)
            elif pd.notna(body) and str(body).strip():
                text = str(body)
            else:
                logger.warning(f"Article {article_id}: no usable text; recording error row")
                result = {
                    "article_id": article_id,
                    "extractions": [],
                    "error": "empty_text",
                }
                results.append(result)
                jsonl_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                continue

            # Truncate very long articles to ~3000 words (Gemini context is large
            # but we want focused extraction near prosecutor mentions)
            words = text.split()
            if len(words) > 3000:
                text = " ".join(words[:3000])

            result = extract_article(
                article_id=article_id,
                text=text,
                model_id=model_id,
                api_key=api_key,
                max_workers=1,  # per-article parallelism (langextract internal)
            )

            # Stop gracefully on rate-limit errors (don't record failed entry)
            if result["error"] and "429" in str(result["error"]):
                logger.warning(
                    f"Hit RPD limit after {i+1} articles. Stopping gracefully. "
                    f"Re-run with --resume tomorrow."
                )
                break

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


def deduplicate_results_by_article(results: list[dict]) -> list[dict]:
    """Keep one extraction result per article_id.

    Preference order when duplicates exist:
      1) successful record (error is None) over failed record
      2) latest record when both are successful or both failed
    """
    if not results:
        return results

    chosen: dict[str, dict] = {}
    had_dupes = 0
    for res in results:
        aid = str(res.get("article_id"))
        if not aid:
            continue

        prev = chosen.get(aid)
        if prev is None:
            chosen[aid] = res
            continue

        had_dupes += 1
        prev_ok = prev.get("error") is None
        curr_ok = res.get("error") is None

        if curr_ok and not prev_ok:
            chosen[aid] = res
        elif curr_ok == prev_ok:
            # Same status (both success or both error): keep latest.
            chosen[aid] = res

    if had_dupes > 0:
        logger.warning(
            f"Detected duplicate extraction records: {had_dupes} extra rows across "
            f"{len(results)} JSONL entries. Using {len(chosen)} unique article_ids."
        )

    return list(chosen.values())


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

    flat = pd.DataFrame(rows)
    if flat.empty:
        return flat

    # Keep only rows that map to the active analysis corpus.
    before = len(flat)
    flat = flat[flat["prosecutor_type"].notna()].copy()
    dropped = before - len(flat)
    if dropped > 0:
        logger.warning(f"Dropped {dropped} extraction rows not mapped to active prosecutor articles")
    return flat


def build_article_summary(results: list[dict], df: pd.DataFrame) -> pd.DataFrame:
    """Build per-article summary of extraction counts."""
    summaries = []
    for res in results:
        aid = res["article_id"]
        exts = res.get("extractions", [])

        counts = Counter(e.get("extraction_class") for e in exts)
        summary = {
            "article_id": aid,
            "n_extractions_total": len(exts),
            "n_claims": counts.get("claim_against_prosecutor", 0),
            "n_sources": counts.get("source_attribution", 0),
            "n_causal": counts.get("causal_claim", 0),
            "n_policy_actions": counts.get("policy_action", 0),
            "n_comparisons": counts.get("comparison", 0),
            "error": res.get("error"),
        }

        # Count specific attribute values
        for ext in exts:
            attrs = ext.get("attributes") or {}
            cls = ext.get("extraction_class")

            if cls == "source_attribution":
                stype = attrs.get("source_type", "unknown")
                summary[f"source_{stype}"] = summary.get(f"source_{stype}", 0) + 1
                stance = attrs.get("stance_toward_prosecutor", "neutral")
                summary[f"stance_{stance}"] = summary.get(f"stance_{stance}", 0) + 1

            elif cls == "causal_claim":
                direction = attrs.get("direction", "ambiguous")
                summary[f"causal_{direction}"] = summary.get(f"causal_{direction}", 0) + 1
                strength = attrs.get("causal_strength", "implied")
                summary[f"causal_strength_{strength}"] = summary.get(f"causal_strength_{strength}", 0) + 1

            elif cls == "claim_against_prosecutor":
                ctype = attrs.get("claim_type", "unknown")
                summary[f"claim_{ctype}"] = summary.get(f"claim_{ctype}", 0) + 1
                spec = attrs.get("specificity", "vague")
                summary[f"specificity_{spec}"] = summary.get(f"specificity_{spec}", 0) + 1

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

    # Keep only current corpus articles with prosecutor attribution.
    result = result[result["prosecutor_type"].notna()].copy()
    return result


def run_statistical_analysis(ext_df: pd.DataFrame, summary_df: pd.DataFrame) -> dict:
    """Compute group-level statistics on extraction patterns."""
    stats = {}

    # Failed extractions previously entered statistics as zero-count articles,
    # attenuating group means non-randomly. Exclude them and report the count.
    if "error" in summary_df.columns:
        n_err = int(summary_df["error"].notna().sum())
        if n_err > 0:
            logger.warning(f"Excluding {n_err} articles with extraction errors from statistics")
        summary_df = summary_df[summary_df["error"].isna()].copy()
        stats["n_error_articles_excluded"] = n_err

    prog = summary_df[summary_df["prosecutor_type"] == "Progressive"]
    trad = summary_df[summary_df["prosecutor_type"] == "Traditional"]

    # 1. Extraction volume comparison
    for col in ["n_claims", "n_sources", "n_causal", "n_policy_actions", "n_comparisons"]:
        p_mean = prog[col].mean() if col in prog.columns else 0
        t_mean = trad[col].mean() if col in trad.columns else 0
        stats[f"mean_{col}_progressive"] = float(p_mean)
        stats[f"mean_{col}_traditional"] = float(t_mean)

    # 2. Source type distribution
    source_types = ["police", "victim", "defense_attorney", "prosecutor",
                    "politician", "community_member", "journalist", "expert",
                    "advocacy_group"]
    source_dist = {"Progressive": {}, "Traditional": {}}
    if not ext_df.empty and "extraction_class" in ext_df.columns:
        sources = ext_df[ext_df["extraction_class"] == "source_attribution"]
        for ptype in ["Progressive", "Traditional"]:
            subset = sources[sources["prosecutor_type"] == ptype]
            total = len(subset)
            src_series = subset.get("attr_source_type", pd.Series(dtype=object))
            known_total = 0
            for stype in source_types:
                n = int((src_series == stype).sum())
                source_dist[ptype][stype] = n
                known_total += n
            # Keep denominators honest when model outputs unmapped/missing values.
            source_dist[ptype]["other_or_missing"] = int(max(total - known_total, 0))
            source_dist[ptype]["total"] = int(total)
    stats["source_type_distribution"] = source_dist

    # Chi-square on source types (if enough data)
    try:
        ct = pd.DataFrame(source_dist).fillna(0).drop("total", errors="ignore")
        if ct.sum().sum() > 0 and (ct > 0).any().all():
            chi2, p, dof, _ = chi2_contingency(ct.values)
            stats["source_type_chi2"] = float(chi2)
            stats["source_type_chi2_p"] = float(p)
            stats["source_type_chi2_dof"] = int(dof)
    except Exception:
        pass

    # 3. Source stance comparison
    stance_dist = {"Progressive": {}, "Traditional": {}}
    if not ext_df.empty and "extraction_class" in ext_df.columns:
        sources = ext_df[ext_df["extraction_class"] == "source_attribution"]
        for ptype in ["Progressive", "Traditional"]:
            subset = sources[sources["prosecutor_type"] == ptype]
            for stance in ["critical", "supportive", "neutral"]:
                n = (subset.get("attr_stance_toward_prosecutor", pd.Series()) == stance).sum()
                stance_dist[ptype][stance] = int(n)
    stats["source_stance_distribution"] = stance_dist

    # 4. Causal claim direction
    causal_dist = {"Progressive": {}, "Traditional": {}}
    if not ext_df.empty and "extraction_class" in ext_df.columns:
        causal = ext_df[ext_df["extraction_class"] == "causal_claim"]
        for ptype in ["Progressive", "Traditional"]:
            subset = causal[causal["prosecutor_type"] == ptype]
            for direction in ["prosecutor_caused_harm", "prosecutor_helped", "ambiguous"]:
                n = (subset.get("attr_direction", pd.Series()) == direction).sum()
                causal_dist[ptype][direction] = int(n)
    stats["causal_direction_distribution"] = causal_dist

    # 5. Claim type distribution
    claim_dist = {"Progressive": {}, "Traditional": {}}
    if not ext_df.empty and "extraction_class" in ext_df.columns:
        claims = ext_df[ext_df["extraction_class"] == "claim_against_prosecutor"]
        for ptype in ["Progressive", "Traditional"]:
            subset = claims[claims["prosecutor_type"] == ptype]
            for ctype in ["performance", "policy", "character", "competence"]:
                n = (subset.get("attr_claim_type", pd.Series()) == ctype).sum()
                claim_dist[ptype][ctype] = int(n)
    stats["claim_type_distribution"] = claim_dist

    # 6. Policy action framing
    action_dist = {"Progressive": {}, "Traditional": {}}
    if not ext_df.empty and "extraction_class" in ext_df.columns:
        actions = ext_df[ext_df["extraction_class"] == "policy_action"]
        for ptype in ["Progressive", "Traditional"]:
            subset = actions[actions["prosecutor_type"] == ptype]
            for framing in ["positive", "negative", "neutral"]:
                n = (subset.get("attr_framing", pd.Series()) == framing).sum()
                action_dist[ptype][framing] = int(n)
    stats["policy_action_framing"] = action_dist

    # 7. Comparison direction
    comp_dist = {"Progressive": {}, "Traditional": {}}
    if not ext_df.empty and "extraction_class" in ext_df.columns:
        comps = ext_df[ext_df["extraction_class"] == "comparison"]
        for ptype in ["Progressive", "Traditional"]:
            subset = comps[comps["prosecutor_type"] == ptype]
            for favored in ["current", "predecessor", "neither"]:
                n = (subset.get("attr_who_favored", pd.Series()) == favored).sum()
                comp_dist[ptype][favored] = int(n)
    stats["comparison_direction"] = comp_dist

    # 8. Per-prosecutor extraction counts
    per_prosecutor = {}
    for p in PROSECUTORS:
        p_sub = summary_df[summary_df["primary_prosecutor"] == p.name]
        if len(p_sub) == 0:
            continue
        per_prosecutor[p.name] = {
            "n_articles": int(len(p_sub)),
            "mean_claims": float(p_sub["n_claims"].mean()),
            "mean_sources": float(p_sub["n_sources"].mean()),
            "mean_causal": float(p_sub["n_causal"].mean()),
            "mean_policy_actions": float(p_sub["n_policy_actions"].mean()),
            "mean_comparisons": float(p_sub["n_comparisons"].mean()),
            "mean_total_extractions": float(p_sub["n_extractions_total"].mean()),
        }
    stats["per_prosecutor"] = per_prosecutor

    return stats


def print_analysis_report(stats: dict):
    """Log a readable summary of the extraction analysis."""
    logger.info("\n" + "=" * 70)
    logger.info("LANGEXTRACT ANALYSIS REPORT")
    logger.info("=" * 70)

    # Extraction volume
    logger.info("\n── Extraction Volume (mean per article) ──")
    for metric in ["n_claims", "n_sources", "n_causal", "n_policy_actions", "n_comparisons"]:
        p = stats.get(f"mean_{metric}_progressive", 0)
        t = stats.get(f"mean_{metric}_traditional", 0)
        label = metric.replace("n_", "").replace("_", " ").title()
        logger.info(f"  {label:25s}  Progressive: {p:.2f}   Traditional: {t:.2f}")

    # Source types
    logger.info("\n── Source Type Distribution ──")
    sd = stats.get("source_type_distribution", {})
    for stype in ["police", "victim", "prosecutor", "politician", "defense_attorney",
                  "community_member", "expert", "advocacy_group", "journalist",
                  "other_or_missing"]:
        p = sd.get("Progressive", {}).get(stype, 0)
        t = sd.get("Traditional", {}).get(stype, 0)
        if p + t > 0:
            logger.info(f"  {stype:25s}  Progressive: {p:5d}   Traditional: {t:5d}")

    if "source_type_chi2" in stats:
        logger.info(f"  Chi2 = {stats['source_type_chi2']:.2f}, "
                     f"p = {stats['source_type_chi2_p']:.6f}")

    # Source stance
    logger.info("\n── Source Stance (who is critical/supportive?) ──")
    ss = stats.get("source_stance_distribution", {})
    for stance in ["critical", "supportive", "neutral"]:
        p = ss.get("Progressive", {}).get(stance, 0)
        t = ss.get("Traditional", {}).get(stance, 0)
        logger.info(f"  {stance:25s}  Progressive: {p:5d}   Traditional: {t:5d}")

    # Causal claims
    logger.info("\n── Causal Claim Direction ──")
    cd = stats.get("causal_direction_distribution", {})
    for direction in ["prosecutor_caused_harm", "prosecutor_helped", "ambiguous"]:
        p = cd.get("Progressive", {}).get(direction, 0)
        t = cd.get("Traditional", {}).get(direction, 0)
        if p + t > 0:
            logger.info(f"  {direction:30s}  Progressive: {p:5d}   Traditional: {t:5d}")

    # Claim types
    logger.info("\n── Claim Types ──")
    ct = stats.get("claim_type_distribution", {})
    for ctype in ["performance", "policy", "character", "competence"]:
        p = ct.get("Progressive", {}).get(ctype, 0)
        t = ct.get("Traditional", {}).get(ctype, 0)
        if p + t > 0:
            logger.info(f"  {ctype:25s}  Progressive: {p:5d}   Traditional: {t:5d}")

    # Policy action framing
    logger.info("\n── Policy Action Framing ──")
    af = stats.get("policy_action_framing", {})
    for framing in ["positive", "negative", "neutral"]:
        p = af.get("Progressive", {}).get(framing, 0)
        t = af.get("Traditional", {}).get(framing, 0)
        if p + t > 0:
            logger.info(f"  {framing:25s}  Progressive: {p:5d}   Traditional: {t:5d}")

    # Per-prosecutor
    logger.info("\n── Per-Prosecutor Mean Extractions ──")
    pp = stats.get("per_prosecutor", {})
    for name, vals in pp.items():
        logger.info(f"  {name}: {vals['mean_total_extractions']:.1f} extractions/article "
                     f"({vals['n_articles']} articles)")

    logger.info("\nDone.")


# ── Visualization ────────────────────────────────────────────────────────

def generate_visualization(jsonl_path: Path, output_html: Path):
    """Generate interactive HTML visualization from langextract results."""
    import io as _io

    # Temporarily redirect stdout to utf-8 to prevent Windows cp1252 errors
    # from langextract's internal print statements
    old_stdout = sys.stdout
    temp_stdout = None
    try:
        if sys.platform == "win32":
            temp_stdout = _io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            sys.stdout = temp_stdout
        html = lx.visualize(str(jsonl_path))
        if html:
            output_html.write_text(html, encoding="utf-8")
            logger.info(f"Visualization saved to {output_html}")
        else:
            logger.warning("langextract.visualize returned empty output")
    except Exception as e:
        logger.warning(f"Could not generate visualization: {e}")
    finally:
        # Detach wrapper so it doesn't close the underlying stdout buffer.
        if temp_stdout is not None:
            try:
                temp_stdout.flush()
                temp_stdout.detach()
            except Exception:
                pass
        sys.stdout = old_stdout


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    setup_logging()

    # Suppress duplicate logging from langextract/absl internals
    import logging as _logging
    _logging.getLogger("absl").setLevel(_logging.WARNING)
    _logging.getLogger("langextract").setLevel(_logging.WARNING)

    parser = argparse.ArgumentParser(description="Step 08: langextract grounded extraction")
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
    parser.add_argument("--max-articles", type=int, default=0,
                        help="Max articles to process this run (0 = all). "
                             "Use ~1800 to stay under Gemini 10K RPD limit.")
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

        with timer("Extraction"):
            results = run_extraction(
                df=df,
                model_id=args.model,
                api_key=api_key,
                max_workers=args.max_workers,
                delay=args.delay,
                resume=args.resume,
                max_articles=args.max_articles,
            )

        n_success = sum(1 for r in results if r["error"] is None)
        n_errors = sum(1 for r in results if r["error"] is not None)
        n_total_exts = sum(r["n_extractions"] for r in results)
        logger.info(f"Extraction complete: {n_success} succeeded, {n_errors} errors, "
                     f"{n_total_exts} total extractions")

    # Analysis phase
    if not EXTRACTIONS_JSONL.exists():
        logger.error(f"No extraction results found at {EXTRACTIONS_JSONL}")
        sys.exit(1)

    with timer("Analysis"):
        raw_results = load_all_extractions(EXTRACTIONS_JSONL)
        logger.info(f"Loaded {len(raw_results)} extraction results from JSONL")
        all_results = deduplicate_results_by_article(raw_results)
        logger.info(f"Using {len(all_results)} unique per-article extraction results")

        # Flatten to per-extraction DataFrame
        ext_df = flatten_extractions(all_results, df)
        logger.info(f"Flattened to {len(ext_df)} individual extractions")

        # Build per-article summary
        summary_df = build_article_summary(all_results, df)
        save_parquet(summary_df, EXTRACTIONS_PARQUET)

        # Run statistical analysis
        stats = run_statistical_analysis(ext_df, summary_df)

        # Save stats
        with open(EXTRACTION_STATS_JSON, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Stats saved to {EXTRACTION_STATS_JSON}")

        # Print report
        print_analysis_report(stats)

    # Visualization
    with timer("Visualization"):
        generate_visualization(EXTRACTIONS_JSONL, EXTRACTION_VIZ_HTML)

    logger.info(f"\nAll outputs in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
