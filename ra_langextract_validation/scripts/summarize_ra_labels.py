"""
Summarize completed RA coding sheets for the Step 08 validation workflow.

Blinding design:
- RA-facing packets contain no model outputs, no prosecutor_type, and no
  sampling-bucket labels. This script joins the PI-side key files
  (generated/keys/<packet>_KEY_<coder>.csv) back onto the completed sheets
  on packet_id at summary time.
- Everything written to summary/ and adjudication/ is PI-only.

Reporting design:
- The HEADLINE agreement figures use only the random sampling buckets
  (bucket_kind == "random"), which are corpus-representative. Purposive
  (top-k priority) buckets are reported separately.
- Percent agreement is always shown next to Cohen's kappa; kappa CIs come
  from a seeded nonparametric bootstrap.
- Frame agreement: the model's dominant_frame is always one of the 5 frames,
  so RA labels of mixed/other are excluded from the exact-match rate (their
  share is reported separately). The forced-choice column
  ra_dominant_frame_forced is compared head-to-head.

Multi-coder design:
- Completed files may be namespaced by coder id, either
  completed/<coder_id>/<packet>_completed.csv or
  completed/<packet>_completed_<coder_id>.csv. A bare
  completed/<packet>_completed.csv is treated as coder "ra1".
- When 2+ coders completed the same packet, inter-coder Cohen's kappa is
  computed on the shared rows (seeded overlap subset + purposive rows) and
  disagreements are written to adjudication/ with empty adjudicated_*
  columns for the PI to fill.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from build_ra_packets import (  # noqa: E402
    STANCE_BUCKET_THRESHOLD,
    STANCE_SENSITIVITY_THRESHOLDS,
    model_stance_bucket,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT / "ra_langextract_validation"
COMPLETED_DIR = BASE_DIR / "completed"
SUMMARY_DIR = BASE_DIR / "summary"
KEYS_DIR = BASE_DIR / "generated" / "keys"
ADJUDICATION_DIR = BASE_DIR / "adjudication"

DEFAULT_CODER = "ra1"
BOOTSTRAP_SEED = 42
N_BOOTSTRAP = 1000

PACKET_STEMS = [
    "01_article_validation",
    "02_extraction_review",
    "03_case_type_coding",
    "04_extraction_recall",
]

MODEL_FRAMES = {"accountability", "conflict", "consequences", "human_interest", "reform"}
YES_NO_UNCLEAR = {"yes", "no", "unclear"}

# Allowed values per RA column, used for normalization/validation (P2 item).
ALLOWED_RA_VALUES: dict[str, set[str]] = {
    "ra_article_stance": {"critical", "neutral", "mixed", "supportive"},
    "ra_dominant_frame": MODEL_FRAMES | {"mixed", "other"},
    "ra_dominant_frame_forced": set(MODEL_FRAMES),
    "ra_prosecutor_is_subject": set(YES_NO_UNCLEAR),
    "ra_quoted_criticism": set(YES_NO_UNCLEAR),
    "ra_balanced_reporting": set(YES_NO_UNCLEAR),
    "ra_implicit_causal_claim": set(YES_NO_UNCLEAR),
    "ra_present_in_text": {"yes", "no", "partial", "unclear"},
    "ra_class_correct": set(YES_NO_UNCLEAR),
    "ra_attribute_correct": {"yes", "no", "partly", "unclear"},
    "ra_case_type_binary": {"violent", "non_violent", "mixed", "no_specific_offense", "unclear"},
    "ra_specific_case_present": set(YES_NO_UNCLEAR),
}

# Fields used for inter-coder reliability, per packet stem.
RELIABILITY_FIELDS: dict[str, list[str]] = {
    "01_article_validation": [
        "ra_article_stance",
        "ra_dominant_frame",
        "ra_dominant_frame_forced",
        "ra_prosecutor_is_subject",
        "ra_quoted_criticism",
        "ra_balanced_reporting",
        "ra_implicit_causal_claim",
    ],
    "02_extraction_review": [
        "ra_present_in_text",
        "ra_class_correct",
        "ra_attribute_correct",
    ],
    "03_case_type_coding": [
        "ra_case_type_binary",
        "ra_case_type_detailed",
        "ra_specific_case_present",
    ],
    "04_extraction_recall": [
        "ra_n_missed_sources",
        "ra_n_missed_causal_claims",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completed-dir", type=Path, default=COMPLETED_DIR)
    parser.add_argument("--summary-dir", type=Path, default=SUMMARY_DIR)
    parser.add_argument("--keys-dir", type=Path, default=KEYS_DIR)
    parser.add_argument("--adjudication-dir", type=Path, default=ADJUDICATION_DIR)
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Label normalization / validation
# ---------------------------------------------------------------------------


def normalize_label(value) -> str:
    """Lowercase, strip, and collapse internal whitespace/hyphens to _."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().lower()
    if text in {"nan", "none"}:
        return ""
    if re.fullmatch(r"\d+\.0", text):
        # CSV round-trips can turn integer counts into e.g. "2.0".
        text = text[:-2]
    return re.sub(r"[\s\-]+", "_", text)


