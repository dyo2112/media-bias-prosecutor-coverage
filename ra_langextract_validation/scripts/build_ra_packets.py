"""
Build local review packets for RA validation of the Step 08 langextract output.

The generated CSVs include local article excerpts and therefore stay out of Git.
"""

from __future__ import annotations

import argparse
import json
import random
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
DEFAULT_ARTICLE_SAMPLE = 100
DEFAULT_EXTRACTION_SAMPLE = 160
DEFAULT_CASE_SAMPLE = 120
DEFAULT_SEED = 42

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
    parser.add_argument("--extraction-sample-size", type=int, default=DEFAULT_EXTRACTION_SAMPLE)
    parser.add_argument("--case-sample-size", type=int, default=DEFAULT_CASE_SAMPLE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


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


def model_stance_bucket(score: float) -> str:
    if pd.isna(score):
        return ""
    if score <= -0.15:
        return "critical"
    if score >= 0.15:
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
    frames = pd.read_parquet(FRAMES_PARQUET)[
        ["article_id", "dominant_frame"]
    ].copy()
    summary = pd.read_parquet(EXTRACTIONS_PARQUET).copy()

    for frame in (attributed, bias, frames, summary):
        frame["article_id"] = frame["article_id"].astype(str)

    articles = attributed.merge(bias, on="article_id", how="left")
    articles = articles.merge(frames, on="article_id", how="left")
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


def build_article_validation_packet(
    articles: pd.DataFrame,
    article_extractions: dict[str, list[str]],
    n_total: int,
    seed: int,
) -> pd.DataFrame:
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
    prog_random = sample_rows(prog_random_pool, n_per_bucket, seed + 1)
    trad_random = sample_rows(trad_random_pool, n_per_bucket, seed + 2)

    buckets = [
        ("progressive_high_contestation", prog_priority),
        ("traditional_high_self_quote", trad_priority),
        ("progressive_random", prog_random),
        ("traditional_random", trad_random),
    ]

    rows = []
    packet_num = 1
    for sample_bucket, frame in buckets:
        for _, row in frame.iterrows():
            article_text = row.get("full_text") or row.get("body") or row.get("clean_text") or ""
            paragraphs = split_paragraphs(article_text)
            extraction_texts = article_extractions.get(str(row["article_id"]), [])
            rows.append(
                {
                    "packet_id": f"A{packet_num:03d}",
                    "sample_bucket": sample_bucket,
                    "article_id": row["article_id"],
                    "date": row["date"],
                    "publication": row.get("publication", ""),
                    "headline": row.get("headline", ""),
                    "primary_prosecutor": row.get("primary_prosecutor", ""),
                    "prosecutor_type": row.get("prosecutor_type", ""),
                    "score_stance": row.get("score_stance"),
                    "model_stance_bucket": row.get("model_stance_bucket", ""),
                    "dominant_frame": row.get("dominant_frame", ""),
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
                    "lead_excerpt": truncate(" || ".join(paragraphs[:2]), 1800),
                    "focus_excerpt": build_focus_excerpt(
                        article_text,
                        str(row.get("primary_prosecutor", "")),
                        extraction_texts,
                    ),
                    "ra_article_stance": "",
                    "ra_dominant_frame": "",
                    "ra_primary_issue": "",
                    "ra_quoted_criticism": "",
                    "ra_balanced_reporting": "",
                    "ra_implicit_causal_claim": "",
                    "ra_notes": "",
                }
            )
            packet_num += 1

    packet = pd.DataFrame(rows)
    return packet.sort_values(["sample_bucket", "packet_id"]).reset_index(drop=True)


def build_extraction_review_packet(
    articles: pd.DataFrame,
    flat: pd.DataFrame,
    n_total: int,
    seed: int,
) -> pd.DataFrame:
    article_cols = [
        "article_id",
        "date",
        "publication",
        "headline",
        "primary_prosecutor",
        "prosecutor_type",
        "full_text",
        "model_stance_bucket",
        "dominant_frame",
        "stance_critical",
        "stance_supportive",
    ]
    merged = flat.merge(articles[article_cols], on="article_id", how="left")
    merged["invalid_attributes"] = merged.apply(invalid_attributes, axis=1)
    merged["flag_schema_drift"] = merged["invalid_attributes"].ne("")
    merged["flag_balanced_article"] = (
        merged["stance_critical"].fillna(0).gt(0) & merged["stance_supportive"].fillna(0).gt(0)
    )
    merged["flag_reported_speech"] = (
        merged["extraction_text"].fillna("").str.contains(REPORTING_PATTERNS)
        | merged["headline"].fillna("").str.contains(REPORTING_PATTERNS)
    )
    merged["flag_implicit_or_speculative"] = merged.get("attr_causal_strength", "").isin(
        ["implied", "speculative"]
    )

    n_invalid = max(n_total // 4, 1)
    n_source = max((n_total - n_invalid) // 2, 1)
    n_causal = max(n_total - n_invalid - n_source, 1)

    invalid_pool = merged[merged["flag_schema_drift"]].copy()
    invalid_sample = sample_rows(invalid_pool, min(n_invalid, len(invalid_pool)), seed + 10)

    source_pool = merged[merged["extraction_class"] == "source_attribution"].copy()
    source_pool["priority_score"] = (
        source_pool["flag_reported_speech"].astype(int)
        + source_pool["flag_balanced_article"].astype(int)
        + source_pool["flag_schema_drift"].astype(int)
    )
    source_pool = source_pool.sort_values(["priority_score", "article_id"], ascending=[False, True])
    source_priority = source_pool.head(min(n_source // 2, len(source_pool)))
    source_remainder = source_pool[~source_pool.index.isin(source_priority.index)]
    source_random = sample_rows(source_remainder, max(n_source - len(source_priority), 0), seed + 11)
    source_sample = pd.concat([source_priority, source_random], ignore_index=False)

    causal_pool = merged[merged["extraction_class"] == "causal_claim"].copy()
    causal_pool["priority_score"] = (
        causal_pool["flag_implicit_or_speculative"].astype(int)
        + causal_pool["flag_balanced_article"].astype(int)
        + causal_pool["flag_schema_drift"].astype(int)
    )
    causal_pool = causal_pool.sort_values(["priority_score", "article_id"], ascending=[False, True])
    causal_priority = causal_pool.head(min(n_causal // 2, len(causal_pool)))
    causal_remainder = causal_pool[~causal_pool.index.isin(causal_priority.index)]
    causal_random = sample_rows(causal_remainder, max(n_causal - len(causal_priority), 0), seed + 12)
    causal_sample = pd.concat([causal_priority, causal_random], ignore_index=False)

    groups = [
        ("schema_drift", invalid_sample),
        ("source_review", source_sample),
        ("causal_review", causal_sample),
    ]

    rows = []
    packet_num = 1
    for sample_bucket, frame in groups:
        for _, row in frame.drop_duplicates(
            subset=["article_id", "extraction_index", "extraction_class", "extraction_text"]
        ).iterrows():
            article_text = row.get("full_text") or ""
            rows.append(
                {
                    "packet_id": f"E{packet_num:03d}",
                    "sample_bucket": sample_bucket,
                    "article_id": row.get("article_id", ""),
                    "date": row.get("date", ""),
                    "publication": row.get("publication", ""),
                    "headline": row.get("headline", ""),
                    "primary_prosecutor": row.get("primary_prosecutor", ""),
                    "prosecutor_type": row.get("prosecutor_type", ""),
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
                    "invalid_attributes": row.get("invalid_attributes", ""),
                    "flag_schema_drift": "yes" if row.get("flag_schema_drift") else "no",
                    "flag_reported_speech": "yes" if row.get("flag_reported_speech") else "no",
                    "flag_balanced_article": "yes" if row.get("flag_balanced_article") else "no",
                    "flag_implicit_or_speculative": (
                        "yes" if row.get("flag_implicit_or_speculative") else "no"
                    ),
                    "model_stance_bucket": row.get("model_stance_bucket", ""),
                    "dominant_frame": row.get("dominant_frame", ""),
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
            packet_num += 1

    packet = pd.DataFrame(rows)
    return packet.sort_values(["sample_bucket", "packet_id"]).reset_index(drop=True)


def build_case_type_packet(
    articles: pd.DataFrame,
    article_extractions: dict[str, list[str]],
    n_total: int,
    seed: int,
) -> pd.DataFrame:
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
    prog_random = sample_rows(
        progressive[~progressive["article_id"].isin(prog_structural["article_id"])],
        n_per_bucket,
        seed + 21,
    )
    trad_random = sample_rows(
        traditional[~traditional["article_id"].isin(trad_structural["article_id"])],
        n_per_bucket,
        seed + 22,
    )

    groups = [
        ("progressive_structural", prog_structural),
        ("traditional_structural", trad_structural),
        ("progressive_random", prog_random),
        ("traditional_random", trad_random),
    ]

    rows = []
    packet_num = 1
    for sample_bucket, frame in groups:
        for _, row in frame.iterrows():
            article_text = row.get("full_text") or row.get("body") or row.get("clean_text") or ""
            paragraphs = split_paragraphs(article_text)
            rows.append(
                {
                    "packet_id": f"C{packet_num:03d}",
                    "sample_bucket": sample_bucket,
                    "article_id": row["article_id"],
                    "date": row.get("date", ""),
                    "publication": row.get("publication", ""),
                    "headline": row.get("headline", ""),
                    "primary_prosecutor": row.get("primary_prosecutor", ""),
                    "prosecutor_type": row.get("prosecutor_type", ""),
                    "model_stance_bucket": row.get("model_stance_bucket", ""),
                    "dominant_frame": row.get("dominant_frame", ""),
                    "n_claims": int(row.get("n_claims", 0)),
                    "n_causal": int(row.get("n_causal", 0)),
                    "n_policy_actions": int(row.get("n_policy_actions", 0)),
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
            packet_num += 1

    packet = pd.DataFrame(rows)
    return packet.sort_values(["sample_bucket", "packet_id"]).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    require_files([
        ATTRIBUTED_PARQUET,
        BIAS_PARQUET,
        FRAMES_PARQUET,
        EXTRACTIONS_JSONL,
        EXTRACTIONS_PARQUET,
    ])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)
    articles = load_article_table()
    results = load_results()
    flat = flatten_extractions(results)
    flat["article_id"] = flat["article_id"].astype(str)
    article_extractions = collect_extraction_texts(flat)

    article_packet = build_article_validation_packet(
        articles=articles,
        article_extractions=article_extractions,
        n_total=args.article_sample_size,
        seed=args.seed,
    )
    extraction_packet = build_extraction_review_packet(
        articles=articles,
        flat=flat,
        n_total=args.extraction_sample_size,
        seed=args.seed,
    )
    case_packet = build_case_type_packet(
        articles=articles,
        article_extractions=article_extractions,
        n_total=args.case_sample_size,
        seed=args.seed,
    )

    article_path = OUTPUT_DIR / "01_article_validation_sample.csv"
    extraction_path = OUTPUT_DIR / "02_extraction_review_sample.csv"
    case_path = OUTPUT_DIR / "03_case_type_coding_sample.csv"

    article_packet.to_csv(article_path, index=False)
    extraction_packet.to_csv(extraction_path, index=False)
    case_packet.to_csv(case_path, index=False)

    print(f"Wrote {len(article_packet):,} article-review rows to {article_path}")
    print(f"Wrote {len(extraction_packet):,} extraction-review rows to {extraction_path}")
    print(f"Wrote {len(case_packet):,} case-coding rows to {case_path}")


if __name__ == "__main__":
    main()
