"""
Analyze the RA's completed packet-01 (old, pre-blinding schema, self-contained).

Produces meeting-ready numbers:
  1. Centrality-gate validation: does prosecutor_centrality separate the RA's
     "not prosecutor-focused" articles (blank ra_primary_issue) from the rest?
  2. Article-stance agreement (RA vs model_stance_bucket): % agreement, Cohen's
     kappa (bootstrap CI), confusion matrix — and the model's supportive over-
     prediction the RA reported.
  3. Dominant-frame agreement (label-normalized), excluding rows the RA left as
     mixed/other/blank.

This reads the OLD-schema completed file (model outputs inline). New blinded
coders go through summarize_ra_labels.py instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RA_ROOT = HERE.parent
COMPLETED = RA_ROOT / "completed" / "01_article_validation_sample.csv"
# RA's authoritative list of not-prosecutor-focused articles (her second pass,
# n=28). When present it supersedes the blank-ra_primary_issue proxy.
LOW_RELEVANCE = RA_ROOT / "completed" / "01_low_relevance_benchmark.csv"
CENTRALITY = RA_ROOT / "generated" / "prototype_prosecutor_centrality.csv"

SEED = 42
STANCE_LABELS = ["critical", "neutral_or_mixed", "supportive"]
FRAME_NORMALIZE = {
    "reform/ideology": "reform",
    "reform": "reform",
    "human interest": "human_interest",
    "human_interest": "human_interest",
    "accountability": "accountability",
    "conflict": "conflict",
    "consequences": "consequences",
}


def read_csv_any(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")


def read_completed() -> pd.DataFrame:
    return read_csv_any(COMPLETED)


def cohens_kappa(a: pd.Series, b: pd.Series, labels: list[str]) -> float:
    """Cohen's kappa for two aligned label series over a fixed label set."""
    n = len(a)
    if n == 0:
        return float("nan")
    idx = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    conf = np.zeros((k, k))
    for x, y in zip(a, b):
        if x in idx and y in idx:
            conf[idx[x], idx[y]] += 1
    total = conf.sum()
    if total == 0:
        return float("nan")
    po = np.trace(conf) / total
    row = conf.sum(axis=1) / total
    col = conf.sum(axis=0) / total
    pe = float((row * col).sum())
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def kappa_ci(a: pd.Series, b: pd.Series, labels: list[str], n_boot: int = 2000):
    a = a.reset_index(drop=True)
    b = b.reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    n = len(a)
    point = cohens_kappa(a, b, labels)
    if n < 5:
        return point, float("nan"), float("nan")
    boots = []
    for _ in range(n_boot):
        s = rng.integers(0, n, n)
        boots.append(cohens_kappa(a.iloc[s], b.iloc[s], labels))
    boots = [x for x in boots if not np.isnan(x)]
    lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan)
    return point, float(lo), float(hi)


