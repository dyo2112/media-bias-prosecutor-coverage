"""
Step 6: Statistical analysis — compare coverage between progressive and
traditional prosecutors with rigorous tests.

Analyses:
  1. Progressive vs Traditional: t-test, Mann-Whitney U, effect sizes
  2. Same-county paired comparisons (Boudin/Jenkins, O'Malley/Price)
  3. OLS regression with controls
  4. Framing differential (chi-square)
  5. Segmented interrupted time series at tenure transitions
  6. Equivalence test (TOST)
  7. Bootstrap confidence intervals
  8. Sensitivity analysis excluding fallback-attributed articles

Input:  output/04_bias_scores.parquet, output/05_frames.parquet
Output: output/06_stats_results.json, output/06_regression_tables.csv

Prints all results to console and saves structured output.
"""

import json
import warnings
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import mannwhitneyu, ttest_ind, chi2_contingency
import statsmodels.api as sm
import statsmodels.formula.api as smf

from config import (
    BIAS_PARQUET,
    FRAMES_PARQUET,
    ATTRIBUTED_PARQUET,
    STATS_JSON,
    REGRESSION_CSV,
    PROSECUTORS,
    OUTPUT_DIR,
)
from segmented_its_utils import fit_segmented_its, prepare_monthly
from utils import setup_logging, load_parquet, timer, logger

warnings.filterwarnings("ignore", category=FutureWarning)


# ── Effect size calculators ───────────────────────────────────────────────

def cohens_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """Cohen's d effect size (pooled standard deviation)."""
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return (np.mean(group1) - np.mean(group2)) / pooled_std


def cliffs_delta(group1: np.ndarray, group2: np.ndarray) -> float:
    """Cliff's delta (non-parametric effect size)."""
    n1, n2 = len(group1), len(group2)
    if n1 == 0 or n2 == 0:
        return 0.0
    # Count dominance
    more = sum(1 for x in group1 for y in group2 if x > y)
    less = sum(1 for x in group1 for y in group2 if x < y)
    return (more - less) / (n1 * n2)


