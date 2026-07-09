"""
Build local review packets for RA validation of the Step 08 langextract output.

Blinding design:
- RA-facing CSVs contain only article/extraction content plus empty ra_*
  columns. Prosecutor ideology (prosecutor_type), model outputs (stance,
  frame, bias scores, structural counts), sampling-bucket names, and heuristic
  flags are written to PI-side key files under generated/keys/.
- Key files must NEVER be shared with the RA. summarize_ra_labels.py joins
  them back at summary time on packet_id.

Multi-coder design:
- --coder-id namespaces the RA-facing output (generated/<coder_id>/...).
- Within each random sampling bucket, a seeded overlap subset
  (--overlap-fraction, default 0.2) is drawn with a coder-independent seed,
  so it is identical for every coder; the remaining random rows are drawn
  with a coder-specific seed. Purposive (top-k) rows are deterministic and
  therefore also identical across coders. packet_id is derived from
  article_id (and extraction_index), so the same unit has the same packet_id
  in every coder's packet.

The generated CSVs include local article excerpts and therefore stay out of Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from config import (  # noqa: E402
    ATTRIBUTED_PARQUET,
    BIAS_PARQUET,
    EXTRACTIONS_JSONL,
    EXTRACTIONS_PARQUET,
    FRAMES_PARQUET,
)


OUTPUT_DIR = REPO_ROOT / "ra_langextract_validation" / "generated"
KEYS_DIR = OUTPUT_DIR / "keys"

DEFAULT_ARTICLE_SAMPLE = 100
DEFAULT_CASE_SAMPLE = 120
DEFAULT_RECALL_SAMPLE = 40
DEFAULT_DRIFT_SAMPLE = 40
DEFAULT_SOURCE_SAMPLE = 60
DEFAULT_CAUSAL_SAMPLE = 60
DEFAULT_CLAIM_SAMPLE = 20
DEFAULT_POLICY_SAMPLE = 20
DEFAULT_COMPARISON_SAMPLE = 20
DEFAULT_SEED = 42
DEFAULT_OVERLAP_FRACTION = 0.2

# --------------------------------------------------------------------------
# Stance-bucket thresholds.
#
# These are VALIDATION-HARNESS definitions, local to this workspace. The
# pipeline (04_bias_detection.py) reports a continuous score_stance and does
# not bucket it; the +/- threshold below exists only so the RA's categorical
# stance labels can be compared against the model score. The sensitivity
# grid is used by summarize_ra_labels.py to show how agreement moves with
# the threshold choice.
# --------------------------------------------------------------------------
STANCE_BUCKET_THRESHOLD = 0.15
STANCE_SENSITIVITY_THRESHOLDS = (0.10, 0.15, 0.20)

ALLOWED_VALUES = {
    "source_type": {
        "police",
        "victim",
        "defense_attorney",
        "prosecutor",
        "politician",
        "community_member",
        "journalist",
        "expert",
        "advocacy_group",
    },
    "stance_toward_prosecutor": {"critical", "supportive", "neutral"},
    "claim_type": {"performance", "policy", "character", "competence"},
    "specificity": {"vague", "specific", "quantified"},
    "effect": {
        "crime_increase",
        "public_safety_decline",
        "case_outcome",
        "community_impact",
        "positive_outcome",
    },
    "causal_strength": {"explicit", "implied", "speculative"},
    "direction": {"prosecutor_caused_harm", "prosecutor_helped", "ambiguous"},
    "action_type": {
        "declined_to_prosecute",
        "reduced_charges",
        "new_policy",
        "fired_staff",
        "reversed_predecessor",
        "enhanced_prosecution",
        "other",
    },
    "domain": {
        "drugs",
        "property_crime",
        "violent_crime",
        "bail",
        "sentencing",
        "staffing",
        "juvenile",
        "general",
    },
    "framing": {"positive", "negative", "neutral"},
    "compared_to": {"predecessor", "other_prosecutor", "general_standard"},
    "dimension": {"toughness", "case_outcomes", "policy", "competence", "ideology"},
    "who_favored": {"current", "predecessor", "neither"},
}

REPORTING_PATTERNS = re.compile(
    r"\b(?:said|says|according to|argued|warned|claimed|critics say|supporters say|"
    r"opponents say|lawsuit|report|court documents?)\b",
    flags=re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article-sample-size", type=int, default=DEFAULT_ARTICLE_SAMPLE)
    parser.add_argument("--case-sample-size", type=int, default=DEFAULT_CASE_SAMPLE)
    parser.add_argument("--recall-sample-size", type=int, default=DEFAULT_RECALL_SAMPLE)
    parser.add_argument(
        "--drift-sample-size",
        type=int,
        default=DEFAULT_DRIFT_SAMPLE,
        help="Packet 02: schema-drift bucket size.",
    )
    parser.add_argument(
        "--source-sample-size",
        type=int,
        default=DEFAULT_SOURCE_SAMPLE,
        help="Packet 02: source_attribution bucket size.",
    )
    parser.add_argument(
        "--causal-sample-size",
        type=int,
        default=DEFAULT_CAUSAL_SAMPLE,
        help="Packet 02: causal_claim bucket size.",
    )
    parser.add_argument(
        "--claim-sample-size",
        type=int,
        default=DEFAULT_CLAIM_SAMPLE,
        help="Packet 02: claim_against_prosecutor bucket size.",
    )
    parser.add_argument(
        "--policy-sample-size",
        type=int,
        default=DEFAULT_POLICY_SAMPLE,
        help="Packet 02: policy_action bucket size.",
    )
    parser.add_argument(
        "--comparison-sample-size",
        type=int,
        default=DEFAULT_COMPARISON_SAMPLE,
        help="Packet 02: comparison bucket size.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--coder-id",
        type=str,
        default="ra1",
        help="Coder identifier. RA-facing packets go to generated/<coder-id>/.",
    )
    parser.add_argument(
        "--overlap-fraction",
        type=float,
        default=DEFAULT_OVERLAP_FRACTION,
        help="Fraction of each random bucket drawn with a coder-independent "
        "seed so the rows are identical for every coder (reliability overlap).",
    )
    return parser.parse_args()


def coder_seed_offset(coder_id: str) -> int:
    """Stable per-coder integer offset for coder-specific random draws."""
    digest = hashlib.sha256(coder_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 1_000_000


def require_files(paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        joined = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Missing required local files:\n{joined}")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def split_paragraphs(text: str) -> list[str]:
    raw = str(text or "")
    parts = [normalize_text(part) for part in re.split(r"\n\s*\n", raw)]
    parts = [part for part in parts if part]
    if parts:
        return parts
    fallback = normalize_text(raw)
    return [fallback] if fallback else []


def truncate(text: str, max_chars: int) -> str:
    clean = normalize_text(text)
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def word_overlap_score(needle: str, haystack: str) -> int:
    needle_words = {word for word in re.findall(r"[A-Za-z0-9']+", needle.lower()) if len(word) > 3}
    if not needle_words:
        return 0
    haystack_words = set(re.findall(r"[A-Za-z0-9']+", haystack.lower()))
    return len(needle_words & haystack_words)


def find_context_excerpt(article_text: str, extraction_text: str, max_chars: int = 900) -> str:
    paragraphs = split_paragraphs(article_text)
    needle = normalize_text(extraction_text)
    if not paragraphs:
        return ""
    if needle:
        needle_lower = needle.lower()
        for paragraph in paragraphs:
            if needle_lower in paragraph.lower():
                return truncate(paragraph, max_chars)
        ranked = sorted(
            paragraphs,
            key=lambda paragraph: word_overlap_score(needle, paragraph),
            reverse=True,
        )
        if ranked and word_overlap_score(needle, ranked[0]) > 0:
            return truncate(ranked[0], max_chars)
    return truncate(paragraphs[0], max_chars)


def build_focus_excerpt(article_text: str, prosecutor_name: str, extraction_texts: list[str]) -> str:
    paragraphs = split_paragraphs(article_text)
    if not paragraphs:
        return ""

    surname = prosecutor_name.split()[-1].lower() if prosecutor_name else ""
    scored: list[tuple[int, int, str]] = []
    for idx, paragraph in enumerate(paragraphs):
        lower = paragraph.lower()
        score = 0
        if surname and surname in lower:
            score += 4
        for text in extraction_texts[:5]:
            if not text:
                continue
            if normalize_text(text).lower() in lower:
                score += 5
            else:
                score += min(word_overlap_score(text, paragraph), 3)
        if REPORTING_PATTERNS.search(paragraph):
            score += 1
        scored.append((score, idx, paragraph))

    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen: list[str] = []
    used_idx: set[int] = set()
    for score, idx, paragraph in scored:
        if idx in used_idx:
            continue
        if score <= 0 and chosen:
            continue
        chosen.append(paragraph)
        used_idx.add(idx)
        if len(chosen) >= 3:
            break

    if not chosen:
        chosen = paragraphs[:3]
    return truncate(" || ".join(chosen), 2400)


def deduplicate_results(results: list[dict]) -> list[dict]:
    chosen: dict[str, dict] = {}
    for result in results:
        article_id = str(result.get("article_id", ""))
        if not article_id:
            continue
        previous = chosen.get(article_id)
        if previous is None:
            chosen[article_id] = result
            continue
        prev_ok = previous.get("error") is None
        curr_ok = result.get("error") is None
        if curr_ok and not prev_ok:
            chosen[article_id] = result
        elif curr_ok == prev_ok:
            chosen[article_id] = result
    return list(chosen.values())


def load_results() -> list[dict]:
    results = []
    with EXTRACTIONS_JSONL.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            results.append(json.loads(line))
    return deduplicate_results(results)


def flatten_extractions(results: list[dict]) -> pd.DataFrame:
    rows = []
    for result in results:
        article_id = str(result.get("article_id", ""))
        for idx, extraction in enumerate(result.get("extractions", []), start=1):
            attrs = extraction.get("attributes") or {}
            row = {
                "article_id": article_id,
                "extraction_index": idx,
                "extraction_class": extraction.get("extraction_class"),
                "extraction_text": extraction.get("extraction_text", ""),
                "raw_attributes_json": json.dumps(attrs, ensure_ascii=True, sort_keys=True),
            }
            for key, value in attrs.items():
                row[f"attr_{key}"] = value
            rows.append(row)
    return pd.DataFrame(rows)


def invalid_attributes(row: pd.Series) -> str:
    invalid = []
    for key, allowed in ALLOWED_VALUES.items():
        value = row.get(f"attr_{key}")
        if pd.isna(value) or value in ("", None):
            continue
        if value not in allowed:
            invalid.append(f"{key}={value}")
    return "; ".join(invalid)


def model_stance_bucket(score: float, threshold: float = STANCE_BUCKET_THRESHOLD) -> str:
    if pd.isna(score):
        return ""
    if score <= -threshold:
        return "critical"
    if score >= threshold:
        return "supportive"
    return "neutral_or_mixed"


def collect_extraction_texts(flat: pd.DataFrame) -> dict[str, list[str]]:
    grouped = flat.groupby("article_id")["extraction_text"].apply(list)
    return grouped.to_dict()


def load_article_table() -> pd.DataFrame:
    attributed = pd.read_parquet(ATTRIBUTED_PARQUET).copy()
    bias = pd.read_parquet(BIAS_PARQUET)[
        ["article_id", "score_stance", "composite_bias_score"]
    ].copy()
    frames_all = pd.read_parquet(FRAMES_PARQUET)
    # frame_method is new in the regenerated pipeline; older 05 files lack it.
    frame_cols = ["article_id", "dominant_frame"]
    if "frame_method" in frames_all.columns:
        frame_cols.append("frame_method")
    frames = frames_all[frame_cols].copy()
    summary = pd.read_parquet(EXTRACTIONS_PARQUET).copy()

    for frame in (attributed, bias, frames, summary):
        frame["article_id"] = frame["article_id"].astype(str)

    articles = attributed.merge(bias, on="article_id", how="left")
    articles = articles.merge(frames, on="article_id", how="left")
    if "frame_method" not in articles.columns:
        articles["frame_method"] = ""
    articles = articles.merge(summary, on="article_id", how="left", suffixes=("", "_step08"))
    articles["date"] = pd.to_datetime(articles["date"]).dt.strftime("%Y-%m-%d")
    articles["model_stance_bucket"] = articles["score_stance"].apply(model_stance_bucket)
    numeric_cols = [col for col in articles.columns if col.startswith(("n_", "source_", "stance_", "causal_"))]
    for col in numeric_cols:
        articles[col] = articles[col].fillna(0)
    return articles


def sample_rows(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if n <= 0 or df.empty:
        return df.iloc[0:0].copy()
    if len(df) <= n:
        return df.copy()
    return df.sample(n=n, random_state=seed).copy()


def split_overlap_sample(
    pool: pd.DataFrame,
    n: int,
    base_seed: int,
    coder_offset: int,
    overlap_fraction: float,
) -> pd.DataFrame:
    """
    Draw n rows from pool: an overlap portion sampled with a coder-independent
    seed (identical for every coder) plus a coder-specific remainder.

    Adds a boolean `_overlap` column.
    """
    empty = pool.iloc[0:0].copy()
    empty["_overlap"] = pd.Series(dtype=bool)
    if n <= 0 or pool.empty:
        return empty
    n = min(n, len(pool))
    n_overlap = min(n, max(1, round(n * overlap_fraction)))
    overlap = pool.sample(n=n_overlap, random_state=base_seed).copy()
    overlap["_overlap"] = True
    remainder_pool = pool.drop(overlap.index)
    n_rest = min(n - n_overlap, len(remainder_pool))
    if n_rest > 0:
        rest = remainder_pool.sample(n=n_rest, random_state=base_seed + coder_offset).copy()
        rest["_overlap"] = False
        return pd.concat([overlap, rest])
    return overlap


def yes_no(value) -> str:
    return "yes" if bool(value) else "no"


def build_article_validation_packet(
    articles: pd.DataFrame,
    article_extractions: dict[str, list[str]],
    n_total: int,
    seed: int,
    coder_offset: int,
    overlap_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (ra_packet, key) for packet 01."""
    n_per_bucket = max(n_total // 4, 1)
    progressive = articles[articles["prosecutor_type"] == "Progressive"].copy()
    traditional = articles[articles["prosecutor_type"] == "Traditional"].copy()

    progressive["priority_score"] = (
        progressive.get("causal_prosecutor_caused_harm", 0)
        + progressive.get("source_advocacy_group", 0)
        + progressive.get("source_politician", 0)
        + progressive.get("source_expert", 0)
        + progressive.get("stance_critical", 0)
        + progressive.get("n_claims", 0)
    )
    traditional["priority_score"] = (
        traditional.get("source_prosecutor", 0)
        + traditional.get("stance_neutral", 0)
        + traditional.get("n_sources", 0)
        + traditional.get("n_policy_actions", 0)
    )

    prog_priority = progressive.sort_values(["priority_score", "n_sources"], ascending=False).head(n_per_bucket)
    trad_priority = traditional.sort_values(["priority_score", "n_sources"], ascending=False).head(n_per_bucket)

    prog_random_pool = progressive[~progressive["article_id"].isin(prog_priority["article_id"])]
    trad_random_pool = traditional[~traditional["article_id"].isin(trad_priority["article_id"])]
    prog_random = split_overlap_sample(
        prog_random_pool, n_per_bucket, seed + 1, coder_offset, overlap_fraction
    )
    trad_random = split_overlap_sample(
        trad_random_pool, n_per_bucket, seed + 2, coder_offset, overlap_fraction
    )

    # (bucket name, bucket kind, frame, random-pool population)
    buckets = [
        ("progressive_high_contestation", "purposive", prog_priority, None),
        ("traditional_high_self_quote", "purposive", trad_priority, None),
        ("progressive_random", "random", prog_random, len(prog_random_pool)),
        ("traditional_random", "random", trad_random, len(trad_random_pool)),
    ]

    ra_rows = []
    key_rows = []
    for sample_bucket, bucket_kind, frame, population in buckets:
        for _, row in frame.iterrows():
            article_text = row.get("full_text") or row.get("body") or row.get("clean_text") or ""
            paragraphs = split_paragraphs(article_text)
            extraction_texts = article_extractions.get(str(row["article_id"]), [])
            packet_id = f"A-{row['article_id']}"
            ra_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": row["article_id"],
                    "date": row["date"],
                    "publication": row.get("publication", ""),
                    "headline": row.get("headline", ""),
                    "primary_prosecutor": row.get("primary_prosecutor", ""),
                    "lead_excerpt": truncate(" || ".join(paragraphs[:2]), 1800),
                    "focus_excerpt": build_focus_excerpt(
                        article_text,
                        str(row.get("primary_prosecutor", "")),
                        extraction_texts,
                    ),
                    "ra_article_stance": "",
                    "ra_dominant_frame": "",
                    "ra_dominant_frame_forced": "",
                    "ra_primary_issue": "",
                    "ra_prosecutor_is_subject": "",
                    "ra_quoted_criticism": "",
                    "ra_balanced_reporting": "",
                    "ra_implicit_causal_claim": "",
                    "ra_notes": "",
                }
            )
            key_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": row["article_id"],
                    "sample_bucket": sample_bucket,
                    "bucket_kind": bucket_kind,
                    # Purposive rows are deterministic, hence shared by all coders.
                    "overlap_set": yes_no(row.get("_overlap", bucket_kind == "purposive")),
                    "bucket_population": population if population is not None else "",
                    "prosecutor_type": row.get("prosecutor_type", ""),
                    "score_stance": row.get("score_stance"),
                    "model_stance_bucket": row.get("model_stance_bucket", ""),
                    "dominant_frame": row.get("dominant_frame", ""),
                    "frame_method": row.get("frame_method", ""),
                    "composite_bias_score": row.get("composite_bias_score"),
                    "n_claims": int(row.get("n_claims", 0)),
                    "n_sources": int(row.get("n_sources", 0)),
                    "n_causal": int(row.get("n_causal", 0)),
                    "n_policy_actions": int(row.get("n_policy_actions", 0)),
                    "n_comparisons": int(row.get("n_comparisons", 0)),
                    "source_prosecutor": int(row.get("source_prosecutor", 0)),
                    "source_advocacy_group": int(row.get("source_advocacy_group", 0)),
                    "source_politician": int(row.get("source_politician", 0)),
                    "source_expert": int(row.get("source_expert", 0)),
                    "stance_critical": int(row.get("stance_critical", 0)),
                    "stance_supportive": int(row.get("stance_supportive", 0)),
                    "stance_neutral": int(row.get("stance_neutral", 0)),
                }
            )

    ra_packet = pd.DataFrame(ra_rows).sort_values("packet_id").reset_index(drop=True)
    key = pd.DataFrame(key_rows).sort_values("packet_id").reset_index(drop=True)
    return ra_packet, key