def auc_rank(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUC = P(score_pos > score_neg) with 0.5 for ties, via rank statistic."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    ranks = pd.Series(allv).rank().values
    r_pos = ranks[: len(pos)].sum()
    u = r_pos - len(pos) * (len(pos) + 1) / 2
    return u / (len(pos) * len(neg))


def main() -> None:
    df = read_completed()
    df["article_id"] = df["article_id"].astype(str)
    cen = pd.read_csv(CENTRALITY, encoding="utf-8-sig")
    cen["article_id"] = cen["article_id"].astype(str)
    m = df.merge(cen[["article_id", "prosecutor_centrality", "n_mentions"]],
                 on="article_id", how="left")

    # Coverage guard: prototype_prosecutor_centrality.py defaults to scoring
    # only the CURRENT blinded packet, which covers about 60% of the RA's
    # (older) packet-01 articles. Silently analyzing that subset biases the
    # AUC upward. Require full coverage and say so loudly if it is missing.
    n_missing = int(m["prosecutor_centrality"].isna().sum())
    if n_missing:
        print(f"!! {n_missing} of {len(m)} coded articles have no centrality "
              f"score ({CENTRALITY.name} holds {len(cen):,} rows).")
        print("!! Rerun: py -3 scripts/prototype_prosecutor_centrality.py --full")
        print("!! Numbers below are computed on a biased subset — do not quote.\n")

    print("=" * 68)
    print("1. CENTRALITY-GATE VALIDATION vs RA's not-prosecutor-focused flag")
    print("=" * 68)
    if LOW_RELEVANCE.exists():
        truth_ids = set(read_csv_any(LOW_RELEVANCE)["article_id"].astype(str))
        not_focused = m["article_id"].isin(truth_ids)
        proxy = m["ra_primary_issue"].isna()
        print(f"RA benchmark sheet (authoritative): {int(not_focused.sum())} of {len(m)} "
              f"not prosecutor-focused")
        print(f"  (blank-primary-issue proxy would give {int(proxy.sum())}; "
              f"overlap with benchmark: {int((proxy & not_focused).sum())})")
    else:
        not_focused = m["ra_primary_issue"].isna()
        print(f"RA 'not focused' (blank ra_primary_issue proxy): "
              f"{int(not_focused.sum())} of {len(m)}")
    c_foc = m.loc[~not_focused, "prosecutor_centrality"].dropna()
    c_not = m.loc[not_focused, "prosecutor_centrality"].dropna()
    print(f"  centrality — focused:     mean={c_foc.mean():.3f}  median={c_foc.median():.3f}")
    print(f"  centrality — not-focused: mean={c_not.mean():.3f}  median={c_not.median():.3f}")
    auc = auc_rank(c_foc.values, c_not.values)
    print(f"  AUC (separating focused from not-focused): {auc:.3f}")
    zero = m["prosecutor_centrality"] == 0
    print(f"  zero-centrality articles: {int(zero.sum())}; "
          f"of those, RA-not-focused: {int((zero & not_focused).sum())}")
    print()
    print("  thr   dropped  recall(not-foc caught)  precision(kept truly focused)  kept")
    for thr in (0.05, 0.10, 0.20, 0.30, 0.40):
        kept = m["prosecutor_centrality"] >= thr
        dropped = ~kept
        recall = (dropped & not_focused).sum() / max(int(not_focused.sum()), 1)
        precision = (kept & ~not_focused).sum() / max(int(kept.sum()), 1)
        print(f"  {thr:.2f}   {int(dropped.sum()):5d}    {recall:6.2f}                  "
              f"{precision:6.2f}                        {int(kept.sum()):4d}")

    print()
    print("=" * 68)
    print("2. ARTICLE-STANCE AGREEMENT (RA vs model_stance_bucket)")
    print("=" * 68)
    st = m.dropna(subset=["model_stance_bucket"]).copy()
    st = st[st["ra_article_stance"].isin(STANCE_LABELS)]
    print(f"n compared (model stance present, RA labeled): {len(st)} "
          f"(excluded {len(m) - len(st)}: {int(m['model_stance_bucket'].isna().sum())} "
          f"model-NaN + RA blank/other)")
    agree = (st["ra_article_stance"] == st["model_stance_bucket"]).mean()
    kap, lo, hi = kappa_ci(st["ra_article_stance"], st["model_stance_bucket"], STANCE_LABELS)
    print(f"  raw agreement: {agree:.3f}")
    print(f"  Cohen's kappa: {kap:.3f}  (95% CI {lo:.3f}, {hi:.3f})")
    print("  confusion (rows=RA, cols=model):")
    conf = pd.crosstab(st["ra_article_stance"], st["model_stance_bucket"])
    print(conf.to_string().replace("\n", "\n    "))
    n_over = int(((st["model_stance_bucket"] == "supportive") &
                  (st["ra_article_stance"] == "neutral_or_mixed")).sum())
    print(f"  model=supportive & RA=neutral_or_mixed: {n_over}  "
          f"(RA reported ~13 — the model's supportive over-prediction)")

    # Continuous score is fairer to the method than the ±0.15 bucket, which uses
    # thresholds invented by the validation harness. Does the raw score_stance
    # separate the RA's critical vs supportive articles?
    if "score_stance" in m.columns:
        cont = m[m["ra_article_stance"].isin(STANCE_LABELS)].dropna(subset=["score_stance"])
        by = cont.groupby("ra_article_stance")["score_stance"].mean()
        print("  mean continuous score_stance by RA label:")
        for lab in STANCE_LABELS:
            if lab in by:
                print(f"    RA {lab:16s}: {by[lab]:+.3f}")
        crit = cont.loc[cont["ra_article_stance"] == "critical", "score_stance"].values
        supp = cont.loc[cont["ra_article_stance"] == "supportive", "score_stance"].values
        print(f"  AUC(continuous score separates RA supportive>critical): "
              f"{auc_rank(supp, crit):.3f}")

    print()
    print("=" * 68)
    print("3. DOMINANT-FRAME AGREEMENT (label-normalized)")
    print("=" * 68)
    fr = m.copy()
    fr["ra_frame_norm"] = fr["ra_dominant_frame"].str.strip().str.lower().map(FRAME_NORMALIZE)
    fr["model_frame_norm"] = fr["dominant_frame"].str.strip().str.lower().map(FRAME_NORMALIZE)
    excl_mixed = fr["ra_dominant_frame"].notna() & fr["ra_frame_norm"].isna()
    fr2 = fr.dropna(subset=["ra_frame_norm", "model_frame_norm"])
    frame_labels = sorted(set(fr2["ra_frame_norm"]) | set(fr2["model_frame_norm"]))
    print(f"n compared: {len(fr2)} (excluded {int(fr['ra_dominant_frame'].isna().sum())} "
          f"RA-blank + {int(excl_mixed.sum())} RA mixed/other + model-blank)")
    if len(fr2):
        agree_f = (fr2["ra_frame_norm"] == fr2["model_frame_norm"]).mean()
        kap_f, lo_f, hi_f = kappa_ci(fr2["ra_frame_norm"], fr2["model_frame_norm"], frame_labels)
        print(f"  raw agreement: {agree_f:.3f}")
        print(f"  Cohen's kappa: {kap_f:.3f}  (95% CI {lo_f:.3f}, {hi_f:.3f})")

    print()
    print("=" * 68)
    print("4. RA DISCOURSE FLAGS (share yes, among labeled)")
    print("=" * 68)
    for col in ["ra_quoted_criticism", "ra_balanced_reporting", "ra_implicit_causal_claim"]:
        s = m[col].dropna()
        if len(s):
            print(f"  {col}: {(s == 'yes').mean():.2f} yes  (n={len(s)})")


if __name__ == "__main__":
    main()
