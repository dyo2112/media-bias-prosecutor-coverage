"""
Analyze the RA's completed packet-02 (extraction review, old pre-blinding schema).

Produces:
  1. Extraction precision by class and bucket (present-in-text, class-correct,
     attribute-correct) with Wilson 95% CIs.
  2. Grounding check: rows the RA marked not-present are re-verified against
     the FULL article text (the packet's context_excerpt had a known
     construction bug), separating true fabrications from excerpt artifacts.
  3. Attribute-error taxonomy from her corrections/notes: wrong-prosecutor
     causal attribution, causal over-attribution (direction downgrades),
     source-role misclassification, stance over-"supportive".
  4. Direction-downgrade analysis by prosecutor type — bears directly on the
     manuscript's harm-attribution ratio (Appendix A).
  5. Out-of-sample check of the >=2-mentions-or-headline relevance rule on
     articles she flagged low-relevance in this packet.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RA_ROOT = HERE.parent
REPO_ROOT = RA_ROOT.parent
COMPLETED = RA_ROOT / "completed" / "02_extraction_review_sample.csv"
ATTRIBUTED = REPO_ROOT / "output" / "03_attributed.parquet"
OLD_ATTRIBUTED = REPO_ROOT / "output" / "archive_03_asymmetric" / "03_attributed.parquet"


def read_csv_any(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")


def norm_label(v) -> str | None:
    if pd.isna(v):
        return None
    s = str(v).strip().lower()
    fixes = {"tyes": "yes", "not sure": "unclear", "unsure": "unclear"}
    return fixes.get(s, s)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def rate_line(label: str, k: int, n: int) -> str:
    lo, hi = wilson_ci(k, n)
    return f"  {label:34s} {k:3d}/{n:3d} = {k/n if n else float('nan'):.3f}  [{lo:.3f}, {hi:.3f}]"


def norm_text(s: str) -> str:
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_corrected(raw) -> dict:
    """Tolerant parse of the RA's corrected-attributes JSON (may lack braces)."""
    if pd.isna(raw):
        return {}
    s = str(raw).strip()
    if not s:
        return {}
    if not s.startswith("{"):
        s = "{" + s + "}"
    try:
        return {str(k).strip().lower(): str(v).strip().lower()
                for k, v in json.loads(s).items()}
    except (json.JSONDecodeError, AttributeError):
        # last resort: regex key:value pairs
        pairs = re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', s)
        return {k.strip().lower(): v.strip().lower() for k, v in pairs}