def normalize_ra_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Normalize all categorical ra_* columns in place and return
    (df, invalid_report_lines) describing values outside the allowed sets.
    """
    invalid_lines: list[str] = []
    for col, allowed in ALLOWED_RA_VALUES.items():
        if col not in df.columns:
            continue
        df[col] = df[col].map(normalize_label)
        bad = df.loc[df[col].ne("") & ~df[col].isin(allowed), col]
        if not bad.empty:
            counts = bad.value_counts()
            listed = ", ".join(f"`{value}` (n={count})" for value, count in counts.items())
            invalid_lines.append(f"  - `{col}`: invalid values {listed} (excluded from agreement)")
            df.loc[~df[col].isin(allowed), col] = ""
    return df, invalid_lines


# ---------------------------------------------------------------------------
# Agreement statistics (dependency-free)
# ---------------------------------------------------------------------------


def percent_agreement(a: list[str], b: list[str]) -> float:
    if not a:
        return float("nan")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def cohens_kappa(a: list[str], b: list[str]) -> float:
    """Hand-rolled Cohen's kappa for two label sequences of equal length."""
    n = len(a)
    if n == 0:
        return float("nan")
    po = percent_agreement(a, b)
    labels = set(a) | set(b)
    pe = 0.0
    for label in labels:
        pe += (a.count(label) / n) * (b.count(label) / n)
    if math.isclose(pe, 1.0):
        return float("nan")
    return (po - pe) / (1.0 - pe)


def bootstrap_kappa_ci(
    a: list[str],
    b: list[str],
    n_boot: int,
    seed: int,
) -> tuple[float, float]:
    """Seeded nonparametric bootstrap 95% CI for Cohen's kappa."""
    n = len(a)
    if n < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        kappa = cohens_kappa([a[i] for i in idx], [b[i] for i in idx])
        if not math.isnan(kappa):
            stats.append(kappa)
    if not stats:
        return (float("nan"), float("nan"))
    stats.sort()
    lo = stats[max(0, int(round(0.025 * (len(stats) - 1))))]
    hi = stats[min(len(stats) - 1, int(round(0.975 * (len(stats) - 1))))]
    return (lo, hi)


def bootstrap_proportion_ci(
    values: list[int],
    n_boot: int,
    seed: int,
) -> tuple[float, float]:
    """Seeded bootstrap 95% CI for a proportion over 0/1 values."""
    n = len(values)
    if n < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(sum(sample) / n)
    stats.sort()
    lo = stats[max(0, int(round(0.025 * (len(stats) - 1))))]
    hi = stats[min(len(stats) - 1, int(round(0.975 * (len(stats) - 1))))]
    return (lo, hi)