def bootstrap_ci(
    data: np.ndarray,
    stat_fn=np.mean,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Bootstrap confidence interval. Returns (estimate, lower, upper)."""
    rng = np.random.default_rng(seed)
    estimate = stat_fn(data)
    boot_stats = []
    for _ in range(n_boot):
        sample = rng.choice(data, size=len(data), replace=True)
        boot_stats.append(stat_fn(sample))
    alpha = (1 - ci) / 2
    lower = np.percentile(boot_stats, 100 * alpha)
    upper = np.percentile(boot_stats, 100 * (1 - alpha))
    return float(estimate), float(lower), float(upper)


def bootstrap_diff_ci(
    group1: np.ndarray,
    group2: np.ndarray,
    stat_fn=np.mean,
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Bootstrap CI for the difference in a statistic between two groups."""
    rng = np.random.default_rng(seed)
    observed = stat_fn(group1) - stat_fn(group2)
    boot_diffs = []
    for _ in range(n_boot):
        s1 = rng.choice(group1, size=len(group1), replace=True)
        s2 = rng.choice(group2, size=len(group2), replace=True)
        boot_diffs.append(stat_fn(s1) - stat_fn(s2))
    alpha = (1 - ci) / 2
    lower = np.percentile(boot_diffs, 100 * alpha)
    upper = np.percentile(boot_diffs, 100 * (1 - alpha))
    return float(observed), float(lower), float(upper)


# ── TOST Equivalence Test ─────────────────────────────────────────────────

def tost_test(
    group1: np.ndarray,
    group2: np.ndarray,
    bound: float = 0.2,
) -> dict:
    """Two One-Sided Tests (TOST) for equivalence.

    Tests whether the difference in means is within [-bound*pooled_sd, +bound*pooled_sd].
    Default bound = 0.2 (small effect size by convention).
    """
    n1, n2 = len(group1), len(group2)
    mean_diff = np.mean(group1) - np.mean(group2)
    pooled_sd = np.sqrt(
        ((n1 - 1) * np.var(group1, ddof=1) + (n2 - 1) * np.var(group2, ddof=1))
        / (n1 + n2 - 2)
    )
    se = pooled_sd * np.sqrt(1 / n1 + 1 / n2)
    dof = n1 + n2 - 2
    delta = bound * pooled_sd

    # Test 1: H0: diff <= -delta vs H1: diff > -delta
    t1 = (mean_diff + delta) / se
    p1 = 1 - stats.t.cdf(t1, dof)

    # Test 2: H0: diff >= delta vs H1: diff < delta
    t2 = (mean_diff - delta) / se
    p2 = stats.t.cdf(t2, dof)

    p_tost = max(p1, p2)

    return {
        "mean_diff": float(mean_diff),
        "equivalence_bound_raw": float(delta),
        "equivalence_bound_d": bound,
        "t1": float(t1),
        "p1": float(p1),
        "t2": float(t2),
        "p2": float(p2),
        "p_tost": float(p_tost),
        "equivalent": p_tost < 0.05,
    }


# ── Analysis functions ────────────────────────────────────────────────────

def analysis_1_group_comparison(df: pd.DataFrame) -> dict:
    """Primary comparison: Progressive vs Traditional on composite bias score."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 1: Progressive vs Traditional — Composite Bias Score")
    logger.info("=" * 70)

    prog = df.loc[df["prosecutor_type"] == "Progressive", "composite_bias_score"].dropna().values
    trad = df.loc[df["prosecutor_type"] == "Traditional", "composite_bias_score"].dropna().values

    logger.info(f"Progressive: n={len(prog)}, mean={np.mean(prog):.4f}, sd={np.std(prog, ddof=1):.4f}")
    logger.info(f"Traditional: n={len(trad)}, mean={np.mean(trad):.4f}, sd={np.std(trad, ddof=1):.4f}")

    # Welch's t-test
    t_stat, p_ttest = ttest_ind(prog, trad, equal_var=False)
    logger.info(f"\nWelch's t-test: t={t_stat:.4f}, p={p_ttest:.6f}")

    # Mann-Whitney U
    u_stat, p_mann = mannwhitneyu(prog, trad, alternative="two-sided")
    logger.info(f"Mann-Whitney U: U={u_stat:.0f}, p={p_mann:.6f}")

    # Effect sizes
    d = cohens_d(prog, trad)
    delta = cliffs_delta(prog, trad)
    logger.info(f"\nCohen's d: {d:.4f} ({'negligible' if abs(d) < 0.2 else 'small' if abs(d) < 0.5 else 'medium' if abs(d) < 0.8 else 'large'})")
    logger.info(f"Cliff's delta: {delta:.4f}")

    # Bootstrap CI for the difference
    diff_est, diff_lo, diff_hi = bootstrap_diff_ci(prog, trad, n_boot=10000)
    logger.info(f"\nBootstrap 95% CI for mean difference: {diff_est:.4f} [{diff_lo:.4f}, {diff_hi:.4f}]")

    # Equivalence test
    tost = tost_test(prog, trad, bound=0.2)
    logger.info(f"\nTOST Equivalence Test (bound=0.2d): p={tost['p_tost']:.6f}, equivalent={tost['equivalent']}")

    return {
        "progressive_n": len(prog),
        "progressive_mean": float(np.mean(prog)),
        "progressive_sd": float(np.std(prog, ddof=1)),
        "traditional_n": len(trad),
        "traditional_mean": float(np.mean(trad)),
        "traditional_sd": float(np.std(trad, ddof=1)),
        "welch_t": float(t_stat),
        "welch_p": float(p_ttest),
        "mannwhitney_u": float(u_stat),
        "mannwhitney_p": float(p_mann),
        "cohens_d": float(d),
        "cliffs_delta": float(delta),
        "bootstrap_diff": diff_est,
        "bootstrap_ci_lower": diff_lo,
        "bootstrap_ci_upper": diff_hi,
        "tost": tost,
    }


def _fallback_assignment_mask(df: pd.DataFrame) -> tuple[pd.Series, str]:
    """Return fallback-attribution mask and detection method label."""
    if "assigned_via_generic_da_fallback" in df.columns:
        mask = df["assigned_via_generic_da_fallback"].fillna(False).astype(bool)
        return mask, "explicit_flag"

    # If Step 04 output is stale and lacks the explicit column, recover it from
    # Step 03 by article_id (the source of truth for attribution metadata).
    if "article_id" in df.columns and ATTRIBUTED_PARQUET.exists():
        try:
            attrs = pd.read_parquet(
                ATTRIBUTED_PARQUET,
                columns=["article_id", "assigned_via_generic_da_fallback"],
            )
            attrs = attrs.drop_duplicates(subset=["article_id"])
            attr_map = (
                attrs.assign(article_id=lambda x: x["article_id"].astype(str))
                .set_index("article_id")["assigned_via_generic_da_fallback"]
            )
            joined = (
                df["article_id"]
                .astype(str)
                .map(attr_map)
            )
            if joined.notna().any():
                mask = joined.fillna(False).astype(bool)
                return mask, "joined_from_03_attribution"
        except Exception as e:
            msg = str(e)
            if "assigned_via_generic_da_fallback" not in msg:
                logger.warning(f"Fallback flag join from {ATTRIBUTED_PARQUET.name} failed: {e}")

    required = {"total_prosecutor_mentions", "generic_da_refs", "primary_prosecutor"}
    if required.issubset(df.columns):
        mask = (
            (df["total_prosecutor_mentions"] == 0)
            & (df["generic_da_refs"] > 0)
            & df["primary_prosecutor"].notna()
        )
        return mask, "inferred_from_counts_and_generic_refs"

    return pd.Series(False, index=df.index), "no_fallback_columns_available"


def analysis_12_sensitivity_no_fallback(df: pd.DataFrame) -> dict:
    """Recompute group comparison after excluding fallback-attributed articles."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 12: Sensitivity (Exclude Fallback Attributions)")
    logger.info("=" * 70)

    fallback_mask, method = _fallback_assignment_mask(df)
    n_total = len(df)
    n_excluded = int(fallback_mask.sum())
    n_remaining = int(n_total - n_excluded)
    excluded_pct = (100 * n_excluded / n_total) if n_total > 0 else 0.0

    logger.info(
        f"Fallback detection method: {method}; excluded {n_excluded:,}/{n_total:,} "
        f"articles ({excluded_pct:.1f}%)"
    )

    sens_df = df.loc[~fallback_mask].copy()
    prog = sens_df.loc[
        sens_df["prosecutor_type"] == "Progressive", "composite_bias_score"
    ].dropna().values
    trad = sens_df.loc[
        sens_df["prosecutor_type"] == "Traditional", "composite_bias_score"
    ].dropna().values

    if len(prog) < 5 or len(trad) < 5:
        logger.warning(
            f"Insufficient data after exclusion: Progressive={len(prog)}, "
            f"Traditional={len(trad)}"
        )
        return {
            "fallback_detection_method": method,
            "n_total": int(n_total),
            "n_excluded_fallback": int(n_excluded),
            "n_remaining": int(n_remaining),
            "excluded_pct": float(excluded_pct),
            "error": "insufficient_data_after_exclusion",
        }

    t_stat, p_ttest = ttest_ind(prog, trad, equal_var=False)
    u_stat, p_mann = mannwhitneyu(prog, trad, alternative="two-sided")
    d = cohens_d(prog, trad)
    diff_est, diff_lo, diff_hi = bootstrap_diff_ci(prog, trad, n_boot=10000)
    tost = tost_test(prog, trad, bound=0.2)

    logger.info(
        f"After exclusion: Progressive n={len(prog)}, mean={np.mean(prog):.4f}; "
        f"Traditional n={len(trad)}, mean={np.mean(trad):.4f}"
    )
    logger.info(f"Welch's t-test: t={t_stat:.4f}, p={p_ttest:.6f}")
    logger.info(f"Mann-Whitney U: U={u_stat:.0f}, p={p_mann:.6f}")
    logger.info(f"Cohen's d: {d:.4f}")
    logger.info(
        f"Bootstrap 95% CI for mean diff (Prog - Trad): "
        f"{diff_est:.4f} [{diff_lo:.4f}, {diff_hi:.4f}]"
    )
    logger.info(
        f"TOST Equivalence Test (bound=0.2d): p={tost['p_tost']:.6f}, "
        f"equivalent={tost['equivalent']}"
    )

    return {
        "fallback_detection_method": method,
        "n_total": int(n_total),
        "n_excluded_fallback": int(n_excluded),
        "n_remaining": int(n_remaining),
        "excluded_pct": float(excluded_pct),
        "progressive_n": int(len(prog)),
        "progressive_mean": float(np.mean(prog)),
        "progressive_sd": float(np.std(prog, ddof=1)),
        "traditional_n": int(len(trad)),
        "traditional_mean": float(np.mean(trad)),
        "traditional_sd": float(np.std(trad, ddof=1)),
        "welch_t": float(t_stat),
        "welch_p": float(p_ttest),
        "mannwhitney_u": float(u_stat),
        "mannwhitney_p": float(p_mann),
        "cohens_d": float(d),
        "bootstrap_diff": diff_est,
        "bootstrap_ci_lower": diff_lo,
        "bootstrap_ci_upper": diff_hi,
        "tost": tost,
    }


