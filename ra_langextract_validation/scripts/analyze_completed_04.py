"""
Analyze the RA's completed packet-04 (extraction recall / missed content).

This is the only packet that measures FALSE NEGATIVES: content present in the
article that the machine failed to extract. The source-ecology counts in
Appendix A depend on recall being adequate and, critically, on recall error
being SYMMETRIC across prosecutor types.

Reports:
  1. Missed-item totals and per-article distribution.
  2. Excerpt/extraction mismatch (RA-flagged): how many model extractions fall
     outside the excerpt shown, and whether they appear in the FULL article
     text - distinguishing "excerpt too short" (packet bug) from ungrounded
     extraction (model bug).
  3. False-negative rates per class, with a naive and a corrected denominator
     (only extractions verifiably inside the excerpt count as true positives).
  4. Symmetry check: do missed sources/causal claims differ by prosecutor
     type? This is the load-bearing question for Appendix A.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

HERE = Path(__file__).resolve().parent
RA_ROOT = HERE.parent
REPO_ROOT = RA_ROOT.parent
COMPLETED = RA_ROOT / "completed" / "04_extraction_recall_sample.csv"
KEY = RA_ROOT / "generated" / "keys" / "04_extraction_recall_KEY_ra1.csv"
ATTRIBUTED = REPO_ROOT / "output" / "03_attributed.parquet"

EXTRACTION_LINE = re.compile(r"^\s*\d+\.\s*\[([a-z_]+)\]\s*(.+?)\s*$")


def read_csv_any(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")


def norm(s: str) -> str:
    s = re.sub(r"[‘’]", "'", str(s))
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def contained(needle: str, hay: str) -> bool:
    """Verbatim containment, then a lenient fallback on the first 8 words."""
    n, h = norm(needle), norm(hay)
    if not n:
        return False
    if n in h:
        return True
    words = n.split()
    if len(words) >= 5:
        return " ".join(words[:8]) in h
    return False


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def main() -> None:
    d = read_csv_any(COMPLETED)
    d["article_id"] = d["article_id"].astype(str)

    print("=" * 72)
    print("1. MISSED-ITEM TOTALS")
    print("=" * 72)
    ms = int(d["ra_n_missed_sources"].sum())
    mc = int(d["ra_n_missed_causal_claims"].sum())
    print(f"  articles coded: {len(d)}")
    print(f"  missed sources: {ms} total; "
          f"{int((d['ra_n_missed_sources'] > 0).sum())}/{len(d)} articles affected")
    print(f"  missed causal claims: {mc} total; "
          f"{int((d['ra_n_missed_causal_claims'] > 0).sum())}/{len(d)} articles affected")
    print(f"  -> {ms / (ms + mc):.0%} of missed items are source attributions "
          f"(confirms the RA's first observation)")

    print()
    print("=" * 72)
    print("2. EXCERPT / EXTRACTION MISMATCH")
    print("=" * 72)
    art = pd.read_parquet(ATTRIBUTED, columns=["article_id", "body", "full_text"])
    art["article_id"] = art["article_id"].astype(str)
    art = art.set_index("article_id")

    rows = []
    for _, r in d.iterrows():
        exc = str(r["article_excerpt"])
        full = ""
        if r["article_id"] in art.index:
            a = art.loc[r["article_id"]]
            full = f"{a.get('full_text') or ''} {a.get('body') or ''}"
        for line in str(r["model_extractions"]).split("\n"):
            m = EXTRACTION_LINE.match(line)
            if not m:
                continue
            cls, txt = m.group(1), m.group(2)
            rows.append({
                "packet_id": r["packet_id"],
                "article_id": r["article_id"],
                "cls": cls,
                "text": txt,
                "in_excerpt": contained(txt, exc),
                "in_full": contained(txt, full) if full else None,
            })
    E = pd.DataFrame(rows)
    print(f"  model extractions parsed: {len(E)} across {E['article_id'].nunique()} articles")
    out = E[~E["in_excerpt"]]
    print(f"  NOT in the excerpt shown: {len(out)} ({len(out) / len(E):.1%})")
    if len(out):
        rec = int((out["in_full"] == True).sum())
        gone = int((out["in_full"] == False).sum())
        print(f"    of those, present in the FULL article: {rec} ({rec / len(out):.0%})"
              f"  -> excerpt too short (packet bug, not model error)")
        print(f"    absent from the full article too: {gone}"
              f"  -> possible paraphrase/fabrication")
    aff = int(E.groupby("article_id")["in_excerpt"].apply(lambda s: (~s).any()).sum())
    print(f"  articles with >=1 out-of-excerpt extraction: {aff}/{E['article_id'].nunique()}"
          f"  (RA flagged {int(d['ra_notes'].notna().sum())} in her notes)")
    print("  by class:")
    for c, g in E.groupby("cls"):
        print(f"    {c:24s} {int((~g['in_excerpt']).sum()):3d}/{len(g):3d} outside excerpt")

    print()
    print("=" * 72)
    print("3. FALSE-NEGATIVE RATES (recall)")
    print("=" * 72)
    print("  FN rate = missed / (missed + true positives visible in excerpt)")
    for cls, misscol, label in [
        ("source_attribution", "ra_n_missed_sources", "sources"),
        ("causal_claim", "ra_n_missed_causal_claims", "causal claims"),
    ]:
        missed = int(d[misscol].sum())
        tp_all = int((E["cls"] == cls).sum())
        tp_exc = int(((E["cls"] == cls) & E["in_excerpt"]).sum())
        fn_naive = missed / (missed + tp_all) if (missed + tp_all) else float("nan")
        fn_corr = missed / (missed + tp_exc) if (missed + tp_exc) else float("nan")
        lo, hi = wilson(missed, missed + tp_exc)
        print(f"  {label}:")
        print(f"    missed={missed}  extracted(all)={tp_all}  extracted(in excerpt)={tp_exc}")
        print(f"    FN rate: naive={fn_naive:.3f}   corrected={fn_corr:.3f}  [{lo:.3f}, {hi:.3f}]")
    print("  The corrected rate is the defensible one: extractions the RA could")
    print("  not see cannot count as recall successes against her judgment.")

    print()
    print("=" * 72)
    print("4. SYMMETRY BY PROSECUTOR TYPE  (load-bearing for Appendix A)")
    print("=" * 72)
    if KEY.exists():
        k = read_csv_any(KEY)[["packet_id", "prosecutor_type"]]
        d2 = d.merge(k, on="packet_id", how="left")
    else:
        att = pd.read_parquet(ATTRIBUTED, columns=["article_id", "prosecutor_type"])
        att["article_id"] = att["article_id"].astype(str)
        d2 = d.merge(att, on="article_id", how="left")
    print(d2["prosecutor_type"].value_counts(dropna=False).to_string())
    for col, label in [("ra_n_missed_sources", "missed sources"),
                       ("ra_n_missed_causal_claims", "missed causal claims")]:
        p = d2.loc[d2["prosecutor_type"] == "Progressive", col].dropna().values
        t = d2.loc[d2["prosecutor_type"] == "Traditional", col].dropna().values
        if len(p) > 2 and len(t) > 2:
            _, pv = ttest_ind(p, t, equal_var=False)
            print(f"  {label}: Progressive mean={p.mean():.2f} (n={len(p)}) vs "
                  f"Traditional mean={t.mean():.2f} (n={len(t)}), Welch p={pv:.3f}")
    print("  If these are symmetric, differential recall error does not")
    print("  manufacture the Appendix A source-ecology differential.")


if __name__ == "__main__":
    main()