def fmt(value: float, pct: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.1%}" if pct else f"{value:.3f}"


def agreement_line(
    label: str,
    human: list[str],
    model: list[str],
    args: argparse.Namespace,
) -> str:
    n = len(human)
    if n == 0:
        return f"- {label}: no comparable rows"
    agree = percent_agreement(human, model)
    kappa = cohens_kappa(human, model)
    lo, hi = bootstrap_kappa_ci(human, model, args.n_bootstrap, args.bootstrap_seed)
    return (
        f"- {label}: agreement {fmt(agree, pct=True)}, "
        f"kappa {fmt(kappa)} (95% CI {fmt(lo)} to {fmt(hi)}), n={n}"
    )


# ---------------------------------------------------------------------------
# File discovery and key joins
# ---------------------------------------------------------------------------


def find_completed_files(completed_dir: Path) -> dict[str, dict[str, Path]]:
    """Return {packet_stem: {coder_id: path}} for all completed sheets found."""
    found: dict[str, dict[str, Path]] = {stem: {} for stem in PACKET_STEMS}
    if not completed_dir.exists():
        return found
    for stem in PACKET_STEMS:
        # completed/<stem>_completed.csv  -> default coder
        bare = completed_dir / f"{stem}_completed.csv"
        if bare.exists():
            found[stem][DEFAULT_CODER] = bare
        # completed/<stem>_completed_<coder>.csv
        for path in completed_dir.glob(f"{stem}_completed_*.csv"):
            coder = path.stem.replace(f"{stem}_completed_", "")
            if coder:
                found[stem][coder] = path
        # completed/<coder>/<stem>_completed.csv
        for path in completed_dir.glob(f"*/{stem}_completed.csv"):
            found[stem][path.parent.name] = path
    return found


def read_csv_robust(path: Path) -> pd.DataFrame:
    """Read a CSV that may come back from Excel in any of several encodings.

    RA-returned sheets are saved from Excel on Windows and arrive variously as
    UTF-8 with BOM, plain UTF-8, or cp1252. utf-8-sig transparently strips a
    BOM if present and reads plain UTF-8 otherwise; cp1252 is the last resort.
    """
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Final attempt: replace undecodable bytes rather than fail the run.
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")


def load_key(keys_dir: Path, stem: str, coder_id: str) -> pd.DataFrame | None:
    """
    Load the PI-side key for (stem, coder). Falls back to the union of all
    coders' keys for the stem (packet-level facts are identical across
    coders for shared rows).
    """
    exact = keys_dir / f"{stem}_KEY_{coder_id}.csv"
    if exact.exists():
        return read_csv_robust(exact)
    others = sorted(keys_dir.glob(f"{stem}_KEY_*.csv"))
    if not others:
        return None
    combined = pd.concat([read_csv_robust(path) for path in others], ignore_index=True)
    return combined.drop_duplicates(subset="packet_id", keep="first")


def join_key(df: pd.DataFrame, key: pd.DataFrame | None) -> pd.DataFrame:
    if key is None:
        out = df.copy()
        for col in ("sample_bucket", "bucket_kind", "overlap_set", "prosecutor_type"):
            if col not in out.columns:
                out[col] = ""
        return out
    key_cols = key.drop(
        columns=[c for c in ("coder_id", "article_id", "extraction_index") if c in key.columns]
    )
    df = df.drop(columns=[c for c in key_cols.columns if c != "packet_id" and c in df.columns])
    return df.merge(key_cols, on="packet_id", how="left")


def random_subset(df: pd.DataFrame) -> pd.DataFrame:
    if "bucket_kind" not in df.columns:
        return df.iloc[0:0]
    return df[df["bucket_kind"].fillna("").eq("random")]


def purposive_subset(df: pd.DataFrame) -> pd.DataFrame:
    if "bucket_kind" not in df.columns:
        return df.iloc[0:0]
    return df[df["bucket_kind"].fillna("").eq("purposive")]


