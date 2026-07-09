"""Shared segmented ITS helpers for temporal analyses.

This module centralizes the segmented interrupted time-series logic used by
Step 06 (main stats) and Step 12 (appendix robustness) so their estimates
cannot drift due to duplicated implementations.

Conventions:
  - Monthly classification: a month is POST if its calendar month contains or
    follows the transition date (i.e., the transition month counts as post).
    This mirrors the article-level convention used elsewhere in the pipeline
    (article is post if ``date >= transition_date``), since the majority of
    each transition month's days fall after the mid-month transitions studied
    here (SF 2022-07-08, Alameda 2023-01-03).
  - Time index: ``time`` is calendar months elapsed since the first observed
    month (period ordinals), NOT row position, so calendar gaps (months with
    zero articles, which are dropped) do not distort the trend.
  - ``time_after`` is 0 in the first post month (standard ITS coding), so the
    ``post`` coefficient is the immediate level change at the transition.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import statsmodels.api as sm

logger = logging.getLogger(__name__)


def build_design(
    monthly: pd.DataFrame,
    transition_date: pd.Timestamp,
) -> tuple[pd.Series, pd.DataFrame]:
    """Construct segmented ITS regressors for monthly data.

    A month is classified as post if its month period is >= the transition
    date's month period, so the transition month itself counts as post (see
    module docstring). ``time`` counts calendar months since the first
    observed month, and ``time_after`` counts calendar months since the first
    post month, starting at 0 (standard ITS coding: the ``post`` coefficient
    is the immediate level change in the transition month).

    If there are no post months, ``time_after`` is all zeros and the caller's
    pre/post sample-size guard is expected to reject the fit.
    """
    if "month" in monthly.columns:
        periods = monthly["month"]
    else:
        periods = monthly["month_dt"].dt.to_period("M")

    transition_period = pd.Timestamp(transition_date).to_period("M")
    post_mask = periods >= transition_period

    # Calendar-based time index (month ordinals), robust to missing months.
    ordinals = periods.map(lambda p: p.ordinal).to_numpy(dtype=float)
    t = ordinals - ordinals[0]
    post = post_mask.to_numpy(dtype=float)

    post_positions = np.flatnonzero(post_mask.to_numpy())
    if post_positions.size:
        t_first_post = t[post_positions[0]]
        time_after = np.where(post > 0, t - t_first_post, 0.0)
    else:
        time_after = np.zeros_like(t)

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
    """Aggregate article-level data to monthly outcome means.

    Calendar months with zero articles between the first and last observed
    month are dropped (they have no outcome mean to fit and would carry zero
    weight); a note is logged with the count. The ITS design remains valid
    because ``build_design`` indexes time by calendar month, not row position.
    """
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

    full_range = pd.period_range(
        monthly["month"].min(), monthly["month"].max(), freq="M"
    )
    n_missing = len(full_range) - len(monthly)
    if n_missing > 0:
        logger.info(
            "prepare_monthly(%s): dropped %d calendar month(s) with zero "
            "articles between %s and %s; time index stays calendar-based.",
            outcome_col,
            n_missing,
            full_range[0],
            full_range[-1],
        )

    monthly["month_dt"] = monthly["month"].dt.to_timestamp()
    return monthly.reset_index(drop=True)


def _param_dict(names: list[str], values: np.ndarray) -> dict[str, float]:
    return {k: float(v) for k, v in zip(names, values)}


def _ci_dict(names: list[str], ci: np.ndarray) -> dict[str, list[float]]:
    ci = np.asarray(ci)
    return {k: [float(ci[i, 0]), float(ci[i, 1])] for i, k in enumerate(names)}


def _horizon_test(results, horizon: int) -> tuple[float, float, list[float]]:
    """Effect ``horizon`` months after the transition month.

    With ``time_after`` = 0 in the first post month, the effect at horizon h
    is ``post + h * time_after`` (immediate level change plus h months of
    accumulated slope change).
    """
    L = np.array([0.0, 0.0, 1.0, float(horizon)])
    test = results.t_test(L)
    effect = float(np.asarray(test.effect).reshape(-1)[0])
    p = float(np.asarray(test.pvalue).reshape(-1)[0])
    ci = np.asarray(test.conf_int()).reshape(-1, 2)[0]
    return effect, p, [float(ci[0]), float(ci[1])]


def fit_segmented_its(
    monthly: pd.DataFrame,
    transition_date: pd.Timestamp,
    max_hac_lag: int = 3,
    min_pre_months: int = 6,
    min_post_months: int = 6,
    horizon_months: int = 12,
) -> dict:
    """Fit weighted segmented ITS with HAC-robust inference.

    Primary fit: WLS (weights = monthly article counts) with Newey-West HAC
    standard errors at ``max_hac_lag`` (existing keys, unchanged). Two
    robustness sets are returned alongside it:

    - ``*_hac_auto``: same WLS coefficients with HAC SEs at the data-driven
      Newey-West lag floor(4 * (n / 100) ** (2 / 9)).
    - ``*_ar1``: Prais-Winsten-style AR(1) fit via ``sm.GLSAR`` with
      iterative rho estimation (unweighted, since GLSAR does not support
      observation weights), addressing the severe positive autocorrelation
      (Durbin-Watson ~0.8-0.9) that HAC lags may not fully absorb.

    The horizon effect is ``post + horizon * time_after`` where ``time_after``
    is 0 in the transition month, so ``horizon_months=12`` is the effect 12
    calendar months after the transition month. The horizon is capped at the
    last observed post month (``n_post - 1`` months after the first).
    """
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
    n_obs = len(monthly)
    names = list(X.columns)

    base = sm.WLS(y, X, weights=w).fit()
    robust = base.get_robustcov_results(cov_type="HAC", maxlags=max_hac_lag)

    params = _param_dict(names, robust.params)
    pvals = _param_dict(names, robust.pvalues)
    cis = _ci_dict(names, robust.conf_int())
    ses = _param_dict(names, robust.bse)

    # time_after = 0 in the transition month, so the last observed post month
    # is (n_post - 1) months after it; cap the horizon there.
    horizon = min(int(horizon_months), n_post - 1)
    effect_h, p_h, ci_h = _horizon_test(robust, horizon)

    # Data-driven Newey-West lag (Newey-West 1994 rule of thumb).
    auto_lag = int(np.floor(4.0 * (n_obs / 100.0) ** (2.0 / 9.0)))
    robust_auto = base.get_robustcov_results(cov_type="HAC", maxlags=auto_lag)
    _, p_h_auto, _ = _horizon_test(robust_auto, horizon)

    result = {
        "n_months": n_obs,
        "n_pre_months": n_pre,
        "n_post_months": n_post,
        "date_min": str(monthly["month_dt"].min().date()),
        "date_max": str(monthly["month_dt"].max().date()),
        "coefficients": params,
        "p_values": pvals,
        "confidence_intervals": cis,
        "std_errors": ses,
        "hac_max_lag": int(max_hac_lag),
        "dw_stat": float(sm.stats.stattools.durbin_watson(base.resid)),
        "horizon_months": int(horizon),
        "effect_at_horizon": effect_h,
        "effect_at_horizon_p": p_h,
        "effect_at_horizon_ci": ci_h,
        "hac_auto_lag": auto_lag,
        "std_errors_hac_auto": _param_dict(names, robust_auto.bse),
        "p_values_hac_auto": _param_dict(names, robust_auto.pvalues),
        "effect_at_horizon_p_hac_auto": p_h_auto,
    }

    # AR(1) (Prais-Winsten-style GLSAR) robustness fit.
    try:
        ar_model = sm.GLSAR(y, X, rho=1)
        ar_fit = ar_model.iterative_fit(maxiter=50)
        rho = float(np.atleast_1d(ar_model.rho)[0])
        effect_h_ar1, p_h_ar1, ci_h_ar1 = _horizon_test(ar_fit, horizon)
        result.update(
            {
                "ar1_rho": rho,
                "coefficients_ar1": _param_dict(names, ar_fit.params),
                "std_errors_ar1": _param_dict(names, ar_fit.bse),
                "p_values_ar1": _param_dict(names, ar_fit.pvalues),
                "confidence_intervals_ar1": _ci_dict(names, ar_fit.conf_int()),
                # DW on whitened residuals: ~2 means the AR(1) transform
                # removed the serial correlation.
                "dw_stat_ar1": float(
                    sm.stats.stattools.durbin_watson(ar_fit.wresid)
                ),
                "effect_at_horizon_ar1": effect_h_ar1,
                "effect_at_horizon_ar1_p": p_h_ar1,
                "effect_at_horizon_ar1_ci": ci_h_ar1,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("AR(1) robustness fit failed: %s", exc)
        result["ar1_error"] = str(exc)

    return result
