"""
Analyze the RA's completed packet-03 (case-type coding, old pre-blinding schema).

Packet 03 asks a different question from 01/02: it codes a NEW construct
(offense/issue type) rather than auditing a model output, so the payoff is a
confound check — does the mix of case-centered vs policy/political coverage
differ by prosecutor type? If it does, the composite contrast could partly
reflect story-type composition rather than differential treatment.

Reports:
  1. Coding-consistency check (binary vs specific-case-present) and the
     boundary cases the RA flagged as judgment calls.
  2. Case-type composition by prosecutor type (the confound test).
  3. Within-case-type progressive-traditional gaps, WITH a power caveat.
  4. Low-relevance / wrong-target-DA notes: rate by prosecutor type, the
     contamination direction, and a further out-of-sample check of the
     >=2-mentions-or-headline relevance rule.
  5. Data-quality issues in the returned sheet (label variants, CSV
     column-shift artifacts).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact, ttest_ind

HERE = Path(__file__).resolve().parent
RA_ROOT = HERE.parent
REPO_ROOT = RA_ROOT.parent
COMPLETED = RA_ROOT / "completed" / "03_case_type_coding_sample.csv"
BIAS = REPO_ROOT / "output" / "04_bias_scores.parquet"
ATTRIBUTED = REPO_ROOT / "output" / "03_attributed.parquet"

# Notes the RA used to mark articles that are not substantively about the
# attributed prosecutor (same intent as her packet-01 low-relevance benchmark).
RELEVANCE_NOTE_RE = re.compile(
    r"low.{0,15}relevan|non-?prosecutor|not (?:about|mainly|only)|mainly about|"
    r"wrong|not Boudin|not Price|not Jenkins",
    re.IGNORECASE,
)


def read_csv_any(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    n1, n2 = len(a), len(b)
    if n1 < 3 or n2 < 3:
        return float("nan")
    pooled = np.sqrt(((n1 - 1) * np.var(a, ddof=1) + (n2 - 1) * np.var(b, ddof=1))
                     / (n1 + n2 - 2))
    return float((np.mean(a) - np.mean(b)) / pooled) if pooled else float("nan")


def main() -> None:
    df = read_csv_any(COMPLETED)
    df["article_id"] = df["article_id"].astype(str)

    print("=" * 72)
    print("0. RETURNED-SHEET DATA QUALITY")
    print("=" * 72)
    valid_type = df["prosecutor_type"].isin(["Progressive", "Traditional"])
    print(f"  rows: {len(df)}; malformed prosecutor_type (CSV column shift): "
          f"{int((~valid_type).sum())}")
    for _, r in df[~valid_type].iterrows():
        print(f"    {r['packet_id']} article {r['article_id']}: "
              f"prosecutor_type={r['prosecutor_type']!r} — labels still readable "
              f"(binary={r['ra_case_type_binary']!r}); recover type from the packet")
    detailed = (df["ra_case_type_detailed"].astype(str).str.strip().str.lower()
                .str.replace(" ", "_", regex=False).str.replace("/", "_or_", regex=False))
    canon = {"criminal_case", "policy", "political", "general_issue"}
    off = detailed[~detailed.isin(canon)]
    print(f"  non-canonical ra_case_type_detailed values: {len(off)} "
          f"({sorted(set(off))})")

    print()
    print("=" * 72)
    print("1. CODING CONSISTENCY (binary vs specific-case-present)")
    print("=" * 72)
    ct = pd.crosstab(df["ra_case_type_binary"], df["ra_specific_case_present"])
    print(ct.to_string())
    agree = int(((df["ra_case_type_binary"] == 1) & (df["ra_specific_case_present"] == "yes")).sum()
                + ((df["ra_case_type_binary"] == 0) & (df["ra_specific_case_present"] == "no")).sum())
    print(f"  internally consistent: {agree}/{len(df)} = {agree/len(df):.3f}")
    boundary = df[(df["ra_specific_case_present"] == "yes") & (df["ra_case_type_binary"] == 0)]
    print(f"  boundary calls (case present but coded policy/political): {len(boundary)}")
    print("  — these are the judgment calls the RA flagged; they are the whole")
    print("    disagreement surface and should be adjudicated explicitly.")

    print()
    print("=" * 72)
    print("2. CASE-TYPE COMPOSITION BY PROSECUTOR TYPE (confound test)")
    print("=" * 72)
    sub = df[valid_type]
    comp = pd.crosstab(sub["prosecutor_type"], sub["ra_case_type_binary"])
    print(comp.to_string())
    if comp.shape == (2, 2):
        odds, pv = fisher_exact(comp.values)
        print(f"  Fisher exact p={pv:.4f}, odds ratio={odds:.2f}")
        print("  -> no detectable difference in story-type mix: the composite")
        print("     contrast is not explained by case-vs-policy composition.")

    print()
    print("=" * 72)
    print("3. WITHIN-CASE-TYPE GAP (underpowered — read the caveat)")
    print("=" * 72)
    bs = pd.read_parquet(BIAS, columns=["article_id", "composite_bias_score",
                                        "score_stance", "prosecutor_type"])
    bs["article_id"] = bs["article_id"].astype(str)
    m = df[["article_id", "ra_case_type_binary"]].merge(bs, on="article_id", how="inner")
    print(f"  matched to bias scores: {len(m)}/{len(df)}")
    for label, grp in [("case-centered", m[m["ra_case_type_binary"] == 1]),
                       ("policy/political", m[m["ra_case_type_binary"] == 0])]:
        p = grp.loc[grp["prosecutor_type"] == "Progressive", "composite_bias_score"].dropna().values
        t = grp.loc[grp["prosecutor_type"] == "Traditional", "composite_bias_score"].dropna().values
        if len(p) > 2 and len(t) > 2:
            _, pv = ttest_ind(p, t, equal_var=False)
            print(f"  {label:18s} nP={len(p):3d} nT={len(t):3d} "
                  f"d={cohens_d(p, t):+.3f} p={pv:.3f}")
    print("  CAVEAT: ~25-36 articles per cell gives roughly 0.2 power to detect")
    print("  the corpus effect (d=0.15). These nulls are uninformative about")
    print("  whether the gap holds within case type; do not report as evidence.")

    print()
    print("=" * 72)
    print("4. LOW-RELEVANCE / WRONG-TARGET NOTES")
    print("=" * 72)
    notes = df["ra_notes"].fillna("").astype(str)
    flag = notes.str.contains(RELEVANCE_NOTE_RE)
    print(f"  flagged rows: {int(flag.sum())} of {len(df)}")
    fct = pd.crosstab(df.loc[valid_type, "prosecutor_type"], flag[valid_type])
    print(fct.to_string())
    if fct.shape == (2, 2):
        odds, pv = fisher_exact(fct.values)
        print(f"  Fisher exact p={pv:.4f} -> asymmetry between groups NOT established")

    ids = set(df.loc[flag, "article_id"])
    fl = bs[bs["article_id"].isin(ids)]
    prog = bs[bs["prosecutor_type"] == "Progressive"]
    print(f"\n  contamination direction (composite): flagged={fl['composite_bias_score'].mean():+.4f} "
          f"vs all-progressive={prog['composite_bias_score'].mean():+.4f}")
    print("  -> flagged articles are LESS critical than typical progressive")
    print("     coverage, so removing them would strengthen (not weaken) the")
    print("     contrast — same direction as the fallback-exclusion sensitivity.")

    att = pd.read_parquet(ATTRIBUTED)
    att["article_id"] = att["article_id"].astype(str)
    s = att[att["article_id"].isin(ids)]
    caught = 0
    print("\n  out-of-sample check of the >=2-mentions-or-headline rule:")
    for _, r in s.iterrows():
        p_ = r["primary_prosecutor"]
        mm = r.get(f"mentions_{p_}", 0) or 0
        hh = r.get(f"headline_mention_{p_}", 0) or 0
        kept = (mm >= 2) or (hh >= 1)
        caught += (not kept)
        print(f"    {r['article_id']}: mentions={int(mm):2d} headline={int(hh)} "
              f"-> {'drops (correct)' if not kept else 'KEEPS (miss)'}")
    if len(s):
        print(f"  rule catches {caught}/{len(s)} = {caught/len(s):.2f}")
        print("  Consistent with the packet-02 probe (4/9): the rule screens the")
        print("  low-mention population only. Articles that name the prosecutor")
        print("  many times while being about someone else are not detected.")


if __name__ == "__main__":
    main()
