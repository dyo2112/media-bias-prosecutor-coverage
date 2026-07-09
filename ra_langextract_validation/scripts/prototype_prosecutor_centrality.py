"""
Prototype: prosecutor-centrality gate (RA-suggested pre-extraction filter).

Motivation
----------
During packet-01 coding the RA (Guanwen) observed that ~27 instances were not
really prosecutor-focused: the DA appears only as a factual source, procedural
background, or a passing reference, even though the extraction/attribution is
technically valid. This mirrors the Step-03 attribution-validity gap flagged in
the audit. She suggested a pre-extraction check of whether the prosecutor is the
*substantive target* of the passage, not merely mentioned.

This script prototypes that check as a transparent, dependency-light heuristic
so we can discuss it (with evidence) at the RA meeting before deciding whether
to fold it into the pipeline. It does NOT modify the pipeline.

Centrality signals (each in [0, 1], then weighted):
  1. headline_mention   - prosecutor named in the title (strong centrality cue)
  2. lede_mention       - named in the first LEDE_SENTS sentences
  3. mention_density    - prosecutor mentions per 100 words (saturating)
  4. non_attributive    - fraction of mentions NOT in a "said/according to X"
                          construction (attributive mention = source, not subject)
  5. subject_position   - fraction of mentions at/near sentence start (proxy for
                          grammatical subject/agent without a full parser)

Output
------
- generated/prototype_prosecutor_centrality.csv : per-article scores for the
  packet-01 article set (or the full attributed corpus with --full).
- If --completed <ra_01_completed.csv> is given and a prosecutor-focus flag
  column is found, prints a separation analysis (score distribution + rate
  table across thresholds) against the RA's ground truth.

Usage
-----
  py -3 scripts/prototype_prosecutor_centrality.py
  py -3 scripts/prototype_prosecutor_centrality.py --completed path/to/ra_01.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from config import ATTRIBUTED_PARQUET, PROSECUTORS  # noqa: E402
from utils import split_sentences  # noqa: E402

HERE = Path(__file__).resolve().parent
GENERATED_DIR = HERE.parent / "generated"
PACKET_01 = GENERATED_DIR / "ra1" / "01_article_validation_sample.csv"
KEY_01 = GENERATED_DIR / "keys" / "01_article_validation_KEY_ra1.csv"
OUT_CSV = GENERATED_DIR / "prototype_prosecutor_centrality.csv"

LEDE_SENTS = 3
# Weights are a starting point for the meeting; tune against RA ground truth.
WEIGHTS = {
    "headline_mention": 0.25,
    "lede_mention": 0.15,
    "mention_density": 0.20,
    "non_attributive": 0.25,
    "subject_position": 0.15,
}
# Attribution cues that mark a prosecutor mention as a source rather than subject.
_ATTRIB_BEFORE = re.compile(
    r"(?:according to|per|says?|said|told|stated|noted|added|"
    r"argued|claimed|announced|confirmed)\s*$",
    re.IGNORECASE,
)
_ATTRIB_AFTER = re.compile(
    r"^\s*(?:said|says?|told|stated|noted|added|argued|claimed|announced|"
    r"confirmed|according)",
    re.IGNORECASE,
)


def variant_regex(prosecutor_name: str) -> re.Pattern | None:
    """Whole-word regex matching a prosecutor's name variants (not generic DA)."""
    p = next((p for p in PROSECUTORS if p.name == prosecutor_name), None)
    if p is None:
        return None
    terms = sorted(
        {re.escape(v) for v in p.name_variants} | {re.escape(p.name)},
        key=len,
        reverse=True,
    )
    return re.compile(r"(?<!\w)(?:" + "|".join(terms) + r")(?!\w)", re.IGNORECASE)


def _sat(x: float, scale: float) -> float:
    """Saturating map [0, inf) -> [0, 1): x / (x + scale)."""
    return x / (x + scale) if x > 0 else 0.0


def score_article(title: str, body: str, name_re: re.Pattern) -> dict:
    title = title if isinstance(title, str) else ""
    body = body if isinstance(body, str) else ""

    headline_mention = 1.0 if name_re.search(title) else 0.0

    sentences = split_sentences(body)
    lede = " ".join(sentences[:LEDE_SENTS])
    lede_mention = 1.0 if name_re.search(lede) else 0.0

    n_words = max(len(body.split()), 1)
    matches = list(name_re.finditer(body))
    n_mentions = len(matches)
    mention_density = _sat(100.0 * n_mentions / n_words, scale=1.0)

    if n_mentions == 0:
        non_attributive = 0.0
        subject_position = 0.0
    else:
        n_attrib = 0
        n_subject = 0
        for m in matches:
            before = body[max(0, m.start() - 30):m.start()]
            after = body[m.end():m.end() + 20]
            if _ATTRIB_BEFORE.search(before) or _ATTRIB_AFTER.search(after):
                n_attrib += 1
            # Distance from the start of the containing sentence (proxy for
            # subject position): find the last sentence break before the match.
            seg_start = max(
                body.rfind(".", 0, m.start()),
                body.rfind("!", 0, m.start()),
                body.rfind("?", 0, m.start()),
                body.rfind("\n", 0, m.start()),
            )
            if m.start() - seg_start <= 40:
                n_subject += 1
        non_attributive = 1.0 - (n_attrib / n_mentions)
        subject_position = n_subject / n_mentions

    parts = {
        "headline_mention": headline_mention,
        "lede_mention": lede_mention,
        "mention_density": mention_density,
        "non_attributive": non_attributive,
        "subject_position": subject_position,
    }
    centrality = sum(WEIGHTS[k] * v for k, v in parts.items())
    parts["n_mentions"] = n_mentions
    parts["prosecutor_centrality"] = round(centrality, 4)
    return parts