def paired_labels(df: pd.DataFrame, human_col: str, model_col: str) -> tuple[list[str], list[str]]:
    valid = df[df[human_col].fillna("").ne("") & df[model_col].fillna("").ne("")]
    return list(valid[human_col]), list(valid[model_col])


def collapse_stance(labels: list[str]) -> list[str]:
    return [
        "neutral_or_mixed" if label in {"neutral", "mixed"} else label
        for label in labels
    ]


# ---------------------------------------------------------------------------
# Packet 01: article validation
# ---------------------------------------------------------------------------


def summarize_article_packet(
    df: pd.DataFrame,
    coder_id: str,
    outdir: Path,
    args: argparse.Namespace,
) -> list[str]:
    lines = [f"## Packet 01: Article Validation (coder `{coder_id}`)", ""]
    lines.append(f"- Rows: {len(df):,}")
    coded = df["ra_article_stance"].fillna("").ne("").sum()
    lines.append(f"- Rows with a stance label: {coded:,}")

    df, invalid_lines = normalize_ra_columns(df)
    if invalid_lines:
        lines.append("- Invalid label values found:")
        lines.extend(invalid_lines)

    if "model_stance_bucket" not in df.columns:
        lines.append("- Key file missing: no model comparisons possible. Rebuild packets first.")
        return lines + [""]

    # --- Stance vs model bucket (headline = random buckets) ---
    lines.append("")
    lines.append("### Stance vs model (neutral/mixed collapsed to neutral_or_mixed)")
    for subset_name, subset in [
        ("HEADLINE random buckets", random_subset(df)),
        ("purposive buckets", purposive_subset(df)),
        ("all rows", df),
    ]:
        human, model = paired_labels(subset, "ra_article_stance", "model_stance_bucket")
        lines.append(agreement_line(subset_name, collapse_stance(human), model, args))

    human_all, model_all = paired_labels(df, "ra_article_stance", "model_stance_bucket")
    if human_all:
        confusion = pd.crosstab(
            pd.Series(collapse_stance(human_all), name="ra_stance"),
            pd.Series(model_all, name="model_stance_bucket"),
        )
        confusion.to_csv(outdir / f"01_stance_confusion_{coder_id}.csv")

    # --- Threshold sensitivity (validation-harness bucket definition) ---
    if "score_stance" in df.columns:
        lines.append("")
        lines.append("### Stance-threshold sensitivity (random buckets only)")
        lines.append(
            f"Buckets are a validation-harness construct (default +/-{STANCE_BUCKET_THRESHOLD}); "
            "the pipeline itself reports a continuous score."
        )
        lines.append("")
        lines.append("| threshold | agreement | kappa | n |")
        lines.append("|---|---|---|---|")
        sens_rows = []
        rand = random_subset(df)
        for threshold in STANCE_SENSITIVITY_THRESHOLDS:
            sub = rand[
                rand["ra_article_stance"].fillna("").ne("")
                & rand["score_stance"].notna()
            ]
            human = collapse_stance(list(sub["ra_article_stance"]))
            model = [model_stance_bucket(score, threshold) for score in sub["score_stance"]]
            pairs = [(h, m) for h, m in zip(human, model) if h and m]
            human = [h for h, _ in pairs]
            model = [m for _, m in pairs]
            agree = percent_agreement(human, model)
            kappa = cohens_kappa(human, model)
            lines.append(
                f"| +/-{threshold:.2f} | {fmt(agree, pct=True)} | {fmt(kappa)} | {len(human)} |"
            )
            sens_rows.append(
                {"threshold": threshold, "agreement": agree, "kappa": kappa, "n": len(human)}
            )
        pd.DataFrame(sens_rows).to_csv(
            outdir / f"01_stance_threshold_sensitivity_{coder_id}.csv", index=False
        )

    # --- Frame agreement ---
    lines.append("")
    lines.append("### Dominant frame vs model")
    frame_coded = df[df["ra_dominant_frame"].fillna("").ne("")]
    n_frame = len(frame_coded)
    if n_frame:
        mixed_other = frame_coded["ra_dominant_frame"].isin(["mixed", "other"]).sum()
        lines.append(
            f"- RA chose mixed/other on {mixed_other:,}/{n_frame:,} coded rows "
            f"({mixed_other / n_frame:.1%}); excluded from exact match below."
        )
    exact = df[
        df["ra_dominant_frame"].isin(sorted(MODEL_FRAMES))
        & df["dominant_frame"].fillna("").ne("")
    ]
    for subset_name, subset in [
        ("HEADLINE random buckets, exact match (mixed/other excluded)", random_subset(exact)),
        ("purposive buckets, exact match (mixed/other excluded)", purposive_subset(exact)),
    ]:
        human, model = paired_labels(subset, "ra_dominant_frame", "dominant_frame")
        lines.append(agreement_line(subset_name, human, model, args))

    if "ra_dominant_frame_forced" in df.columns:
        for subset_name, subset in [
            ("HEADLINE random buckets, forced choice", random_subset(df)),
            ("purposive buckets, forced choice", purposive_subset(df)),
        ]:
            human, model = paired_labels(subset, "ra_dominant_frame_forced", "dominant_frame")
            lines.append(agreement_line(subset_name, human, model, args))
        human_f, model_f = paired_labels(df, "ra_dominant_frame_forced", "dominant_frame")
        if human_f:
            confusion = pd.crosstab(
                pd.Series(human_f, name="ra_frame_forced"),
                pd.Series(model_f, name="model_dominant_frame"),
            )
            confusion.to_csv(outdir / f"01_frame_confusion_{coder_id}.csv")

    # --- Discourse-condition flags (unclear excluded with count) ---
    lines.append("")
    lines.append("### Discourse-condition flags")
    for col in [
        "ra_prosecutor_is_subject",
        "ra_quoted_criticism",
        "ra_balanced_reporting",
        "ra_implicit_causal_claim",
    ]:
        if col not in df.columns:
            continue
        values = df[col].fillna("")
        coded_vals = values[values.ne("")]
        if coded_vals.empty:
            continue
        n_unclear = coded_vals.eq("unclear").sum()
        decisive = coded_vals[coded_vals.ne("unclear")]
        share_yes = decisive.eq("yes").mean() if not decisive.empty else float("nan")
        lines.append(
            f"- `{col}`: yes {fmt(share_yes, pct=True)} of {len(decisive):,} decisive rows "
            f"(unclear excluded: {n_unclear:,})"
        )

    # Per-bucket agreement table (PI-side CSV).
    if "sample_bucket" in df.columns:
        bucket_rows = []
        for bucket, group in df.groupby(df["sample_bucket"].fillna("")):
            if not bucket:
                continue
            human, model = paired_labels(group, "ra_article_stance", "model_stance_bucket")
            human = collapse_stance(human)
            bucket_rows.append(
                {
                    "sample_bucket": bucket,
                    "n": len(human),
                    "stance_agreement": percent_agreement(human, model),
                    "stance_kappa": cohens_kappa(human, model),
                }
            )
        if bucket_rows:
            pd.DataFrame(bucket_rows).to_csv(
                outdir / f"01_stance_agreement_by_bucket_{coder_id}.csv", index=False
            )
            lines.append("")
            lines.append(
                f"- Per-bucket stance agreement written to "
                f"`01_stance_agreement_by_bucket_{coder_id}.csv`"
            )
    return lines + [""]