def build_extraction_review_packet(
    articles: pd.DataFrame,
    flat: pd.DataFrame,
    bucket_sizes: dict[str, int],
    seed: int,
    coder_offset: int,
    overlap_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (ra_packet, key) for packet 02."""
    article_cols = [
        "article_id",
        "date",
        "publication",
        "headline",
        "primary_prosecutor",
        "prosecutor_type",
        "full_text",
        "score_stance",
        "composite_bias_score",
        "model_stance_bucket",
        "dominant_frame",
        "frame_method",
        "stance_critical",
        "stance_supportive",
    ]
    merged = flat.merge(articles[article_cols], on="article_id", how="left")

    # Guarantee every attr_* column referenced below exists, even when the
    # extraction run produced no instance of that attribute (a missing column
    # would otherwise turn merged.get(...) into a plain string -> .isin crash).
    for attr_key in ALLOWED_VALUES:
        col = f"attr_{attr_key}"
        if col not in merged.columns:
            merged[col] = ""

    merged["invalid_attributes"] = merged.apply(invalid_attributes, axis=1)
    merged["flag_schema_drift"] = merged["invalid_attributes"].ne("")
    merged["flag_balanced_article"] = (
        merged["stance_critical"].fillna(0).gt(0) & merged["stance_supportive"].fillna(0).gt(0)
    )
    # Reported-speech heuristic is restricted to the extraction span itself;
    # matching on the headline flagged unrelated extractions.
    merged["flag_reported_speech"] = merged["extraction_text"].fillna("").str.contains(
        REPORTING_PATTERNS
    )
    merged["flag_implicit_or_speculative"] = merged["attr_causal_strength"].fillna("").isin(
        ["implied", "speculative"]
    )
    merged["uid"] = merged["article_id"].astype(str) + "-" + merged["extraction_index"].astype(str)
    merged = merged.drop_duplicates(
        subset=["article_id", "extraction_index", "extraction_class", "extraction_text"]
    )

    # Bucket specs. The schema-drift bucket is cross-class and fully random;
    # the class buckets are half purposive (priority flags), half random.
    class_specs = [
        (
            "source_review",
            "source_attribution",
            bucket_sizes["source_review"],
            ["flag_reported_speech", "flag_balanced_article", "flag_schema_drift"],
            seed + 11,
        ),
        (
            "causal_review",
            "causal_claim",
            bucket_sizes["causal_review"],
            ["flag_implicit_or_speculative", "flag_balanced_article", "flag_schema_drift"],
            seed + 12,
        ),
        (
            "claim_review",
            "claim_against_prosecutor",
            bucket_sizes["claim_review"],
            ["flag_reported_speech", "flag_balanced_article", "flag_schema_drift"],
            seed + 13,
        ),
        (
            "policy_review",
            "policy_action",
            bucket_sizes["policy_review"],
            ["flag_balanced_article", "flag_schema_drift"],
            seed + 14,
        ),
        (
            "comparison_review",
            "comparison",
            bucket_sizes["comparison_review"],
            ["flag_balanced_article", "flag_schema_drift"],
            seed + 15,
        ),
    ]

    def overlap_count(n_random: int) -> int:
        if n_random <= 0:
            return 0
        return min(n_random, max(1, round(n_random * overlap_fraction)))

    # Two-phase sampling so that (a) no extraction appears twice in one
    # coder's packet (cross-bucket dedup) and (b) the purposive + overlap
    # portions are identical for every coder. Phase 1 draws all
    # coder-INDEPENDENT rows in a fixed bucket order using only
    # coder-independent exclusions; phase 2 draws each coder's remaining
    # random rows, excluding both the shared rows and this coder's earlier
    # draws.
    shared_uids: set[str] = set()
    plans: list[dict] = []

    # Phase 1a: schema-drift bucket (cross-class, fully random).
    drift_pool = merged[merged["flag_schema_drift"]].copy()
    n_drift = min(bucket_sizes["schema_drift"], len(drift_pool))
    n_drift_overlap = min(overlap_count(n_drift), len(drift_pool))
    drift_overlap = drift_pool.sample(n=n_drift_overlap, random_state=seed + 10).copy()
    shared_uids.update(drift_overlap["uid"])
    plans.append(
        {
            "bucket": "schema_drift",
            "purposive": drift_pool.iloc[0:0],
            "overlap": drift_overlap,
            "n_rest": n_drift - n_drift_overlap,
            "pool_mask": merged["flag_schema_drift"],
            "seed": seed + 10,
            "population": len(drift_pool),
        }
    )

    # Phase 1b: class buckets (purposive head + overlap portion).
    for bucket_name, extraction_class, n_bucket, priority_flags, bucket_seed in class_specs:
        pool = merged[
            merged["extraction_class"].eq(extraction_class) & ~merged["uid"].isin(shared_uids)
        ].copy()
        pool["priority_score"] = sum(pool[flag].astype(int) for flag in priority_flags)
        n_priority = min(n_bucket // 2, len(pool))
        priority = pool.sort_values(
            ["priority_score", "article_id", "extraction_index"],
            ascending=[False, True, True],
        ).head(n_priority)
        shared_uids.update(priority["uid"])
        remainder = pool.drop(priority.index)
        n_random = min(n_bucket - n_priority, len(remainder))
        n_overlap = min(overlap_count(n_random), len(remainder))
        overlap = remainder.sample(n=n_overlap, random_state=bucket_seed).copy()
        shared_uids.update(overlap["uid"])
        plans.append(
            {
                "bucket": bucket_name,
                "purposive": priority,
                "overlap": overlap,
                "n_rest": n_random - n_overlap,
                "pool_mask": merged["extraction_class"].eq(extraction_class),
                "seed": bucket_seed,
                "population": len(remainder),
            }
        )

    # Phase 2: coder-specific remainders, excluding all shared rows (from
    # every bucket) plus this coder's own earlier draws.
    coder_uids: set[str] = set()
    sampled: list[tuple[str, str, pd.DataFrame, int | None]] = []
    for plan in plans:
        rest_pool = merged[
            plan["pool_mask"]
            & ~merged["uid"].isin(shared_uids)
            & ~merged["uid"].isin(coder_uids)
        ]
        n_rest = min(plan["n_rest"], len(rest_pool))
        rest = rest_pool.sample(n=n_rest, random_state=plan["seed"] + coder_offset).copy()
        coder_uids.update(rest["uid"])

        overlap = plan["overlap"].copy()
        overlap["_overlap"] = True
        rest["_overlap"] = False
        random_part = pd.concat([overlap, rest]) if not rest.empty else overlap
        if not plan["purposive"].empty:
            sampled.append((plan["bucket"], "purposive", plan["purposive"], None))
        sampled.append((plan["bucket"], "random", random_part, plan["population"]))

    ra_rows = []
    key_rows = []
    for sample_bucket, bucket_kind, frame, population in sampled:
        for _, row in frame.iterrows():
            article_text = row.get("full_text") or ""
            packet_id = f"E-{row['article_id']}-{int(row['extraction_index']):03d}"
            ra_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": row.get("article_id", ""),
                    "date": row.get("date", ""),
                    "publication": row.get("publication", ""),
                    "headline": row.get("headline", ""),
                    "primary_prosecutor": row.get("primary_prosecutor", ""),
                    "extraction_class": row.get("extraction_class", ""),
                    "extraction_text": row.get("extraction_text", ""),
                    "attr_source_type": row.get("attr_source_type", ""),
                    "attr_stance_toward_prosecutor": row.get("attr_stance_toward_prosecutor", ""),
                    "attr_effect": row.get("attr_effect", ""),
                    "attr_causal_strength": row.get("attr_causal_strength", ""),
                    "attr_direction": row.get("attr_direction", ""),
                    "attr_claim_type": row.get("attr_claim_type", ""),
                    "attr_specificity": row.get("attr_specificity", ""),
                    "attr_action_type": row.get("attr_action_type", ""),
                    "attr_domain": row.get("attr_domain", ""),
                    "attr_framing": row.get("attr_framing", ""),
                    "attr_compared_to": row.get("attr_compared_to", ""),
                    "attr_dimension": row.get("attr_dimension", ""),
                    "attr_who_favored": row.get("attr_who_favored", ""),
                    "raw_attributes_json": row.get("raw_attributes_json", ""),
                    "context_excerpt": find_context_excerpt(article_text, row.get("extraction_text", "")),
                    "ra_present_in_text": "",
                    "ra_class_correct": "",
                    "ra_attribute_correct": "",
                    "ra_corrected_class": "",
                    "ra_corrected_attributes_json": "",
                    "ra_ambiguity_type": "",
                    "ra_notes": "",
                }
            )
            key_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": row.get("article_id", ""),
                    "extraction_index": int(row["extraction_index"]),
                    "sample_bucket": sample_bucket,
                    "bucket_kind": bucket_kind,
                    "overlap_set": yes_no(row.get("_overlap", bucket_kind == "purposive")),
                    "bucket_population": population if population is not None else "",
                    "prosecutor_type": row.get("prosecutor_type", ""),
                    "invalid_attributes": row.get("invalid_attributes", ""),
                    "flag_schema_drift": yes_no(row.get("flag_schema_drift")),
                    "flag_reported_speech": yes_no(row.get("flag_reported_speech")),
                    "flag_balanced_article": yes_no(row.get("flag_balanced_article")),
                    "flag_implicit_or_speculative": yes_no(row.get("flag_implicit_or_speculative")),
                    "score_stance": row.get("score_stance"),
                    "composite_bias_score": row.get("composite_bias_score"),
                    "model_stance_bucket": row.get("model_stance_bucket", ""),
                    "dominant_frame": row.get("dominant_frame", ""),
                    "frame_method": row.get("frame_method", ""),
                }
            )

    ra_packet = pd.DataFrame(ra_rows).sort_values("packet_id").reset_index(drop=True)
    key = pd.DataFrame(key_rows).sort_values("packet_id").reset_index(drop=True)
    return ra_packet, key


def build_case_type_packet(
    articles: pd.DataFrame,
    article_extractions: dict[str, list[str]],
    n_total: int,
    seed: int,
    coder_offset: int,
    overlap_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (ra_packet, key) for packet 03."""
    candidate = articles[
        (articles.get("n_claims", 0) > 0)
        | (articles.get("n_causal", 0) > 0)
        | (articles.get("n_policy_actions", 0) > 0)
    ].copy()
    if candidate.empty:
        candidate = articles.copy()

    n_per_bucket = max(n_total // 4, 1)
    progressive = candidate[candidate["prosecutor_type"] == "Progressive"].copy()
    traditional = candidate[candidate["prosecutor_type"] == "Traditional"].copy()

    progressive["priority_score"] = progressive.get("n_causal", 0) + progressive.get("n_policy_actions", 0)
    traditional["priority_score"] = traditional.get("n_causal", 0) + traditional.get("n_policy_actions", 0)

    prog_structural = progressive.sort_values(["priority_score", "n_claims"], ascending=False).head(n_per_bucket)
    trad_structural = traditional.sort_values(["priority_score", "n_claims"], ascending=False).head(n_per_bucket)
    prog_random_pool = progressive[~progressive["article_id"].isin(prog_structural["article_id"])]
    trad_random_pool = traditional[~traditional["article_id"].isin(trad_structural["article_id"])]
    prog_random = split_overlap_sample(
        prog_random_pool, n_per_bucket, seed + 21, coder_offset, overlap_fraction
    )
    trad_random = split_overlap_sample(
        trad_random_pool, n_per_bucket, seed + 22, coder_offset, overlap_fraction
    )

    buckets = [
        ("progressive_structural", "purposive", prog_structural, None),
        ("traditional_structural", "purposive", trad_structural, None),
        ("progressive_random", "random", prog_random, len(prog_random_pool)),
        ("traditional_random", "random", trad_random, len(trad_random_pool)),
    ]

    ra_rows = []
    key_rows = []
    for sample_bucket, bucket_kind, frame, population in buckets:
        for _, row in frame.iterrows():
            article_text = row.get("full_text") or row.get("body") or row.get("clean_text") or ""
            paragraphs = split_paragraphs(article_text)
            packet_id = f"C-{row['article_id']}"
            ra_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": row["article_id"],
                    "date": row.get("date", ""),
                    "publication": row.get("publication", ""),
                    "headline": row.get("headline", ""),
                    "primary_prosecutor": row.get("primary_prosecutor", ""),
                    "lead_excerpt": truncate(" || ".join(paragraphs[:2]), 1800),
                    "focus_excerpt": build_focus_excerpt(
                        article_text,
                        str(row.get("primary_prosecutor", "")),
                        article_extractions.get(str(row["article_id"]), []),
                    ),
                    "ra_case_type_binary": "",
                    "ra_case_type_detailed": "",
                    "ra_primary_offense_or_issue": "",
                    "ra_specific_case_present": "",
                    "ra_notes": "",
                }
            )
            key_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": row["article_id"],
                    "sample_bucket": sample_bucket,
                    "bucket_kind": bucket_kind,
                    "overlap_set": yes_no(row.get("_overlap", bucket_kind == "purposive")),
                    "bucket_population": population if population is not None else "",
                    "prosecutor_type": row.get("prosecutor_type", ""),
                    "score_stance": row.get("score_stance"),
                    "model_stance_bucket": row.get("model_stance_bucket", ""),
                    "dominant_frame": row.get("dominant_frame", ""),
                    "frame_method": row.get("frame_method", ""),
                    "n_claims": int(row.get("n_claims", 0)),
                    "n_causal": int(row.get("n_causal", 0)),
                    "n_policy_actions": int(row.get("n_policy_actions", 0)),
                }
            )

    ra_packet = pd.DataFrame(ra_rows).sort_values("packet_id").reset_index(drop=True)
    key = pd.DataFrame(key_rows).sort_values("packet_id").reset_index(drop=True)
    return ra_packet, key