def analysis_2_paired_county(df: pd.DataFrame) -> dict:
    """Same-county paired comparisons — the strongest quasi-experimental design."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 2: Same-County Paired Comparisons")
    logger.info("=" * 70)

    pairs = [
        ("Chesa Boudin", "Brooke Jenkins", "San Francisco"),
        ("Pamela Price", "Nancy O'Malley", "Alameda"),
    ]

    results = {}
    for prog_name, trad_name, county in pairs:
        logger.info(f"\n── {prog_name} (Progressive) vs {trad_name} (Traditional) [{county}] ──")

        g1 = df.loc[df["primary_prosecutor"] == prog_name, "composite_bias_score"].dropna().values
        g2 = df.loc[df["primary_prosecutor"] == trad_name, "composite_bias_score"].dropna().values

        if len(g1) < 5 or len(g2) < 5:
            logger.warning(f"  Insufficient data: {prog_name}={len(g1)}, {trad_name}={len(g2)}")
            continue

        logger.info(f"  {prog_name}: n={len(g1)}, mean={np.mean(g1):.4f}")
        logger.info(f"  {trad_name}: n={len(g2)}, mean={np.mean(g2):.4f}")

        t_stat, p_val = ttest_ind(g1, g2, equal_var=False)
        d = cohens_d(g1, g2)
        diff_est, diff_lo, diff_hi = bootstrap_diff_ci(g1, g2, n_boot=10000)

        logger.info(f"  t={t_stat:.4f}, p={p_val:.6f}")
        logger.info(f"  Cohen's d={d:.4f}")
        logger.info(f"  Bootstrap 95% CI: {diff_est:.4f} [{diff_lo:.4f}, {diff_hi:.4f}]")

        results[f"{county}_{prog_name}_vs_{trad_name}"] = {
            "county": county,
            "progressive": prog_name,
            "traditional": trad_name,
            "n_progressive": len(g1),
            "n_traditional": len(g2),
            "mean_progressive": float(np.mean(g1)),
            "mean_traditional": float(np.mean(g2)),
            "welch_t": float(t_stat),
            "welch_p": float(p_val),
            "cohens_d": float(d),
            "bootstrap_diff": diff_est,
            "bootstrap_ci_lower": diff_lo,
            "bootstrap_ci_upper": diff_hi,
        }

    return results


def analysis_3_regression(df: pd.DataFrame) -> dict:
    """OLS regression with controls for county, publication, year, article length."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 3: OLS Regression with Controls")
    logger.info("=" * 70)

    # Prepare data
    reg_df = df[["composite_bias_score", "prosecutor_type", "primary_prosecutor",
                  "publication", "date", "body"]].dropna(subset=["composite_bias_score"]).copy()

    reg_df["is_progressive"] = (reg_df["prosecutor_type"] == "Progressive").astype(int)
    reg_df["year"] = reg_df["date"].dt.year
    reg_df["article_length"] = reg_df["body"].str.split().str.len()

    # Get county from prosecutor
    prosecutor_county = {p.name: p.county for p in PROSECUTORS}
    reg_df["county"] = reg_df["primary_prosecutor"].map(prosecutor_county)

    # Basic model
    try:
        formula = "composite_bias_score ~ is_progressive + C(county) + C(year) + article_length"
        model = smf.ols(formula, data=reg_df).fit(
            cov_type="cluster",
            cov_kwds={"groups": reg_df["publication"]},
        )
        logger.info("\nModel 1: Bias ~ Progressive + County + Year + Article Length")
        logger.info(f"  (Cluster-robust SEs by publication)")
        logger.info(model.summary().tables[1].as_text())
        logger.info(f"\n  R²: {model.rsquared:.4f}")
        logger.info(f"  Progressive coefficient: {model.params.get('is_progressive', 'N/A'):.4f}")
        logger.info(f"  Progressive p-value: {model.pvalues.get('is_progressive', 'N/A'):.6f}")

        regression_results = {
            "r_squared": float(model.rsquared),
            "progressive_coef": float(model.params.get("is_progressive", np.nan)),
            "progressive_se": float(model.bse.get("is_progressive", np.nan)),
            "progressive_p": float(model.pvalues.get("is_progressive", np.nan)),
            "n_obs": int(model.nobs),
        }

        # Save full regression table
        reg_table = pd.DataFrame({
            "coefficient": model.params,
            "std_error": model.bse,
            "t_value": model.tvalues,
            "p_value": model.pvalues,
            "ci_lower": model.conf_int()[0],
            "ci_upper": model.conf_int()[1],
        })
        reg_table.to_csv(REGRESSION_CSV)
        logger.info(f"\nRegression table saved to {REGRESSION_CSV.name}")

    except Exception as e:
        logger.error(f"Regression failed: {e}")
        regression_results = {"error": str(e)}

    return regression_results