def main() -> None:
    df = read_csv_any(COMPLETED)
    df["article_id"] = df["article_id"].astype(str)
    for c in ("ra_present_in_text", "ra_class_correct", "ra_attribute_correct"):
        df[c] = df[c].map(norm_label)

    print("=" * 72)
    print("1. EXTRACTION PRECISION (Wilson 95% CIs)")
    print("=" * 72)
    for scope_name, sub in [("ALL 160", df)] + [
        (f"class={c}", df[df["extraction_class"] == c])
        for c in df["extraction_class"].unique()
    ] + [
        (f"bucket={b}", df[df["sample_bucket"] == b])
        for b in df["sample_bucket"].unique()
    ]:
        pres = sub["ra_present_in_text"].dropna()
        cls = sub["ra_class_correct"].dropna()
        attr = sub[sub["ra_attribute_correct"].isin(["yes", "no"])]["ra_attribute_correct"]
        print(f"{scope_name}:")
        print(rate_line("present_in_excerpt", int((pres == "yes").sum()), len(pres)))
        print(rate_line("class_correct (of judged)", int((cls == "yes").sum()), len(cls)))
        print(rate_line("attribute_correct (of judged)", int((attr == "yes").sum()), len(attr)))
    print("NOTE: schema_drift bucket was sampled for suspicion; source/causal")
    print("buckets are half purposive — pooled rates are not corpus-representative.")

    print()
    print("=" * 72)
    print("2. GROUNDING RE-CHECK OF 'NOT PRESENT' ROWS vs FULL ARTICLE TEXT")
    print("=" * 72)
    not_present = df[df["ra_present_in_text"] == "no"]
    art_path = ATTRIBUTED if ATTRIBUTED.exists() else OLD_ATTRIBUTED
    art = pd.read_parquet(art_path, columns=["article_id", "body", "full_text"])
    art["article_id"] = art["article_id"].astype(str)
    body_by_id = art.set_index("article_id")
    n_found_full, n_truly_absent, n_no_article = 0, 0, 0
    for _, r in not_present.iterrows():
        aid = r["article_id"]
        if aid not in body_by_id.index:
            n_no_article += 1
            continue
        row = body_by_id.loc[aid]
        hay = norm_text(str(row.get("full_text") or "") + " " + str(row.get("body") or ""))
        needle = norm_text(str(r["extraction_text"]))
        if needle and needle in hay:
            n_found_full += 1
        else:
            n_truly_absent += 1
    print(f"RA marked not-present: {len(not_present)}")
    print(f"  found verbatim in FULL article text (excerpt artifact): {n_found_full}")
    print(f"  not found in full text either (possible fabrication/paraphrase): {n_truly_absent}")
    print(f"  article no longer in corpus (attribution change): {n_no_article}")

    print()
    print("=" * 72)
    print("3. ATTRIBUTE-ERROR TAXONOMY (notes + corrections)")
    print("=" * 72)
    notes = df["ra_notes"].fillna("").astype(str)
    wrong_prosecutor = notes.str.contains(
        r"not Boudin|not Price|not Jenkins|rather than (?:Chesa|Boudin|Price)|"
        r"refers to (?:Gascon|Gasc|Spitzer|Chisholm)|concerns John",
        case=False, regex=True)
    over_attrib = notes.str.contains(
        r"not explicitly (?:attribute|state|link)|no explicit (?:prosecutor|evidence)|"
        r"assigned to the administration|police not prosecutor|rather than explicitly to|"
        r"not the prosecutor who|responsibility is not clearly",
        case=False, regex=True)
    stance_over = notes.str.contains(
        r"not supportive|stance[: ]*(?:critical|neutral)|stance not correct",
        case=False, regex=True)
    low_rel = notes.str.contains(r"low.{0,15}relevan|non-?prosecutor-?focused", case=False, regex=True)
    amb = df["ra_ambiguity_type"].fillna("").astype(str).str.contains("over_attribution")
    print(f"  wrong-prosecutor attribution (Gascon/Spitzer/Chisholm etc.): {int(wrong_prosecutor.sum())}")
    print(f"  causal over-attribution to prosecutor (notes + ambiguity flag): {int((over_attrib | amb).sum())}")
    print(f"  stance corrections (model too supportive/wrong stance): {int(stance_over.sum())}")
    print(f"  low-relevance article notes: {int(low_rel.sum())}")

    # Field-level corrections
    corr = df[df["ra_corrected_attributes_json"].notna()
              & (df["ra_corrected_attributes_json"].astype(str).str.strip() != "")].copy()
    print(f"\n  rows with corrected attributes: {len(corr)}")
    field_changes: dict[str, int] = {}
    direction_downgrades = []
    source_type_confusions = []
    stance_changes = []
    for _, r in corr.iterrows():
        fixed = parse_corrected(r["ra_corrected_attributes_json"])
        for field, ra_val in fixed.items():
            model_val = r.get(f"attr_{field}")
            if pd.isna(model_val):
                continue
            model_val = str(model_val).strip().lower()
            if model_val and ra_val and model_val != ra_val:
                field_changes[field] = field_changes.get(field, 0) + 1
                if field == "direction":
                    direction_downgrades.append((r["prosecutor_type"], model_val, ra_val))
                if field == "source_type":
                    source_type_confusions.append((model_val, ra_val))
                if field == "stance_toward_prosecutor":
                    stance_changes.append((model_val, ra_val))
    print("  field-level changes (model != RA):")
    for f, n in sorted(field_changes.items(), key=lambda kv: -kv[1]):
        print(f"    {f:28s} {n}")

    print()
    print("=" * 72)
    print("4. CAUSAL DIRECTION DOWNGRADES BY PROSECUTOR TYPE")
    print("   (bears on the Appendix A harm-attribution ratio)")
    print("=" * 72)
    causal = df[df["extraction_class"] == "causal_claim"].copy()
    harm = causal[causal["attr_direction"].astype(str).str.lower() == "prosecutor_caused_harm"]
    print(f"  causal rows judged: {len(causal)}; model said prosecutor_caused_harm: {len(harm)}")
    dd = pd.DataFrame(direction_downgrades, columns=["prosecutor_type", "model", "ra"])
    if len(dd):
        harm_dd = dd[dd["model"] == "prosecutor_caused_harm"]
        print(f"  direction changed by RA (all): {len(dd)}; harm->something else: {len(harm_dd)}")
        print("  harm downgrades by prosecutor type / new value:")
        print(dd.groupby(["prosecutor_type", "model", "ra"]).size().to_string())
        # downgrade rate among model-harm rows per type
        for ptype in ("Progressive", "Traditional"):
            n_harm = int((harm["prosecutor_type"] == ptype).sum())
            n_down = int((harm_dd["prosecutor_type"] == ptype).sum())
            if n_harm:
                lo, hi = wilson_ci(n_down, n_harm)
                print(f"  {ptype}: {n_down}/{n_harm} harm labels downgraded "
                      f"= {n_down/n_harm:.2f} [{lo:.2f}, {hi:.2f}]")
    if source_type_confusions:
        print("\n  source_type confusions (model -> RA):")
        for m, ra in source_type_confusions:
            print(f"    {m} -> {ra}")
    if stance_changes:
        print("\n  stance_toward_prosecutor changes (model -> RA):")
        vc = pd.Series([f"{m} -> {ra}" for m, ra in stance_changes]).value_counts()
        print(vc.to_string())

    print()
    print("=" * 72)
    print("5. OUT-OF-SAMPLE RELEVANCE-RULE CHECK (articles flagged low-relevance)")
    print("=" * 72)
    flagged_articles = sorted(set(df.loc[low_rel, "article_id"]))
    print(f"  articles flagged low-relevance in packet-02 notes: {len(flagged_articles)}")
    if flagged_articles:
        art2 = pd.read_parquet(art_path)
        art2["article_id"] = art2["article_id"].astype(str)
        sub = art2[art2["article_id"].isin(flagged_articles)]
        for _, r in sub.iterrows():
            p = r["primary_prosecutor"]
            m = r.get(f"mentions_{p}", 0)
            h = r.get(f"headline_mention_{p}", 0)
            kept = (m >= 2) or (h >= 1)
            print(f"    {r['article_id']}: mentions={int(m)} headline={int(h)} "
                  f"-> rule {'KEEPS (miss)' if kept else 'drops (correct)'}")


if __name__ == "__main__":
    main()