# ---------------------------------------------------------------------------
# Packet 02: extraction review
# ---------------------------------------------------------------------------


def summarize_extraction_packet(
    df: pd.DataFrame,
    coder_id: str,
    outdir: Path,
    args: argparse.Namespace,
) -> list[str]:
    lines = [f"## Packet 02: Extraction Review (coder `{coder_id}`)", ""]
    lines.append(f"- Rows: {len(df):,}")

    df, invalid_lines = normalize_ra_columns(df)
    if invalid_lines:
        lines.append("- Invalid label values found:")
        lines.extend(invalid_lines)

    correct_specs = [
        ("ra_present_in_text", {"yes"}, "extraction present in text"),
        ("ra_class_correct", {"yes"}, "extraction class correct"),
        ("ra_attribute_correct", {"yes"}, "attributes fully correct"),
    ]
    for subset_name, subset in [
        ("HEADLINE random buckets", random_subset(df)),
        ("purposive buckets", purposive_subset(df)),
    ]:
        lines.append("")
        lines.append(f"### {subset_name}")
        for col, positive, label in correct_specs:
            if col not in subset.columns:
                continue
            values = subset[col].fillna("")
            coded_vals = values[values.ne("")]
            if coded_vals.empty:
                lines.append(f"- {label} (`{col}`): no coded rows")
                continue
            n_unclear = coded_vals.eq("unclear").sum()
            decisive = coded_vals[coded_vals.ne("unclear")]
            if decisive.empty:
                lines.append(f"- {label} (`{col}`): all {n_unclear:,} coded rows unclear")
                continue
            hits = [1 if value in positive else 0 for value in decisive]
            rate = sum(hits) / len(hits)
            lo, hi = bootstrap_proportion_ci(hits, args.n_bootstrap, args.bootstrap_seed)
            lines.append(
                f"- {label} (`{col}`): {fmt(rate, pct=True)} "
                f"(95% CI {fmt(lo, pct=True)} to {fmt(hi, pct=True)}), "
                f"n={len(hits):,}, unclear excluded: {n_unclear:,}"
            )

    # Per-class and per-bucket crosstabs (PI-side CSVs).
    for col in ("ra_present_in_text", "ra_class_correct", "ra_attribute_correct"):
        if col not in df.columns:
            continue
        sub = df[df[col].fillna("").ne("")]
        if sub.empty:
            continue
        if "sample_bucket" in sub.columns:
            pd.crosstab(sub["sample_bucket"], sub[col]).to_csv(
                outdir / f"02_{col}_by_bucket_{coder_id}.csv"
            )
        if "extraction_class" in sub.columns:
            pd.crosstab(sub["extraction_class"], sub[col]).to_csv(
                outdir / f"02_{col}_by_class_{coder_id}.csv"
            )

    if "ra_ambiguity_type" in df.columns:
        ambiguity = df["ra_ambiguity_type"].fillna("")
        ambiguity = ambiguity[ambiguity.ne("")]
        if not ambiguity.empty:
            lines.append("")
            lines.append("### Top ambiguity types")
            for label, count in ambiguity.value_counts().head(10).items():
                lines.append(f"- `{label}`: {count:,}")
    return lines + [""]