def build_scores(article_ids: set[str] | None) -> pd.DataFrame:
    df = pd.read_parquet(ATTRIBUTED_PARQUET)
    df = df[df["primary_prosecutor"].notna()].copy()
    df["article_id"] = df["article_id"].astype(str)
    if article_ids is not None:
        df = df[df["article_id"].isin(article_ids)]
    title_col = "title" if "title" in df.columns else "headline"

    re_cache: dict[str, re.Pattern | None] = {}
    rows = []
    for _, row in df.iterrows():
        name = row["primary_prosecutor"]
        if name not in re_cache:
            re_cache[name] = variant_regex(name)
        name_re = re_cache[name]
        if name_re is None:
            continue
        scored = score_article(row.get(title_col, ""), row.get("body", ""), name_re)
        scored["article_id"] = row["article_id"]
        scored["primary_prosecutor"] = name
        rows.append(scored)
    return pd.DataFrame(rows)


def find_focus_flag(completed: pd.DataFrame) -> str | None:
    """Best-effort detection of the RA's 'not prosecutor-focused' column."""
    candidates = [
        c for c in completed.columns
        if re.search(r"(focus|subject|relevan|prosecutor_is|centrality)", c, re.I)
    ]
    return candidates[0] if candidates else None


def run_validation(scores: pd.DataFrame, completed_path: Path) -> list[str]:
    lines: list[str] = ["", "== Validation against RA ground truth ==", ""]
    completed = pd.read_csv(completed_path, encoding="utf-8-sig")
    # Map packet_id -> article_id via the key file (RA sheet is blinded).
    if "article_id" not in completed.columns and KEY_01.exists():
        key = pd.read_csv(KEY_01, encoding="utf-8-sig")[["packet_id", "article_id"]]
        completed = completed.merge(key, on="packet_id", how="left")
    if "article_id" not in completed.columns:
        lines.append("Could not resolve article_id in the completed sheet; "
                     "pass a file that has article_id or packet_id.")
        return lines
    completed["article_id"] = completed["article_id"].astype(str)

    flag_col = find_focus_flag(completed)
    if flag_col is None:
        lines.append(
            "No prosecutor-focus column detected in the completed sheet. "
            f"Columns present: {list(completed.columns)}. "
            "Tell me which column encodes the RA's 27 'not prosecutor-focused' "
            "cases and I'll rerun."
        )
        return lines

    merged = scores.merge(
        completed[["article_id", flag_col]], on="article_id", how="inner"
    )
    lines.append(f"Using RA column '{flag_col}' as focus flag; "
                 f"{len(merged)} articles matched.")
    # Interpret truthy/no/low-relevance strings as "not focused".
    raw = merged[flag_col].astype(str).str.strip().str.lower()
    not_focused = raw.isin({"no", "n", "false", "0", "low", "not_focused",
                            "non_prosecutor", "unclear", "yes"})
    lines.append(f"'Not prosecutor-focused' rows (heuristic parse): "
                 f"{int(not_focused.sum())} of {len(merged)} "
                 f"(confirm the parse maps to her 27).")

    c = merged["prosecutor_centrality"]
    lines.append(f"Centrality — focused: mean={c[~not_focused].mean():.3f}; "
                 f"not-focused: mean={c[not_focused].mean():.3f}")
    lines.append("")
    lines.append("Threshold  kept  dropped  dropped_that_are_not_focused(recall)  "
                 "kept_that_are_focused(precision)")
    for thr in (0.2, 0.3, 0.4, 0.5):
        kept = c >= thr
        dropped = ~kept
        recall = (dropped & not_focused).sum() / max(not_focused.sum(), 1)
        precision = (kept & ~not_focused).sum() / max(kept.sum(), 1)
        lines.append(f"  {thr:.2f}     {int(kept.sum()):4d}  {int(dropped.sum()):5d}  "
                     f"{recall:6.2f}                                 {precision:6.2f}")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description="Prosecutor-centrality gate prototype")
    ap.add_argument("--full", action="store_true",
                    help="Score the full attributed corpus (default: packet-01 set)")
    ap.add_argument("--completed", type=Path, default=None,
                    help="RA's completed packet-01 CSV for validation")
    args = ap.parse_args()

    article_ids = None
    if not args.full and PACKET_01.exists() and KEY_01.exists():
        key = pd.read_csv(KEY_01, encoding="utf-8-sig")
        article_ids = set(key["article_id"].astype(str))
        print(f"Scoring the {len(article_ids)} packet-01 articles "
              f"(use --full for the whole corpus).")
    else:
        print("Scoring the full attributed corpus.")

    scores = build_scores(article_ids)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    scores.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(scores):,} scored articles -> {OUT_CSV}")
    print("\nprosecutor_centrality distribution:")
    print(scores["prosecutor_centrality"].describe().round(3).to_string())

    if args.completed is not None:
        for line in run_validation(scores, args.completed):
            print(line)
    else:
        print("\nNo --completed sheet provided: validation against the RA's "
              "27 flagged cases is pending her packet-01 file.")


if __name__ == "__main__":
    main()