def analysis_4_framing(df: pd.DataFrame) -> dict:
    """Framing differential: chi-square tests on frame frequencies by type."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 4: Framing Differential Analysis")
    logger.info("=" * 70)

    frame_cols = [c for c in df.columns if c.startswith("frame_") and c != "dominant_frame"]

    if not frame_cols:
        logger.warning("No frame columns found. Run 05_framing_analysis.py first.")
        return {}

    results = {}

    # Chi-square on dominant frame
    if "dominant_frame" in df.columns:
        ct = pd.crosstab(df["prosecutor_type"], df["dominant_frame"])
        if ct.shape[0] >= 2 and ct.shape[1] >= 2:
            chi2, p, dof, expected = chi2_contingency(ct)
            cramers_v = np.sqrt(chi2 / (ct.sum().sum() * (min(ct.shape) - 1)))
            logger.info(f"\nDominant Frame × Prosecutor Type:")
            logger.info(f"  Chi² = {chi2:.2f}, p = {p:.6f}, Cramér's V = {cramers_v:.4f}")
            logger.info(f"\nContingency table (proportions):")
            ct_norm = ct.div(ct.sum(axis=1), axis=0)
            logger.info(ct_norm.round(3).to_string())

            results["dominant_frame_chi2"] = {
                "chi2": float(chi2),
                "p": float(p),
                "dof": int(dof),
                "cramers_v": float(cramers_v),
            }

    # Per-frame comparison (continuous scores)
    for fc in frame_cols:
        prog = df.loc[df["prosecutor_type"] == "Progressive", fc].dropna().values
        trad = df.loc[df["prosecutor_type"] == "Traditional", fc].dropna().values

        if len(prog) < 5 or len(trad) < 5:
            continue

        t_stat, p_val = ttest_ind(prog, trad, equal_var=False)
        d = cohens_d(prog, trad)

        frame_name = fc.replace("frame_", "")
        logger.info(f"\n  {frame_name}: Prog mean={np.mean(prog):.3f}, "
                     f"Trad mean={np.mean(trad):.3f}, d={d:.3f}, p={p_val:.4f}")

        results[fc] = {
            "progressive_mean": float(np.mean(prog)),
            "traditional_mean": float(np.mean(trad)),
            "cohens_d": float(d),
            "p_value": float(p_val),
        }

    return results


def analysis_5_time_series(df: pd.DataFrame) -> dict:
    """Segmented interrupted time series around tenure transitions."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 5: Segmented Interrupted Time Series")
    logger.info("=" * 70)

    results = {}

    transitions = [
        {
            "label": "SF: Boudin to Jenkins",
            "county_prosecutors": ["Chesa Boudin", "Brooke Jenkins"],
            "transition_date": pd.Timestamp("2022-07-08"),
        },
        {
            "label": "Alameda: O'Malley to Price",
            "county_prosecutors": ["Nancy O'Malley", "Pamela Price"],
            "transition_date": pd.Timestamp("2023-01-03"),
        },
    ]

    for trans in transitions:
        logger.info(f"\n-- {trans['label']} --")
        subset = df[df["primary_prosecutor"].isin(trans["county_prosecutors"])].copy()

        if len(subset) < 20:
            logger.warning(f"  Insufficient data: {len(subset)} articles")
            continue

        monthly = prepare_monthly(
            df=subset,
            prosecutors=tuple(trans["county_prosecutors"]),
            outcome_col="composite_bias_score",
        )
        model = fit_segmented_its(monthly, trans["transition_date"])
        if "error" in model:
            logger.warning(f"  Segmented ITS skipped: {model['error']}")
            continue

        # Preserve article-level pre/post descriptives for continuity.
        transition_dt = trans["transition_date"]
        pre = subset.loc[subset["date"] < transition_dt, "composite_bias_score"].dropna().values
        post = subset.loc[subset["date"] >= transition_dt, "composite_bias_score"].dropna().values

        prepost = None
        if len(pre) >= 5 and len(post) >= 5:
            t_stat, p_val = ttest_ind(pre, post, equal_var=False)
            d = cohens_d(pre, post)
            prepost = {
                "n_pre": len(pre),
                "n_post": len(post),
                "mean_pre": float(np.mean(pre)),
                "mean_post": float(np.mean(post)),
                "welch_t": float(t_stat),
                "welch_p": float(p_val),
                "cohens_d": float(d),
            }
            logger.info(
                f"  Pre/post descriptive: n_pre={len(pre)}, n_post={len(post)}, "
                f"d={d:.4f}, p={p_val:.6f}"
            )
        else:
            logger.info(
                f"  Pre/post descriptive skipped: n_pre={len(pre)}, n_post={len(post)}"
            )

        level_beta = model["coefficients"]["post"]
        level_p = model["p_values"]["post"]
        slope_beta = model["coefficients"]["time_after"]
        slope_p = model["p_values"]["time_after"]
        horizon = model["horizon_months"]
        horizon_eff = model["effect_at_horizon"]
        horizon_p = model["effect_at_horizon_p"]
        logger.info(
            f"  Segmented ITS: level={level_beta:.4f} (p={level_p:.4g}), "
            f"slope={slope_beta:.4f} (p={slope_p:.4g}), "
            f"{horizon}m effect={horizon_eff:.4f} (p={horizon_p:.4g})"
        )

        entry = {
            "model": "segmented_its",
            **model,
            "level_change_beta": float(level_beta),
            "level_change_p": float(level_p),
            "slope_change_beta": float(slope_beta),
            "slope_change_p": float(slope_p),
        }
        if prepost is not None:
            entry["prepost_descriptive"] = prepost
            # Backward-compatible top-level fields.
            entry.update(prepost)
        results[trans["label"]] = entry

    return results