# ---------------------------------------------------------------------------
# Packet 03: case-type coding
# ---------------------------------------------------------------------------


def summarize_case_packet(
    df: pd.DataFrame,
    coder_id: str,
    outdir: Path,
    args: argparse.Namespace,
) -> list[str]:
    lines = [f"## Packet 03: Case-Type Coding (coder `{coder_id}`)", ""]
    lines.append(f"- Rows: {len(df):,}")

    df, invalid_lines = normalize_ra_columns(df)
    if invalid_lines:
        lines.append("- Invalid label values found:")
        lines.extend(invalid_lines)

    coded = df[df["ra_case_type_binary"].fillna("").ne("")]
    lines.append(f"- Rows with binary case-type coding: {len(coded):,}")
    if coded.empty:
        return lines + [""]

    n_unclear = coded["ra_case_type_binary"].eq("unclear").sum()
    decisive = coded[coded["ra_case_type_binary"].ne("unclear")]
    lines.append(f"- Unclear (excluded from shares): {n_unclear:,}")
    for subset_name, subset in [
        ("HEADLINE random buckets", random_subset(decisive)),
        ("purposive buckets", purposive_subset(decisive)),
    ]:
        if subset.empty:
            lines.append(f"- {subset_name}: no decisive coded rows")
            continue
        shares = subset["ra_case_type_binary"].value_counts(normalize=True)
        rendered = ", ".join(f"`{label}` {share:.1%}" for label, share in shares.items())
        lines.append(f"- {subset_name} (n={len(subset):,}): {rendered}")

    if "prosecutor_type" in decisive.columns and decisive["prosecutor_type"].fillna("").ne("").any():
        pd.crosstab(decisive["prosecutor_type"], decisive["ra_case_type_binary"]).to_csv(
            outdir / f"03_case_type_by_prosecutor_type_{coder_id}.csv"
        )
        rand = random_subset(decisive)
        if not rand.empty:
            pd.crosstab(rand["prosecutor_type"], rand["ra_case_type_binary"]).to_csv(
                outdir / f"03_case_type_by_prosecutor_type_random_{coder_id}.csv"
            )
        lines.append(
            f"- Case-type-by-group crosstabs written to "
            f"`03_case_type_by_prosecutor_type_{coder_id}.csv` (PI-side)"
        )
    return lines + [""]


