"""Shared segmented ITS helpers for temporal analyses.

This module centralizes the segmented interrupted time-series logic used by
Step 06 (main stats) and Step 12 (appendix robustness) so their estimates
cannot drift due to duplicated implementations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def build_design(
    monthly: pd.DataFrame,
    transition_date: pd.Timestamp,
) -> tuple[pd.Series, pd.DataFrame]:
    """Construct segmented ITS regressors for monthly data."""
    post_mask = monthly["month_dt"] >= transition_date
    t = np.arange(len(monthly), dtype=float)
    post = post_mask.astype(float).values
    first_post_idx = int(np.flatnonzero(post_mask.values)[0])
    time_after = np.where(post > 0, t - first_post_idx + 1.0, 0.0)

    X = pd.DataFrame(
        {
            "const": 1.0,
            "time": t,
            "post": post,
            "time_after": time_after,
        }
    )
    return post_mask, X


def prepare_monthly(
    df: pd.DataFrame,
    prosecutors: tuple[str, str] | list[str],
    outcome_col: str,
) -> pd.DataFrame:
    """Aggregate article-level data to monthly outcome means."""
    subset = df[df["primary_prosecutor"].isin(prosecutors)].copy()
    subset = subset[subset["date"].notna() & subset[outcome_col].notna()].copy()
    if subset.empty:
        return subset

    subset["month"] = subset["date"].dt.to_period("M")
    monthly = (
        subset.groupby("month", as_index=False)
        .agg(
            mean_outcome=(outcome_col, "mean"),
            n_articles=(outcome_col, "count"),
        )
        .sort_values("month")
    )
    monthly["month_dt"] = monthly["month"].dt.to_timestamp()
    return monthly.reset_index(drop=True)


def fit_segmented_its(
    monthly: pd.DataFrame,
    transition_date: pd.Timestamp,
    max_hac_lag: int = 3,
    min_pre_months: int = 6,
    min_post_months: int = 6,
    horizon_months: int = 12,
) -> dict:
    """Fit weighted segmented ITS with HAC-robust inference."""
    if monthly.empty:
        return {"error": "no_data"}

    post_mask, X = build_design(monthly, transition_date)
    n_pre = int((~post_mask).sum())
    n_post = int(post_mask.sum())
    if n_pre < min_pre_months or n_post < min_post_months:
        return {
            "error": "insufficient_pre_post_months",
            "n_pre_months": n_pre,
            "n_post_months": n_post,
        }

    y = monthly["mean_outcome"].astype(float).values
    w = monthly["n_articles"].astype(float).values

    base = sm.WLS(y, X, weights=w).fit()
    robust = base.get_robustcov_results(cov_type="HAC", maxlags=max_hac_lag)

    names = list(X.columns)
    params = {k: float(v) for k, v in zip(names, robust.params)}
    pvals = {k: float(v) for k, v in zip(names, robust.pvalues)}
    cis_raw = robust.conf_int()
    cis = {k: [float(cis_raw[i, 0]), float(cis_raw[i, 1])] for i, k in enumerate(names)}

    horizon = min(int(horizon_months), n_post)
    L = np.array([0.0, 0.0, 1.0, float(horizon)])
    test = robust.t_test(L)
    effect_h = float(np.asarray(test.effect).reshape(-1)[0])
    p_h = float(np.asarray(test.pvalue).reshape(-1)[0])
    ci_h_raw = np.asarray(test.conf_int()).reshape(-1, 2)[0]
    ci_h = [float(ci_h_raw[0]), float(ci_h_raw[1])]

    return {
        "n_months": int(len(monthly)),
        "n_pre_months": n_pre,
        "n_post_months": n_post,
        "date_min": str(monthly["month_dt"].min().date()),
        "date_max": str(monthly["month_dt"].max().date()),
        "coefficients": params,
        "p_values": pvals,
        "confidence_intervals": cis,
        "hac_max_lag": int(max_hac_lag),
        "dw_stat": float(sm.stats.stattools.durbin_watson(base.resid)),
        "horizon_months": int(horizon),
        "effect_at_horizon": effect_h,
        "effect_at_horizon_p": p_h,
        "effect_at_horizon_ci": ci_h,
    }
