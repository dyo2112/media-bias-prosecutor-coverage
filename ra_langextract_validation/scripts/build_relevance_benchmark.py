"""
Build the pooled low-relevance / wrong-target benchmark from the RA's packets,
and grade the two candidate relevance rules against it.

Why this exists: the manuscript cites a pooled benchmark of RA-flagged
articles and the resulting recall/precision of the relevance rules. Those
figures were originally computed ad hoc, so they could not be reproduced from
the repository. This script makes the benchmark a deterministic artifact.

Benchmark definition (explicit, so the count is auditable):
  - Packet 01 contributes the RA's own authoritative low-relevance sheet
    (completed/01_low_relevance_benchmark.csv), her second-pass list.
  - Packets 02 and 03 contribute rows whose free-text notes match
    NOTE_PATTERN below, which captures the two failure modes she described:
    the article is not substantively about a prosecutor, or it is about a
    DIFFERENT prosecutor than the one it was attributed to.
  - The universe is every distinct article_id appearing in packets 01-03.
    Packet 04 is excluded: it collects no relevance judgment.

Outputs generated/pooled_relevance_benchmark.csv and prints rule performance.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RA_ROOT = HERE.parent
REPO_ROOT = RA_ROOT.parent
COMPLETED = RA_ROOT / "completed"
OUT = RA_ROOT / "generated" / "pooled_relevance_benchmark.csv"
ATTRIBUTED = REPO_ROOT / "output" / "03_attributed.parquet"

# Two failure modes, kept as one documented pattern so the count is stable.
NOTE_PATTERN = re.compile(
    r"low\s*\w*\s*relevan"           # "low prosecutor relevance", "low relevance"
    r"|non-?prosecutor"               # "non-prosecutor-focused"
    r"|not\s+(?:about|mainly|only|primarily|primarily\s+about)"
    r"|mainly\s+about"                # "mainly about Gascon not Boudin"
    r"|wrong\s+(?:da|prosecutor|target)"
    r"|refers?\s+to\s+(?:gasc|spitzer|chisholm|another)"
    r"|concerns\s+john\s+chisholm",
    re.IGNORECASE,
)

UNTRACKED = re.compile(
    r"(?<!\w)(?:gasc[oó]n|kamala\s+harris|jeff\s+rosen|todd\s+spitzer"
    r"|chisholm|krasner|mosby|kim\s+foxx)(?!\w)",
    re.IGNORECASE,
)


def read_csv_any(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def main() -> None:
    rows, universe = [], set()

    bench01 = COMPLETED / "01_low_relevance_benchmark.csv"
    pkt01 = COMPLETED / "01_article_validation_sample.csv"
    if pkt01.exists():
        universe |= set(read_csv_any(pkt01)["article_id"].astype(str))
    if bench01.exists():
        for a in read_csv_any(bench01)["article_id"].astype(str):
            rows.append({"article_id": a, "source_packet": "01", "basis": "RA authoritative sheet"})

    for stem, pkt in [("02", "02_extraction_review_sample.csv"),
                      ("03", "03_case_type_coding_sample.csv")]:
        p = COMPLETED / pkt
        if not p.exists():
            continue
        d = read_csv_any(p)
        d["article_id"] = d["article_id"].astype(str)
        universe |= set(d["article_id"])
        notes = d["ra_notes"].fillna("").astype(str) if "ra_notes" in d.columns else pd.Series("", index=d.index)
        for aid, nt in zip(d["article_id"], notes):
            if NOTE_PATTERN.search(nt):
                rows.append({"article_id": aid, "source_packet": stem, "basis": nt.strip()[:200]})

    bench = pd.DataFrame(rows).drop_duplicates(subset="article_id", keep="first")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bench.to_csv(OUT, index=False, encoding="utf-8-sig")

    flagged = set(bench["article_id"])
    print(f"pooled benchmark: {len(flagged)} flagged articles "
          f"out of {len(universe)} distinct articles coded in packets 01-03")
    print(bench["source_packet"].value_counts().sort_index().to_string())
    print(f"wrote {OUT}")

    att = pd.read_parquet(ATTRIBUTED)
    att["article_id"] = att["article_id"].astype(str)
    att = att[att["article_id"].isin(universe)].copy()

    def signals(r):
        p = r["primary_prosecutor"]
        prim = float(r.get(f"mentions_{p}", 0) or 0)
        head = float(r.get(f"headline_mention_{p}", 0) or 0)
        others = sum(float(r.get(f"mentions_{q}", 0) or 0)
                     for q in att["primary_prosecutor"].dropna().unique() if q != p)
        text = f"{r.get('full_text') or ''} {r.get('headline') or ''}"
        return prim, head, others, len(UNTRACKED.findall(text))

    sig = att.apply(signals, axis=1, result_type="expand")
    sig.columns = ["prim", "hl", "others", "untracked"]
    sig["article_id"] = att["article_id"].values
    sig["flag"] = sig["article_id"].isin(flagged)

    print()
    print(f"{'rule':46s} {'recall':>7s} {'prec':>7s} {'kept':>6s}")
    for name, keep in [
        ("mentions>=2 or headline", (sig.prim >= 2) | (sig.hl >= 1)),
        ("+ dominance over all other prosecutors",
         ((sig.prim >= 2) | (sig.hl >= 1)) & (sig.prim > (sig.others + sig.untracked))),
    ]:
        dropped = ~keep
        rec = (dropped & sig.flag).sum() / max(int(sig.flag.sum()), 1)
        prec = (keep & ~sig.flag).sum() / max(int(keep.sum()), 1)
        lo, hi = wilson(int((dropped & sig.flag).sum()), int(sig.flag.sum()))
        print(f"{name:46s} {rec:7.3f} {prec:7.3f} {int(keep.sum()):6d}   "
              f"recall 95% CI [{lo:.3f}, {hi:.3f}]")
    n_unt = int((sig.flag & (sig.untracked > 0)).sum())
    print(f"\nflagged articles naming a non-study prosecutor: {n_unt}/{int(sig.flag.sum())}")
    print("NOTE: both rules were developed against these same flags, so these "
          "figures are in-sample; treat as upper bounds.")


if __name__ == "__main__":
    main()
