"""
Step 12: Segmented interrupted time-series (ITS) appendix analysis.

Purpose:
  Replace simple pre/post mean-difference tests with a stronger ITS design:
    y_t = b0 + b1*time + b2*post + b3*time_after + e_t

  - b2 estimates an immediate level change at the transition (time_after = 0
    in the first post month; the transition month counts as post).
  - b3 estimates a slope change after the transition.
  - Models are fit on monthly aggregated outcomes, weighted by article counts.
  - Inference uses HAC (Newey-West) robust standard errors, with automatic-lag
    HAC and AR(1)/GLSAR robustness fits reported alongside.

Controlled ITS:
  San Mateo county (Steve Wagstaffe; no prosecutor transition) serves as an
  untreated comparison series. For each transition and outcome, the monthly
  difference (treated mean - San Mateo mean) is passed through the same
  segmented design - the simplest comparative ITS - which nets out shocks
  common to Bay Area crime coverage.

Input:
  output/04_bias_scores.parquet

Outputs:
  output/12_segmented_its_results.json  (controlled fits under "controlled_its")
  output/12_segmented_its_table.csv
  output/12_segmented_its_controlled_table.csv
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from config import BIAS_PARQUET, OUTPUT_DIR
from segmented_its_utils import build_design, fit_segmented_its, prepare_monthly
from utils import setup_logging, load_parquet, logger, timer


ITS_JSON = OUTPUT_DIR / "12_segmented_its_results.json"
ITS_CSV = OUTPUT_DIR / "12_segmented_its_table.csv"
ITS_CONTROLLED_CSV = OUTPUT_DIR / "12_segmented_its_controlled_table.csv"
ITS_FIG = OUTPUT_DIR / "figures" / "18_segmented_its.png"
PAPER_FIG_DIR = Path(__file__).resolve().parent / "paper" / "figures"
PAPER_ITS_FIG = PAPER_FIG_DIR / "18_segmented_its.png"


@dataclass(frozen=True)
class TransitionSpec:
    label: str
    prosecutors: tuple[str, str]
    transition_date: pd.Timestamp


TRANSITIONS = [
    TransitionSpec(
        label="SF: Boudin to Jenkins",
        prosecutors=("Chesa Boudin", "Brooke Jenkins"),
        transition_date=pd.Timestamp("2022-07-08"),
    ),
    TransitionSpec(
        label="Alameda: O'Malley to Price",
        prosecutors=("Nancy O'Malley", "Pamela Price"),
        transition_date=pd.Timestamp("2023-01-03"),
    ),
]

OUTCOMES = {
    "composite_bias_score": "Composite",
    "score_stance": "B: Stance",
    "score_keywords": "C: Keywords",
    "score_aspect_sentiment": "A: Aspect sentiment",
    "score_doc_sentiment": "D: Document sentiment",
}

# San Mateo county: same media market, no prosecutor transition in-window.
CONTROL_PROSECUTORS = ("Steve Wagstaffe",)
CONTROL_LABEL = "San Mateo (Wagstaffe)"


def _build_design(
    monthly: pd.DataFrame,
    transition_date: pd.Timestamp,
) -> tuple[pd.Series, pd.DataFrame]:
    return build_design(monthly, transition_date)


def _prepare_monthly(
    df: pd.DataFrame,
    prosecutors: tuple[str, str],
    outcome_col: str,
) -> pd.DataFrame:
    return prepare_monthly(df, prosecutors, outcome_col)


def _fit_segmented_its(
    monthly: pd.DataFrame,
    transition_date: pd.Timestamp,
    max_hac_lag: int = 3,
    min_pre_months: int = 6,
    min_post_months: int = 6,
) -> dict:
    return fit_segmented_its(
        monthly=monthly,
        transition_date=transition_date,
        max_hac_lag=max_hac_lag,
        min_pre_months=min_pre_months,
        min_post_months=min_post_months,
        horizon_months=12,
    )


def _prepare_controlled_monthly(
    df: pd.DataFrame,
    treated_prosecutors: tuple[str, str],
    outcome_col: str,
) -> tuple[pd.DataFrame, int]:
    """Build the monthly treated-minus-control difference series.

    Both series are aggregated with the same ``prepare_monthly`` logic over
    the treated county's window; months where either series is missing are
    dropped (the caller logs the count). The difference is weighted by the
    treated county's monthly article count: the treated series carries the
    transition signal and, with far more articles per month than San Mateo,
    dominates the sampling variance of the difference; it also keeps the
    weighting comparable to the primary (uncontrolled) ITS.

    Returns the difference frame (columns month, month_dt, mean_outcome,
    n_articles - the schema ``fit_segmented_its`` expects) and the number of
    treated months dropped for lack of a control observation.
    """
    treated = _prepare_monthly(df, treated_prosecutors, outcome_col)
    control = prepare_monthly(df, list(CONTROL_PROSECUTORS), outcome_col)
    if treated.empty or control.empty:
        return pd.DataFrame(), 0

    treated_m = treated[["month", "mean_outcome", "n_articles"]].rename(
        columns={"mean_outcome": "treated_mean", "n_articles": "treated_n"}
    )
    control_m = control[["month", "mean_outcome"]].rename(
        columns={"mean_outcome": "control_mean"}
    )
    merged = treated_m.merge(control_m, on="month", how="inner")
    n_dropped = len(treated_m) - len(merged)

    merged["mean_outcome"] = merged["treated_mean"] - merged["control_mean"]
    merged["n_articles"] = merged["treated_n"]
    merged["month_dt"] = merged["month"].dt.to_timestamp()
    diff = (
        merged[["month", "month_dt", "mean_outcome", "n_articles"]]
        .sort_values("month")
        .reset_index(drop=True)
    )
    return diff, n_dropped


def _plot_segmented_its(df: pd.DataFrame) -> None:
    plot_outcomes = [
        ("composite_bias_score", "Composite"),
        ("score_stance", "Stance"),
        ("score_keywords", "Keywords"),
    ]
    n_rows = len(plot_outcomes)
    n_cols = len(TRANSITIONS)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(13, 10), sharex="col")
    if n_rows == 1 and n_cols == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = np.array([axes])
    elif n_cols == 1:
        axes = np.array([[ax] for ax in axes])

    for col_i, trans in enumerate(TRANSITIONS):
        for row_i, (outcome_col, outcome_label) in enumerate(plot_outcomes):
            ax = axes[row_i, col_i]
            monthly = _prepare_monthly(df, trans.prosecutors, outcome_col)

            if monthly.empty:
                ax.text(0.5, 0.5, "No data", ha="center", va="center")
                ax.axis("off")
                continue

            post_mask, X = _build_design(monthly, trans.transition_date)
            n_pre = int((~post_mask).sum())
            n_post = int(post_mask.sum())
            if n_pre < 6 or n_post < 6:
                ax.text(0.5, 0.5, "Insufficient pre/post months", ha="center", va="center")
                ax.axis("off")
                continue

            y = monthly["mean_outcome"].astype(float).values
            w = monthly["n_articles"].astype(float).values
            fit = sm.WLS(y, X, weights=w).fit()
            y_hat = fit.predict(X)
            x = monthly["month_dt"]

            marker_sizes = np.clip(np.sqrt(w) * 2.0, 10.0, 90.0)
            ax.scatter(
                x,
                y,
                s=marker_sizes,
                color="#7f8c8d",
                alpha=0.55,
                edgecolor="none",
                label="Observed monthly mean" if (row_i == 0 and col_i == 0) else None,
            )

            pre_idx = np.where(~post_mask.values)[0]
            post_idx = np.where(post_mask.values)[0]
            ax.plot(
                x.iloc[pre_idx],
                y_hat[pre_idx],
                color="#2c7fb8",
                linewidth=2.2,
                label="Fitted pre-period trend" if (row_i == 0 and col_i == 0) else None,
            )
            ax.plot(
                x.iloc[post_idx],
                y_hat[post_idx],
                color="#d95f0e",
                linewidth=2.2,
                label="Fitted post-period trend" if (row_i == 0 and col_i == 0) else None,
            )

            ax.axvline(
                trans.transition_date,
                color="black",
                linestyle="--",
                linewidth=1.2,
                alpha=0.8,
                label="Transition date" if (row_i == 0 and col_i == 0) else None,
            )
            ax.axhline(0, color="gray", linestyle=":", linewidth=1, alpha=0.6)

            ax.text(
                0.02,
                0.95,
                f"n months={len(monthly)}",
                transform=ax.transAxes,
                va="top",
                fontsize=8,
                color="#444444",
            )

            if col_i == 0:
                ax.set_ylabel(f"{outcome_label}\n(monthly mean)")
            if row_i == 0:
                trans_name = trans.label.replace(": ", "\n")
                ax.set_title(
                    f"{trans_name}\n({trans.transition_date.date()})",
                    fontsize=11,
                )

            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            ax.tick_params(axis="x", rotation=0)

    for ax in axes[-1, :]:
        ax.set_xlabel("Month")

    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9)

    fig.suptitle(
        "Segmented ITS Robustness: Monthly Outcomes and Fitted Pre/Post Trends",
        fontsize=13,
        y=0.98,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 0.965])

    ITS_FIG.parent.mkdir(parents=True, exist_ok=True)
    PAPER_FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(ITS_FIG, dpi=220, bbox_inches="tight")
    fig.savefig(PAPER_ITS_FIG, dpi=220, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved ITS figure: {ITS_FIG.name}")
    logger.info(f"Copied ITS figure to manuscript dir: {PAPER_ITS_FIG}")


def _to_row(transition_label: str, outcome_label: str, result: dict) -> dict:
    coefs = result["coefficients"]
    pvals = result["p_values"]
    return {
        "transition": transition_label,
        "outcome": outcome_label,
        "n_months": result["n_months"],
        "n_pre_months": result["n_pre_months"],
        "n_post_months": result["n_post_months"],
        "level_change_beta": coefs["post"],
        "level_change_p": pvals["post"],
        "slope_change_beta": coefs["time_after"],
        "slope_change_p": pvals["time_after"],
        "pre_trend_beta": coefs["time"],
        "pre_trend_p": pvals["time"],
        "effect_at_horizon": result["effect_at_horizon"],
        "effect_at_horizon_p": result["effect_at_horizon_p"],
        "horizon_months": result["horizon_months"],
    }


def main() -> None:
    setup_logging()

    with timer("Load Step 04 bias data"):
        df = load_parquet(BIAS_PARQUET)

    # Keep only rows used in analysis and ensure datetime dtype.
    df = df[df["primary_prosecutor"].notna()].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    logger.info(f"Rows with primary prosecutor: {len(df):,}")

    results: dict[str, dict] = {}
    table_rows: list[dict] = []

    with timer("Fit segmented ITS models"):
        for trans in TRANSITIONS:
            logger.info("")
            logger.info("=" * 70)
            logger.info(f"Transition: {trans.label} ({trans.transition_date.date()})")
            logger.info("=" * 70)
            trans_results: dict[str, dict] = {}

            for outcome_col, outcome_label in OUTCOMES.items():
                if outcome_col not in df.columns:
                    trans_results[outcome_col] = {"error": "missing_outcome_column"}
                    continue

                monthly = _prepare_monthly(df, trans.prosecutors, outcome_col)
                model_result = _fit_segmented_its(monthly, trans.transition_date)
                trans_results[outcome_col] = model_result

                if "error" in model_result:
                    logger.warning(
                        f"{outcome_label}: skipped ({model_result['error']})"
                    )
                    continue

                row = _to_row(trans.label, outcome_label, model_result)
                table_rows.append(row)

                logger.info(
                    f"{outcome_label}: level={row['level_change_beta']:.4f} "
                    f"(p={row['level_change_p']:.4g}), slope={row['slope_change_beta']:.4f} "
                    f"(p={row['slope_change_p']:.4g}), "
                    f"{row['horizon_months']}m effect={row['effect_at_horizon']:.4f} "
                    f"(p={row['effect_at_horizon_p']:.4g})"
                )

            results[trans.label] = trans_results

    controlled_results: dict[str, dict] = {}
    controlled_rows: list[dict] = []

    with timer("Fit controlled ITS models (San Mateo comparison)"):
        for trans in TRANSITIONS:
            logger.info("")
            logger.info("=" * 70)
            logger.info(
                f"Controlled ITS: {trans.label} vs {CONTROL_LABEL} "
                f"({trans.transition_date.date()})"
            )
            logger.info("=" * 70)
            trans_controlled: dict[str, dict] = {}

            for outcome_col, outcome_label in OUTCOMES.items():
                if outcome_col not in df.columns:
                    trans_controlled[outcome_col] = {
                        "error": "missing_outcome_column"
                    }
                    continue

                diff_monthly, n_dropped = _prepare_controlled_monthly(
                    df, trans.prosecutors, outcome_col
                )
                if n_dropped > 0:
                    logger.info(
                        f"{outcome_label}: dropped {n_dropped} treated "
                        f"month(s) without a {CONTROL_LABEL} observation"
                    )

                model_result = _fit_segmented_its(
                    diff_monthly, trans.transition_date
                )
                model_result["control_county"] = CONTROL_LABEL
                model_result["weighting"] = "treated_monthly_article_count"
                model_result["n_months_dropped_missing_control"] = n_dropped
                trans_controlled[outcome_col] = model_result

                if "error" in model_result:
                    logger.warning(
                        f"{outcome_label}: skipped ({model_result['error']})"
                    )
                    continue

                row = _to_row(trans.label, outcome_label, model_result)
                row["control_county"] = CONTROL_LABEL
                row["n_months_dropped_missing_control"] = n_dropped
                controlled_rows.append(row)

                logger.info(
                    f"{outcome_label}: level={row['level_change_beta']:.4f} "
                    f"(p={row['level_change_p']:.4g}), slope={row['slope_change_beta']:.4f} "
                    f"(p={row['slope_change_p']:.4g}), "
                    f"{row['horizon_months']}m effect={row['effect_at_horizon']:.4f} "
                    f"(p={row['effect_at_horizon_p']:.4g})"
                )

            controlled_results[trans.label] = trans_controlled

    results["controlled_its"] = controlled_results

    # Benjamini-Hochberg adjustment across the primary ITS table's test family
    # (2 transitions x 5 outcomes x {level, slope, horizon} p-values). Added as
    # extra columns; existing keys/columns untouched.
    if table_rows:
        p_cols = ["level_change_p", "slope_change_p", "effect_at_horizon_p"]
        flat = [
            (i, col, row[col])
            for i, row in enumerate(table_rows)
            for col in p_cols
            if row.get(col) is not None and not np.isnan(row[col])
        ]
        pvals = np.array([p for _, _, p in flat])
        order = np.argsort(pvals)
        ranked = pvals[order] * len(pvals) / (np.arange(len(pvals)) + 1)
        adj = np.minimum.accumulate(ranked[::-1])[::-1]
        adjusted = np.empty(len(pvals))
        adjusted[order] = np.clip(adj, 0, 1)
        for (i, col, _), p_adj in zip(flat, adjusted):
            table_rows[i][f"{col}_bh"] = float(p_adj)
        results["multiplicity_note"] = (
            "level/slope/horizon p-values BH-adjusted as one family of "
            f"{len(pvals)} tests; adjusted values in *_bh columns of the CSV"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ITS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved ITS JSON: {ITS_JSON.name}")

    if table_rows:
        out_df = pd.DataFrame(table_rows).sort_values(["transition", "outcome"])
        out_df.to_csv(ITS_CSV, index=False)
        logger.info(f"Saved ITS table: {ITS_CSV.name}")
    else:
        logger.warning("No ITS rows produced; CSV not written.")

    if controlled_rows:
        controlled_df = pd.DataFrame(controlled_rows).sort_values(
            ["transition", "outcome"]
        )
        controlled_df.to_csv(ITS_CONTROLLED_CSV, index=False)
        logger.info(f"Saved controlled ITS table: {ITS_CONTROLLED_CSV.name}")
    else:
        logger.warning("No controlled ITS rows produced; CSV not written.")

    with timer("Render segmented ITS figure"):
        _plot_segmented_its(df)

    logger.info("Done.")


if __name__ == "__main__":
    main()