# ---------------------------------------------------------------------------
# Packet 04: extraction recall
# ---------------------------------------------------------------------------


def summarize_recall_packet(
    df: pd.DataFrame,
    coder_id: str,
    outdir: Path,
    args: argparse.Namespace,
) -> list[str]:
    lines = [f"## Packet 04: Extraction Recall (coder `{coder_id}`)", ""]
    lines.append(f"- Rows: {len(df):,}")

    for col in ("ra_n_missed_sources", "ra_n_missed_causal_claims"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "ra_n_missed_sources" in df.columns:
        coded = df[df["ra_n_missed_sources"].notna()]
    else:
        coded = df.iloc[0:0]
    lines.append(f"- Articles with recall coding: {len(coded):,}")
    if coded.empty:
        return lines + [""]

    specs = [
        ("source_attribution", "ra_n_missed_sources", "n_model_sources_in_excerpt"),
        ("causal_claim", "ra_n_missed_causal_claims", "n_model_causal_in_excerpt"),
    ]
    for subset_name, subset in [
        ("HEADLINE random buckets", random_subset(coded)),
        ("all coded rows", coded),
    ]:
        if subset.empty:
            continue
        lines.append("")
        lines.append(f"### {subset_name} (n={len(subset):,})")
        for class_name, missed_col, found_col in specs:
            if missed_col not in subset.columns:
                continue
            missed = subset[missed_col].fillna(0).sum()
            found = (
                subset[found_col].fillna(0).sum() if found_col in subset.columns else float("nan")
            )
            denom = missed + found
            fn_rate = missed / denom if denom and not math.isnan(denom) else float("nan")
            lines.append(
                f"- `{class_name}`: missed {int(missed):,}, model found in excerpt "
                f"{int(found) if not math.isnan(found) else 'n/a'}, "
                f"false-negative rate {fmt(fn_rate, pct=True)}"
            )
            lines.append(
                f"  - mean missed per article: {subset[missed_col].fillna(0).mean():.2f}"
            )
    return lines + [""]


# ---------------------------------------------------------------------------
# Inter-coder reliability and adjudication
# ---------------------------------------------------------------------------


def intercoder_section(
    stem: str,
    coder_frames: dict[str, pd.DataFrame],
    adjudication_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    if len(coder_frames) < 2:
        return []
    lines = [f"## Inter-Coder Reliability: {stem}", ""]
    fields = RELIABILITY_FIELDS.get(stem, [])
    disagreement_rows: list[dict] = []

    for coder_a, coder_b in combinations(sorted(coder_frames), 2):
        df_a = coder_frames[coder_a]
        df_b = coder_frames[coder_b]
        merged = df_a.merge(df_b, on="packet_id", suffixes=("_a", "_b"))
        if merged.empty:
            lines.append(f"- `{coder_a}` vs `{coder_b}`: no shared packet_ids")
            continue
        lines.append(f"### `{coder_a}` vs `{coder_b}` (shared rows: {len(merged):,})")
        for field in fields:
            col_a, col_b = f"{field}_a", f"{field}_b"
            if col_a not in merged.columns or col_b not in merged.columns:
                continue
            pair = merged[
                merged[col_a].astype(str).map(normalize_label).ne("")
                & merged[col_b].astype(str).map(normalize_label).ne("")
            ]
            if pair.empty:
                continue
            labels_a = [normalize_label(value) for value in pair[col_a]]
            labels_b = [normalize_label(value) for value in pair[col_b]]
            lines.append(agreement_line(f"`{field}`", labels_a, labels_b, args))
            for packet_id, val_a, val_b in zip(pair["packet_id"], labels_a, labels_b):
                if val_a != val_b:
                    disagreement_rows.append(
                        {
                            "packet_id": packet_id,
                            "field": field,
                            f"value_{coder_a}": val_a,
                            f"value_{coder_b}": val_b,
                            "adjudicated_value": "",
                            "adjudicated_by": "",
                            "adjudicated_notes": "",
                        }
                    )
        lines.append("")

    if disagreement_rows:
        adjudication_dir.mkdir(parents=True, exist_ok=True)
        out_path = adjudication_dir / f"{stem}_disagreements.csv"
        pd.DataFrame(disagreement_rows).to_csv(out_path, index=False)
        lines.append(
            f"- {len(disagreement_rows):,} disagreements written to `{out_path.name}` "
            "(fill the adjudicated_* columns)"
        )
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SUMMARIZERS = {
    "01_article_validation": summarize_article_packet,
    "02_extraction_review": summarize_extraction_packet,
    "03_case_type_coding": summarize_case_packet,
    "04_extraction_recall": summarize_recall_packet,
}


def main() -> None:
    args = parse_args()
    args.summary_dir.mkdir(parents=True, exist_ok=True)

    completed = find_completed_files(args.completed_dir)
    report_lines = ["# RA Validation Summary", ""]
    report_lines.append(
        "PI-side report. Joins completed RA sheets with generated/keys/. "
        "Headline figures use the random (corpus-representative) buckets only."
    )
    report_lines.append("")

    any_found = False
    for stem in PACKET_STEMS:
        coder_paths = completed[stem]
        if not coder_paths:
            continue
        coder_frames: dict[str, pd.DataFrame] = {}
        for coder_id, path in sorted(coder_paths.items()):
            any_found = True
            df = read_csv_robust(path)
            key = load_key(args.keys_dir, stem, coder_id)
            if key is None:
                report_lines.append(
                    f"WARNING: no key file for `{stem}` (coder `{coder_id}`); "
                    "model comparisons and bucket splits unavailable. "
                    "Run build_ra_packets.py to regenerate keys."
                )
                report_lines.append("")
            df = join_key(df, key)
            coder_frames[coder_id] = df
            report_lines.extend(
                SUMMARIZERS[stem](df.copy(), coder_id, args.summary_dir, args)
            )
        report_lines.extend(
            intercoder_section(stem, coder_frames, args.adjudication_dir, args)
        )

    if not any_found:
        report_lines.append(
            "No completed coding files were found in `completed/`. Expected names: "
            "`<packet>_completed.csv`, `<packet>_completed_<coder>.csv`, or "
            "`<coder>/<packet>_completed.csv`."
        )

    out_path = args.summary_dir / "ra_validation_summary.md"
    out_path.write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote summary to {out_path}")
    print("Reminder: summary/ and adjudication/ join in unblinded key data. PI-only.")


if __name__ == "__main__":
    main()