def analysis_6_per_method(df: pd.DataFrame) -> dict:
    """Break down each method's scores by prosecutor type."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 6: Per-Method Breakdown")
    logger.info("=" * 70)

    method_cols = [
        "score_aspect_sentiment",
        "score_stance",
        "score_keywords",
        "score_doc_sentiment",
    ]

    results = {}
    for col in method_cols:
        if col not in df.columns or df[col].isna().all():
            continue

        prog = df.loc[df["prosecutor_type"] == "Progressive", col].dropna().values
        trad = df.loc[df["prosecutor_type"] == "Traditional", col].dropna().values

        if len(prog) < 5 or len(trad) < 5:
            continue

        t_stat, p_val = ttest_ind(prog, trad, equal_var=False)
        d = cohens_d(prog, trad)

        logger.info(f"\n{col}:")
        logger.info(f"  Progressive: mean={np.mean(prog):.4f}, n={len(prog)}")
        logger.info(f"  Traditional: mean={np.mean(trad):.4f}, n={len(trad)}")
        logger.info(f"  t={t_stat:.4f}, p={p_val:.6f}, d={d:.4f}")

        results[col] = {
            "progressive_mean": float(np.mean(prog)),
            "traditional_mean": float(np.mean(trad)),
            "cohens_d": float(d),
            "p_value": float(p_val),
        }

    return results


def analysis_7_quarterly_effects(df: pd.DataFrame) -> dict:
    """Compute Cohen's d per quarter to assess temporal heterogeneity.

    For each quarter with sufficient data in both groups, compute the
    effect size (Progressive vs Traditional) on composite_bias_score.
    This reveals whether the bias is stable over time or concentrated
    in particular periods.
    """
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 7: Quarterly Effect Sizes (Temporal Heterogeneity)")
    logger.info("=" * 70)

    df = df.copy()
    df["quarter"] = df["date"].dt.to_period("Q")

    min_per_group = 15  # minimum articles per group per quarter

    quarterly = []
    for q in sorted(df["quarter"].unique()):
        qdf = df[df["quarter"] == q]
        prog = qdf.loc[qdf["prosecutor_type"] == "Progressive", "composite_bias_score"].dropna().values
        trad = qdf.loc[qdf["prosecutor_type"] == "Traditional", "composite_bias_score"].dropna().values

        if len(prog) < min_per_group or len(trad) < min_per_group:
            continue

        d = cohens_d(prog, trad)
        t_stat, p_val = ttest_ind(prog, trad, equal_var=False)

        # Bootstrap CI for d
        rng = np.random.default_rng(42)
        boot_ds = []
        for _ in range(2000):
            s1 = rng.choice(prog, size=len(prog), replace=True)
            s2 = rng.choice(trad, size=len(trad), replace=True)
            boot_ds.append(cohens_d(s1, s2))
        ci_lo = float(np.percentile(boot_ds, 2.5))
        ci_hi = float(np.percentile(boot_ds, 97.5))

        quarterly.append({
            "quarter": str(q),
            "n_prog": int(len(prog)),
            "n_trad": int(len(trad)),
            "prog_mean": float(np.mean(prog)),
            "trad_mean": float(np.mean(trad)),
            "cohens_d": float(d),
            "ci_lower": ci_lo,
            "ci_upper": ci_hi,
            "p_value": float(p_val),
        })

        logger.info(f"  {q}: d={d:.3f} [{ci_lo:.3f}, {ci_hi:.3f}], "
                     f"n_prog={len(prog)}, n_trad={len(trad)}, p={p_val:.4f}")

    # Also compute per-county quarterly effects
    county_quarterly = {}
    county_map = {
        "San Francisco": ["Chesa Boudin", "Brooke Jenkins"],
        "Alameda": ["Nancy O'Malley", "Pamela Price"],
    }
    for county, prosecutors in county_map.items():
        cdf = df[df["primary_prosecutor"].isin(prosecutors)]
        cq = []
        for q in sorted(cdf["quarter"].unique()):
            qdf = cdf[cdf["quarter"] == q]
            prog = qdf.loc[qdf["prosecutor_type"] == "Progressive", "composite_bias_score"].dropna().values
            trad = qdf.loc[qdf["prosecutor_type"] == "Traditional", "composite_bias_score"].dropna().values
            if len(prog) < min_per_group or len(trad) < min_per_group:
                continue
            d = cohens_d(prog, trad)
            t_stat, p_val = ttest_ind(prog, trad, equal_var=False)
            rng = np.random.default_rng(42)
            boot_ds = []
            for _ in range(2000):
                s1 = rng.choice(prog, size=len(prog), replace=True)
                s2 = rng.choice(trad, size=len(trad), replace=True)
                boot_ds.append(cohens_d(s1, s2))
            ci_lo = float(np.percentile(boot_ds, 2.5))
            ci_hi = float(np.percentile(boot_ds, 97.5))
            cq.append({
                "quarter": str(q),
                "n_prog": int(len(prog)),
                "n_trad": int(len(trad)),
                "cohens_d": float(d),
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "p_value": float(p_val),
            })
        county_quarterly[county] = cq
        logger.info(f"\n  {county}: {len(cq)} quarters with sufficient data")

    # Summary stats on temporal variability
    if quarterly:
        ds = [q["cohens_d"] for q in quarterly]
        logger.info(f"\nOverall quarterly d: mean={np.mean(ds):.3f}, "
                     f"sd={np.std(ds):.3f}, range=[{min(ds):.3f}, {max(ds):.3f}]")

    return {
        "overall_quarterly": quarterly,
        "county_quarterly": county_quarterly,
    }


# ── Per-method deep-dive analyses ────────────────────────────────────────

METHOD_COLS = [
    "score_aspect_sentiment",
    "score_stance",
    "score_keywords",
    "score_doc_sentiment",
]

METHOD_LABELS = {
    "score_aspect_sentiment": "A: Aspect Sentiment",
    "score_stance": "B: Stance",
    "score_keywords": "C: Keywords",
    "score_doc_sentiment": "D: Doc Sentiment",
}


def analysis_8_per_method_regression(df: pd.DataFrame) -> dict:
    """OLS regression for each method separately — does ideology predict each dimension?"""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 8: Per-Method OLS Regressions")
    logger.info("=" * 70)

    reg_df = df[["prosecutor_type", "primary_prosecutor",
                  "publication", "date", "body"] + METHOD_COLS].copy()
    reg_df["is_progressive"] = (reg_df["prosecutor_type"] == "Progressive").astype(int)
    reg_df["year"] = reg_df["date"].dt.year
    reg_df["article_length"] = reg_df["body"].str.split().str.len()
    prosecutor_county = {p.name: p.county for p in PROSECUTORS}
    reg_df["county"] = reg_df["primary_prosecutor"].map(prosecutor_county)

    results = {}
    for col in METHOD_COLS:
        if col not in reg_df.columns or reg_df[col].isna().all():
            continue
        method_df = reg_df.dropna(subset=[col])
        try:
            formula = f"{col} ~ is_progressive + C(county) + C(year) + article_length"
            model = smf.ols(formula, data=method_df).fit(
                cov_type="cluster",
                cov_kwds={"groups": method_df["publication"]},
            )
            coef = float(model.params.get("is_progressive", np.nan))
            se = float(model.bse.get("is_progressive", np.nan))
            p = float(model.pvalues.get("is_progressive", np.nan))
            ci = model.conf_int().loc["is_progressive"]
            r2 = float(model.rsquared)
            logger.info(f"\n  {METHOD_LABELS.get(col, col)}:")
            logger.info(f"    β={coef:.4f}, SE={se:.4f}, p={p:.6f}, "
                         f"CI=[{float(ci[0]):.4f}, {float(ci[1]):.4f}], R²={r2:.4f}")
            results[col] = {
                "progressive_coef": coef,
                "progressive_se": se,
                "progressive_p": p,
                "ci_lower": float(ci[0]),
                "ci_upper": float(ci[1]),
                "r_squared": r2,
                "n_obs": int(model.nobs),
            }
        except Exception as e:
            logger.error(f"  Regression for {col} failed: {e}")
            results[col] = {"error": str(e)}

    return results


def analysis_9_per_method_paired(df: pd.DataFrame) -> dict:
    """Per-method same-county paired comparisons."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 9: Per-Method Paired County Comparisons")
    logger.info("=" * 70)

    pairs = [
        ("Chesa Boudin", "Brooke Jenkins", "San Francisco"),
        ("Pamela Price", "Nancy O'Malley", "Alameda"),
    ]

    results = {}
    for prog_name, trad_name, county in pairs:
        pair_key = f"{county}_{prog_name}_vs_{trad_name}"
        results[pair_key] = {}
        for col in METHOD_COLS:
            if col not in df.columns or df[col].isna().all():
                continue
            g1 = df.loc[df["primary_prosecutor"] == prog_name, col].dropna().values
            g2 = df.loc[df["primary_prosecutor"] == trad_name, col].dropna().values
            if len(g1) < 5 or len(g2) < 5:
                continue
            t_stat, p_val = ttest_ind(g1, g2, equal_var=False)
            d = cohens_d(g1, g2)
            diff_est, diff_lo, diff_hi = bootstrap_diff_ci(g1, g2, n_boot=5000)
            logger.info(f"  {county} | {METHOD_LABELS.get(col, col)}: "
                         f"d={d:.4f}, p={p_val:.6f}")
            results[pair_key][col] = {
                "cohens_d": float(d),
                "welch_t": float(t_stat),
                "welch_p": float(p_val),
                "bootstrap_ci_lower": diff_lo,
                "bootstrap_ci_upper": diff_hi,
                "n_progressive": len(g1),
                "n_traditional": len(g2),
            }

    return results