def build_recall_packet(
    articles: pd.DataFrame,
    flat: pd.DataFrame,
    n_total: int,
    seed: int,
    coder_offset: int,
    overlap_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return (ra_packet, key) for packet 04 (extraction recall).

    Article-level: the RA sees an article excerpt plus every model extraction
    for that article, and counts sources / causal claims present in the
    excerpt that the model missed.
    """
    if "error" in articles.columns:
        pool_all = articles[articles["error"].isna() | articles["error"].astype(str).eq("")].copy()
    else:
        pool_all = articles.copy()

    n_per_type = max(n_total // 2, 1)
    buckets = []
    for offset, ptype in enumerate(["Progressive", "Traditional"], start=1):
        # Stratified by prosecutor_type; the stratum label goes to the key only.
        type_pool = pool_all[pool_all["prosecutor_type"] == ptype]
        sample = split_overlap_sample(
            type_pool, n_per_type, seed + 30 + offset, coder_offset, overlap_fraction
        )
        buckets.append((f"{ptype.lower()}_random", "random", sample, len(type_pool)))

    flat_by_article = dict(tuple(flat.groupby("article_id")))

    ra_rows = []
    key_rows = []
    for sample_bucket, bucket_kind, frame, population in buckets:
        for _, row in frame.iterrows():
            article_id = str(row["article_id"])
            article_text = row.get("full_text") or row.get("body") or row.get("clean_text") or ""
            paragraphs = split_paragraphs(article_text)
            excerpt = truncate(" || ".join(paragraphs[:8]), 6000)
            excerpt_lower = excerpt.lower()

            extractions = flat_by_article.get(article_id)
            lines = []
            n_sources_in_excerpt = 0
            n_causal_in_excerpt = 0
            if extractions is not None:
                extractions = extractions.sort_values("extraction_index")
                for _, ex in extractions.iterrows():
                    lines.append(
                        f"{int(ex['extraction_index'])}. [{ex['extraction_class']}] "
                        f"{truncate(str(ex['extraction_text']), 300)}"
                    )
                    in_excerpt = normalize_text(str(ex["extraction_text"])).lower() in excerpt_lower
                    if in_excerpt and ex["extraction_class"] == "source_attribution":
                        n_sources_in_excerpt += 1
                    if in_excerpt and ex["extraction_class"] == "causal_claim":
                        n_causal_in_excerpt += 1
            model_extractions = "\n".join(lines) if lines else "(no extractions for this article)"

            packet_id = f"R-{article_id}"
            ra_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": article_id,
                    "date": row.get("date", ""),
                    "publication": row.get("publication", ""),
                    "headline": row.get("headline", ""),
                    "primary_prosecutor": row.get("primary_prosecutor", ""),
                    "article_excerpt": excerpt,
                    "model_extractions": model_extractions,
                    "n_extractions_shown": len(lines),
                    "ra_n_missed_sources": "",
                    "ra_n_missed_causal_claims": "",
                    "ra_missed_notes": "",
                }
            )
            key_rows.append(
                {
                    "packet_id": packet_id,
                    "article_id": article_id,
                    "sample_bucket": sample_bucket,
                    "bucket_kind": bucket_kind,
                    "overlap_set": yes_no(row.get("_overlap", False)),
                    "bucket_population": population,
                    "prosecutor_type": row.get("prosecutor_type", ""),
                    "n_model_sources": int(row.get("n_sources", 0)),
                    "n_model_causal": int(row.get("n_causal", 0)),
                    "n_model_sources_in_excerpt": n_sources_in_excerpt,
                    "n_model_causal_in_excerpt": n_causal_in_excerpt,
                    "n_extractions_total": len(lines),
                }
            )

    ra_packet = pd.DataFrame(ra_rows).sort_values("packet_id").reset_index(drop=True)
    key = pd.DataFrame(key_rows).sort_values("packet_id").reset_index(drop=True)
    return ra_packet, key


RA_FORBIDDEN_COLUMNS = {
    "prosecutor_type",
    "sample_bucket",
    "bucket_kind",
    "overlap_set",
    "score_stance",
    "composite_bias_score",
    "model_stance_bucket",
    "dominant_frame",
    "frame_method",
    "invalid_attributes",
    "flag_schema_drift",
    "flag_reported_speech",
    "flag_balanced_article",
    "flag_implicit_or_speculative",
}


def assert_blinded(packet: pd.DataFrame, name: str) -> None:
    leaked = RA_FORBIDDEN_COLUMNS & set(packet.columns)
    if leaked:
        raise RuntimeError(f"Blinding violation in {name}: {sorted(leaked)}")


def main() -> None:
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.coder_id):
        raise SystemExit("--coder-id must be alphanumeric (plus - or _)")

    require_files([
        ATTRIBUTED_PARQUET,
        BIAS_PARQUET,
        FRAMES_PARQUET,
        EXTRACTIONS_JSONL,
        EXTRACTIONS_PARQUET,
    ])
    coder_dir = OUTPUT_DIR / args.coder_id
    coder_dir.mkdir(parents=True, exist_ok=True)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    offset = coder_seed_offset(args.coder_id)
    articles = load_article_table()
    results = load_results()
    flat = flatten_extractions(results)
    flat["article_id"] = flat["article_id"].astype(str)
    article_extractions = collect_extraction_texts(flat)

    bucket_sizes = {
        "schema_drift": args.drift_sample_size,
        "source_review": args.source_sample_size,
        "causal_review": args.causal_sample_size,
        "claim_review": args.claim_sample_size,
        "policy_review": args.policy_sample_size,
        "comparison_review": args.comparison_sample_size,
    }

    packets = {
        "01_article_validation": build_article_validation_packet(
            articles, article_extractions, args.article_sample_size,
            args.seed, offset, args.overlap_fraction,
        ),
        "02_extraction_review": build_extraction_review_packet(
            articles, flat, bucket_sizes, args.seed, offset, args.overlap_fraction,
        ),
        "03_case_type_coding": build_case_type_packet(
            articles, article_extractions, args.case_sample_size,
            args.seed, offset, args.overlap_fraction,
        ),
        "04_extraction_recall": build_recall_packet(
            articles, flat, args.recall_sample_size, args.seed, offset, args.overlap_fraction,
        ),
    }

    for stem, (ra_packet, key) in packets.items():
        assert_blinded(ra_packet, stem)
        if len(ra_packet) != len(key):
            raise RuntimeError(f"Packet/key row mismatch for {stem}")
        ra_path = coder_dir / f"{stem}_sample.csv"
        key_path = KEYS_DIR / f"{stem}_KEY_{args.coder_id}.csv"
        # utf-8-sig writes a BOM so Excel on Windows detects UTF-8 rather than
        # cp1252 (the earlier packets showed garbled ligatures, e.g. "ﬀ", to
        # the RA when opened in Excel).
        ra_packet.to_csv(ra_path, index=False, encoding="utf-8-sig")
        key.insert(1, "coder_id", args.coder_id)
        key.to_csv(key_path, index=False, encoding="utf-8-sig")
        n_overlap = key["overlap_set"].eq("yes").sum()
        print(
            f"Wrote {len(ra_packet):,} rows to {ra_path} "
            f"(overlap/shared rows: {n_overlap:,}); key -> {key_path}"
        )
    print(
        "Reminder: files under generated/keys/ are PI-only. "
        "Never share them with the RA."
    )


if __name__ == "__main__":
    main()