def analysis_10_per_method_quarterly(df: pd.DataFrame) -> dict:
    """Per-method quarterly Cohen's d — reveals which dimensions are event-driven."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 10: Per-Method Quarterly Effects")
    logger.info("=" * 70)

    df = df.copy()
    df["quarter"] = df["date"].dt.to_period("Q")
    min_per_group = 15

    results = {}
    for col in METHOD_COLS:
        if col not in df.columns or df[col].isna().all():
            continue
        quarterly = []
        for q in sorted(df["quarter"].unique()):
            qdf = df[df["quarter"] == q]
            prog = qdf.loc[qdf["prosecutor_type"] == "Progressive", col].dropna().values
            trad = qdf.loc[qdf["prosecutor_type"] == "Traditional", col].dropna().values
            if len(prog) < min_per_group or len(trad) < min_per_group:
                continue
            d = cohens_d(prog, trad)
            _, p_val = ttest_ind(prog, trad, equal_var=False)
            # Bootstrap CI (reduced iterations for speed — 4 methods × 21 quarters)
            rng = np.random.default_rng(42)
            boot_ds = [cohens_d(
                rng.choice(prog, size=len(prog), replace=True),
                rng.choice(trad, size=len(trad), replace=True),
            ) for _ in range(1000)]
            quarterly.append({
                "quarter": str(q),
                "n_prog": int(len(prog)),
                "n_trad": int(len(trad)),
                "cohens_d": float(d),
                "ci_lower": float(np.percentile(boot_ds, 2.5)),
                "ci_upper": float(np.percentile(boot_ds, 97.5)),
                "p_value": float(p_val),
            })
        results[col] = quarterly
        if quarterly:
            ds = [q["cohens_d"] for q in quarterly]
            logger.info(f"  {METHOD_LABELS.get(col, col)}: {len(quarterly)} quarters, "
                         f"d range=[{min(ds):.3f}, {max(ds):.3f}], sd={np.std(ds):.3f}")

    return results


def analysis_11_per_method_time_series(df: pd.DataFrame) -> dict:
    """Per-method segmented interrupted time series at tenure transitions."""
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS 11: Per-Method Segmented Interrupted Time Series")
    logger.info("=" * 70)

    transitions = [
        {
            "label": "SF: Boudin to Jenkins",
            "county_prosecutors": ["Chesa Boudin", "Brooke Jenkins"],
            "transition_date": pd.Timestamp("2022-07-08"),
        },
        {
            "label": "Alameda: O'Malley to Price",
            "county_prosecutors": ["Nancy O'Malley", "Pamela Price"],
            "transition_date": pd.Timestamp("2023-01-03"),
        },
    ]

    results = {}
    for trans in transitions:
        subset = df[df["primary_prosecutor"].isin(trans["county_prosecutors"])].copy()
        if len(subset) < 20:
            continue
        results[trans["label"]] = {}
        for col in METHOD_COLS:
            if col not in subset.columns or subset[col].isna().all():
                continue

            monthly = prepare_monthly(
                df=subset,
                prosecutors=tuple(trans["county_prosecutors"]),
                outcome_col=col,
            )
            model = fit_segmented_its(monthly, trans["transition_date"])
            if "error" in model:
                continue

            pre = subset.loc[subset["date"] < trans["transition_date"], col].dropna().values
            post = subset.loc[subset["date"] >= trans["transition_date"], col].dropna().values
            prepost = None
            if len(pre) >= 5 and len(post) >= 5:
                t_stat, p_val = ttest_ind(pre, post, equal_var=False)
                d = cohens_d(pre, post)
                prepost = {
                    "n_pre": len(pre),
                    "n_post": len(post),
                    "mean_pre": float(np.mean(pre)),
                    "mean_post": float(np.mean(post)),
                    "welch_t": float(t_stat),
                    "welch_p": float(p_val),
                    "cohens_d": float(d),
                }

            level_beta = model["coefficients"]["post"]
            level_p = model["p_values"]["post"]
            slope_beta = model["coefficients"]["time_after"]
            slope_p = model["p_values"]["time_after"]
            logger.info(
                f"  {trans['label']} | {METHOD_LABELS.get(col, col)}: "
                f"level={level_beta:.4f} (p={level_p:.4g}), "
                f"slope={slope_beta:.4f} (p={slope_p:.4g})"
            )

            entry = {
                "model": "segmented_its",
                **model,
                "level_change_beta": float(level_beta),
                "level_change_p": float(level_p),
                "slope_change_beta": float(slope_beta),
                "slope_change_p": float(slope_p),
            }
            if prepost is not None:
                entry["prepost_descriptive"] = prepost
                # Backward-compatible top-level fields.
                entry.update(prepost)
            results[trans["label"]][col] = entry

    return results


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    # Load bias scores
    df = load_parquet(BIAS_PARQUET)
    logger.info(f"Loaded {len(df):,} articles with bias scores")

    # Try to merge framing data if available
    if FRAMES_PARQUET.exists():
        frames = load_parquet(FRAMES_PARQUET)
        frame_cols = [c for c in frames.columns if c.startswith("frame_") or c == "dominant_frame"]
        if frame_cols:
            # Merge on article_id
            df = df.merge(
                frames[["article_id"] + frame_cols],
                on="article_id",
                how="left",
                suffixes=("", "_frame"),
            )
            logger.info(f"Merged {len(frame_cols)} frame columns")

    # Filter to articles with a primary prosecutor and composite score
    analysis_df = df[
        df["primary_prosecutor"].notna()
        & df["composite_bias_score"].notna()
    ].copy()
    logger.info(f"Articles for analysis: {len(analysis_df):,}")

    all_results = {}

    # Run all analyses
    with timer("Analysis 1: Group comparison"):
        all_results["group_comparison"] = analysis_1_group_comparison(analysis_df)

    with timer("Analysis 2: Paired county comparisons"):
        all_results["paired_county"] = analysis_2_paired_county(analysis_df)

    with timer("Analysis 3: OLS regression"):
        all_results["regression"] = analysis_3_regression(analysis_df)

    with timer("Analysis 4: Framing differential"):
        all_results["framing"] = analysis_4_framing(analysis_df)

    with timer("Analysis 5: Time series"):
        all_results["time_series"] = analysis_5_time_series(analysis_df)

    with timer("Analysis 6: Per-method breakdown"):
        all_results["per_method"] = analysis_6_per_method(analysis_df)

    with timer("Analysis 7: Quarterly effects (temporal heterogeneity)"):
        all_results["quarterly_effects"] = analysis_7_quarterly_effects(analysis_df)

    with timer("Analysis 8: Per-method regressions"):
        all_results["per_method_regression"] = analysis_8_per_method_regression(analysis_df)

    with timer("Analysis 9: Per-method paired comparisons"):
        all_results["per_method_paired"] = analysis_9_per_method_paired(analysis_df)

    with timer("Analysis 10: Per-method quarterly effects"):
        all_results["per_method_quarterly"] = analysis_10_per_method_quarterly(analysis_df)

    with timer("Analysis 11: Per-method time series"):
        all_results["per_method_time_series"] = analysis_11_per_method_time_series(analysis_df)

    with timer("Analysis 12: Sensitivity (exclude fallback attributions)"):
        all_results["sensitivity_no_fallback"] = analysis_12_sensitivity_no_fallback(analysis_df)

    # ── Save results ───────────────────────────────────────────────────
    with open(STATS_JSON, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    logger.info(f"\nAll results saved to {STATS_JSON.name}")

    # ── Summary of key findings ────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY OF KEY FINDINGS")
    logger.info("=" * 70)

    gc = all_results.get("group_comparison", {})
    if gc:
        logger.info(f"\nOverall: Progressive mean={gc.get('progressive_mean', 'N/A'):.4f}, "
                     f"Traditional mean={gc.get('traditional_mean', 'N/A'):.4f}")
        logger.info(f"  Cohen's d = {gc.get('cohens_d', 'N/A'):.4f}")
        logger.info(f"  p = {gc.get('welch_p', 'N/A'):.6f}")
        tost = gc.get("tost", {})
        if tost:
            logger.info(f"  Equivalence test: {'EQUIVALENT' if tost.get('equivalent') else 'NOT EQUIVALENT'} "
                         f"(p_TOST = {tost.get('p_tost', 'N/A'):.4f})")

    sens = all_results.get("sensitivity_no_fallback", {})
    if sens and "error" not in sens:
        logger.info(
            f"\nSensitivity (exclude fallback): excluded {sens.get('n_excluded_fallback', 0):,} "
            f"/ {sens.get('n_total', 0):,} articles ({sens.get('excluded_pct', 0):.1f}%)"
        )
        logger.info(
            f"  Progressive mean={sens.get('progressive_mean', 'N/A'):.4f}, "
            f"Traditional mean={sens.get('traditional_mean', 'N/A'):.4f}"
        )
        logger.info(f"  Cohen's d = {sens.get('cohens_d', 'N/A'):.4f}")
        logger.info(f"  p = {sens.get('welch_p', 'N/A'):.6f}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
