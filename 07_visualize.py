"""
Step 7: Publication-ready figures.

Figures:
  1. Violin + box plots of composite bias by prosecutor type
  2. Per-prosecutor comparison with 95% CIs
  3. Same-county paired comparison (Boudin/Jenkins, O'Malley/Price)
  4. Time series of monthly bias with tenure bands
  5. Framing heatmap: prosecutor × frame
  6. Effect size forest plot with bootstrap CIs
  7. Anti-prosecutor theme prevalence by type
  8. Source type distribution (Appendix A, from Step 08)
  9. Bias indicator distribution (Appendix B, from Step 09)
 10. Method comparison scatter: sentiment vs. stance divergence
 11. Regression coefficient plot with 95% CIs
 12. Theme attribution per-theme differential (Step 10)
 13. Theme attribution per-prosecutor heatmap (Step 10)
 14. Theme attribution method agreement by type (Step 10)

Input:  output/04_bias_scores.parquet, output/05_frames.parquet,
        output/06_stats_results.json, output/08_extraction_stats.json,
        output/09_bias_stats.json, output/10_theme_stats.json,
        output/10_theme_attribution.parquet
Output: output/figures/*.png
"""

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import ttest_ind, sem

from config import (
    BIAS_PARQUET,
    FRAMES_PARQUET,
    STATS_JSON,
    FIGURES_DIR,
    PROSECUTORS,
    EXTRACTION_STATS_JSON,
    BIAS_STATS_JSON,
    REGRESSION_CSV,
    THEME_ATTR_PARQUET,
    THEME_STATS_JSON,
)
from utils import setup_logging, load_parquet, timer, logger


# ── Style setup ───────────────────────────────────────────────────────────

def setup_style():
    """Set consistent matplotlib style for all figures."""
    plt.rcParams.update({
        "figure.figsize": (10, 6),
        "figure.dpi": 150,
        "font.size": 11,
        "font.family": "sans-serif",
        "axes.titlesize": 13,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.3,
    })
    sns.set_palette("Set2")


PROG_COLOR = "#e74c3c"  # red for progressive
TRAD_COLOR = "#3498db"  # blue for traditional
TYPE_COLORS = {"Progressive": PROG_COLOR, "Traditional": TRAD_COLOR}


# ── Figure 1: Violin + box by prosecutor type ────────────────────────────

def fig1_violin_by_type(df: pd.DataFrame):
    """Violin + box plots of composite bias score by prosecutor type."""
    fig, ax = plt.subplots(figsize=(8, 6))

    plot_data = df[df["prosecutor_type"].notna() & df["composite_bias_score"].notna()]

    parts = ax.violinplot(
        [
            plot_data.loc[plot_data["prosecutor_type"] == "Progressive", "composite_bias_score"].values,
            plot_data.loc[plot_data["prosecutor_type"] == "Traditional", "composite_bias_score"].values,
        ],
        positions=[1, 2],
        showmedians=True,
        showextrema=False,
    )

    for i, pc in enumerate(parts["bodies"]):
        color = PROG_COLOR if i == 0 else TRAD_COLOR
        pc.set_facecolor(color)
        pc.set_alpha(0.4)
    parts["cmedians"].set_color("black")

    # Add box plots on top
    bp = ax.boxplot(
        [
            plot_data.loc[plot_data["prosecutor_type"] == "Progressive", "composite_bias_score"].values,
            plot_data.loc[plot_data["prosecutor_type"] == "Traditional", "composite_bias_score"].values,
        ],
        positions=[1, 2],
        widths=0.15,
        patch_artist=True,
        showfliers=False,
    )
    for i, box in enumerate(bp["boxes"]):
        color = PROG_COLOR if i == 0 else TRAD_COLOR
        box.set_facecolor(color)
        box.set_alpha(0.7)

    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Progressive", "Traditional"])
    ax.set_ylabel("Composite Bias Score")
    ax.set_title("Bias Score Distribution by Prosecutor Type")
    ax.axhline(0, color="gray", linestyle="--", alpha=0.5)

    # Add n labels
    for i, ptype in enumerate(["Progressive", "Traditional"], 1):
        n = (plot_data["prosecutor_type"] == ptype).sum()
        ax.text(i, ax.get_ylim()[0], f"n={n:,}", ha="center", va="top", fontsize=9)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "01_violin_by_type.png")
    plt.close(fig)
    logger.info("Saved 01_violin_by_type.png")


# ── Figure 2: Per-prosecutor comparison with CIs ─────────────────────────

def fig2_per_prosecutor(df: pd.DataFrame):
    """Per-prosecutor mean bias score with 95% CIs."""
    fig, ax = plt.subplots(figsize=(10, 6))

    prosecutors_ordered = df.groupby("primary_prosecutor")["composite_bias_score"].mean().sort_values()

    names = []
    means = []
    cis = []
    colors = []

    for name in prosecutors_ordered.index:
        if pd.isna(name):
            continue
        vals = df.loc[df["primary_prosecutor"] == name, "composite_bias_score"].dropna()
        if len(vals) < 5:
            continue

        p = next((p for p in PROSECUTORS if p.name == name), None)
        ideology = p.ideology if p else "Unknown"

        names.append(f"{name}\n({ideology})")
        means.append(vals.mean())
        cis.append(1.96 * sem(vals))
        colors.append(TYPE_COLORS.get(ideology, "gray"))

    y_pos = range(len(names))
    ax.barh(y_pos, means, xerr=cis, color=colors, alpha=0.7, edgecolor="black", linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.set_xlabel("Mean Composite Bias Score (95% CI)")
    ax.set_title("Bias Score by Prosecutor")
    ax.axvline(0, color="gray", linestyle="--", alpha=0.5)

    # Add n labels
    for i, name_full in enumerate(names):
        short_name = name_full.split("\n")[0]
        n = (df["primary_prosecutor"] == short_name).sum()
        ax.text(means[i], i, f" n={n:,}", va="center", fontsize=8)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "02_per_prosecutor.png")
    plt.close(fig)
    logger.info("Saved 02_per_prosecutor.png")


# ── Figure 3: Same-county paired comparison ───────────────────────────────

def fig3_paired_county(df: pd.DataFrame):
    """Side-by-side comparison for same-county pairs."""
    pairs = [
        ("Chesa Boudin", "Brooke Jenkins", "San Francisco"),
        ("Pamela Price", "Nancy O'Malley", "Alameda"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)

    for ax, (prog, trad, county) in zip(axes, pairs):
        g1 = df.loc[df["primary_prosecutor"] == prog, "composite_bias_score"].dropna()
        g2 = df.loc[df["primary_prosecutor"] == trad, "composite_bias_score"].dropna()

        if len(g1) < 5 or len(g2) < 5:
            ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(county)
            continue

        bp = ax.boxplot(
            [g1.values, g2.values],
            tick_labels=[f"{prog}\n(Progressive)", f"{trad}\n(Traditional)"],
            patch_artist=True,
            widths=0.5,
        )
        bp["boxes"][0].set_facecolor(PROG_COLOR)
        bp["boxes"][0].set_alpha(0.5)
        bp["boxes"][1].set_facecolor(TRAD_COLOR)
        bp["boxes"][1].set_alpha(0.5)

        # Add means as diamonds
        ax.scatter([1, 2], [g1.mean(), g2.mean()], marker="D", color="black",
                   s=50, zorder=5, label="Mean")

        t_stat, p_val = ttest_ind(g1, g2, equal_var=False)
        ax.set_title(f"{county} County\n(p={p_val:.4f})")
        ax.axhline(0, color="gray", linestyle="--", alpha=0.5)

        ax.text(0.5, 0.02, f"n={len(g1):,} vs n={len(g2):,}",
                ha="center", transform=ax.transAxes, fontsize=9)

    axes[0].set_ylabel("Composite Bias Score")
    fig.suptitle("Same-County Paired Comparisons", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "03_paired_county.png", bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved 03_paired_county.png")


# ── Figure 4: Time series with tenure bands ──────────────────────────────

def fig4_time_series(df: pd.DataFrame):
    """Monthly average bias over time with prosecutor tenure bands.

    Improvements over v1:
    - X-axis clipped to actual data range (not prosecutor tenure dates)
    - Tenure bands clipped to data range
    - Year-only x-axis labels for cleaner presentation
    - Light gray bars showing monthly article counts (secondary y-axis)
    - Months with <5 articles shown as open circles (flagged as sparse)
    """
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))

    counties = [
        ("San Francisco", ["Chesa Boudin", "Brooke Jenkins"]),
        ("Alameda", ["Nancy O'Malley", "Pamela Price"]),
    ]

    # Determine global data range across both counties
    all_dates = df[df["primary_prosecutor"].isin(
        [p for _, procs in counties for p in procs]
    )]["date"]
    global_min = all_dates.min() - pd.Timedelta(days=30)
    global_max = all_dates.max() + pd.Timedelta(days=30)

    for ax, (county, prosecutors) in zip(axes, counties):
        subset = df[df["primary_prosecutor"].isin(prosecutors)].copy()
        if len(subset) == 0:
            continue

        subset["month"] = subset["date"].dt.to_period("M")
        monthly = subset.groupby(["month", "prosecutor_type"]).agg(
            mean_bias=("composite_bias_score", "mean"),
            n=("composite_bias_score", "count"),
        ).reset_index()
        monthly["month_dt"] = monthly["month"].dt.to_timestamp()

        # Secondary axis for article counts
        ax2 = ax.twinx()
        monthly_total = subset.groupby("month").size().reset_index(name="n_total")
        monthly_total["month_dt"] = monthly_total["month"].dt.to_timestamp()
        ax2.bar(monthly_total["month_dt"], monthly_total["n_total"],
                width=25, color="gray", alpha=0.15, zorder=1)
        ax2.set_ylabel("Articles / month", color="gray", fontsize=9)
        ax2.tick_params(axis="y", labelcolor="gray", labelsize=8)
        ax2.set_ylim(0, monthly_total["n_total"].max() * 3)  # keep bars small

        # Plot bias lines
        min_articles = 5
        for ptype, color in TYPE_COLORS.items():
            data = monthly[monthly["prosecutor_type"] == ptype].copy()
            if len(data) == 0:
                continue
            dense = data[data["n"] >= min_articles].copy()
            sparse = data[data["n"] < min_articles]
            ax.plot(dense["month_dt"], dense["mean_bias"], "o-",
                    color=color, markersize=4, label=ptype, alpha=0.4,
                    linewidth=1.0, zorder=3)
            if len(sparse) > 0:
                ax.scatter(sparse["month_dt"], sparse["mean_bias"],
                           color=color, marker="o", s=20, facecolors="none",
                           linewidths=1, alpha=0.5, zorder=3)
            # Coverage-weighted 3-month rolling average
            if len(dense) >= 3:
                dense = dense.sort_values("month_dt").copy()
                weights = dense["n"].values.astype(float)
                vals = dense["mean_bias"].values
                # Rolling window of 3 months, weighted by article count
                wt_avg = []
                wt_dates = []
                for k in range(len(vals)):
                    lo = max(0, k - 1)
                    hi = min(len(vals), k + 2)
                    w = weights[lo:hi]
                    v = vals[lo:hi]
                    wt_avg.append(np.average(v, weights=w) if w.sum() > 0 else v[k - lo])
                    wt_dates.append(dense["month_dt"].iloc[k])
                ax.plot(wt_dates, wt_avg, "-", color=color, linewidth=2.5,
                        alpha=0.9, zorder=4, label=f"{ptype} (weighted trend)")

        # Add tenure bands, clipped to data range
        for p_name in prosecutors:
            p = next((pp for pp in PROSECUTORS if pp.name == p_name), None)
            if p is None:
                continue
            start = max(pd.Timestamp(p.start_date), global_min)
            end_raw = pd.Timestamp(p.end_date) if p.end_date else pd.Timestamp("2024-12-31")
            end = min(end_raw, global_max)
            color = TYPE_COLORS.get(p.ideology, "gray")
            ax.axvspan(start, end, alpha=0.06, color=color, zorder=0)
            # Label the band at top
            mid = start + (end - start) / 2
            ax.text(mid, 1.0, p.name.split()[-1],
                    ha="center", va="top", fontsize=9, style="italic",
                    transform=ax.get_xaxis_transform(), color=color, alpha=0.7)

        ax.set_xlim(global_min, global_max)
        ax.set_title(f"{county} County", fontsize=12, fontweight="bold")
        ax.set_ylabel("Mean Monthly Bias Score")
        ax.axhline(0, color="gray", linestyle="--", alpha=0.4, linewidth=0.8)
        ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))
        ax.tick_params(axis="x", rotation=0)

    axes[-1].set_xlabel("Year")
    fig.suptitle("Monthly Bias Score Over Time", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "04_time_series.png", dpi=200)
    plt.close(fig)
    logger.info("Saved 04_time_series.png")


# ── Figure 5: Framing heatmap ────────────────────────────────────────────

def fig5_framing_heatmap(df: pd.DataFrame):
    """Heatmap of frame scores by prosecutor."""
    frame_cols = [c for c in df.columns if c.startswith("frame_") and c != "dominant_frame"]
    if not frame_cols:
        logger.warning("No frame columns — skipping framing heatmap")
        return

    # Average frame score per prosecutor
    pivot = df.groupby("primary_prosecutor")[frame_cols].mean()
    pivot.columns = [c.replace("frame_", "").replace("_", " ").title() for c in pivot.columns]

    # Only include prosecutors with enough data
    counts = df["primary_prosecutor"].value_counts()
    valid = counts[counts >= 10].index
    pivot = pivot.loc[pivot.index.isin(valid)]

    if pivot.empty:
        logger.warning("Insufficient data for framing heatmap")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".2f",
        cmap="RdYlBu_r",
        center=0.5,
        ax=ax,
        linewidths=0.5,
    )
    ax.set_title("Average Frame Score by Prosecutor")
    ax.set_ylabel("")

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "05_framing_heatmap.png")
    plt.close(fig)
    logger.info("Saved 05_framing_heatmap.png")


# ── Figure 6: Effect size forest plot ─────────────────────────────────────

def _bootstrap_cohens_d(group1, group2, n_boot=5000, seed=42):
    """Bootstrap 95% CI for Cohen's d."""
    rng = np.random.default_rng(seed)
    boot_ds = []
    for _ in range(n_boot):
        s1 = rng.choice(group1, size=len(group1), replace=True)
        s2 = rng.choice(group2, size=len(group2), replace=True)
        n1, n2 = len(s1), len(s2)
        var1, var2 = np.var(s1, ddof=1), np.var(s2, ddof=1)
        pooled = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
        d = (np.mean(s1) - np.mean(s2)) / pooled if pooled > 0 else 0.0
        boot_ds.append(d)
    return float(np.percentile(boot_ds, 2.5)), float(np.percentile(boot_ds, 97.5))


def fig6_forest_plot(stats_path, df=None):
    """Forest plot of effect sizes across analyses with bootstrap CIs.

    Includes overall, paired county, per-method, and theme attribution results.
    Uses distinct color scheme and prints effect size labels.
    """
    if not stats_path.exists():
        logger.warning("Stats JSON not found — skipping forest plot")
        return

    with open(stats_path) as f:
        results = json.load(f)

    labels = []
    effect_sizes = []
    ci_lowers = []
    ci_uppers = []
    categories = []  # for color coding

    # Overall comparison
    gc = results.get("group_comparison", {})
    if gc and "cohens_d" in gc:
        labels.append("Overall (Prog vs Trad)")
        effect_sizes.append(gc["cohens_d"])
        categories.append("overall")
        # Compute bootstrap CI for d if df available
        if df is not None and "composite_bias_score" in df.columns:
            prog = df.loc[df["prosecutor_type"] == "Progressive", "composite_bias_score"].dropna().values
            trad = df.loc[df["prosecutor_type"] == "Traditional", "composite_bias_score"].dropna().values
            lo, hi = _bootstrap_cohens_d(prog, trad, n_boot=5000)
            ci_lowers.append(lo)
            ci_uppers.append(hi)
        else:
            ci_lowers.append(gc["cohens_d"] - 0.05)
            ci_uppers.append(gc["cohens_d"] + 0.05)

    # Paired comparisons
    paired = results.get("paired_county", {})
    for key, val in paired.items():
        if "cohens_d" not in val:
            continue
        short_label = f"{val.get('county', '')}: {val.get('progressive', '').split()[-1]} vs {val.get('traditional', '').split()[-1]}"
        labels.append(short_label)
        effect_sizes.append(val["cohens_d"])
        categories.append("paired")
        # Compute bootstrap CI for paired
        if df is not None and "composite_bias_score" in df.columns:
            p_name = val.get("progressive", "")
            t_name = val.get("traditional", "")
            prog = df.loc[df["primary_prosecutor"] == p_name, "composite_bias_score"].dropna().values
            trad = df.loc[df["primary_prosecutor"] == t_name, "composite_bias_score"].dropna().values
            if len(prog) > 10 and len(trad) > 10:
                lo, hi = _bootstrap_cohens_d(prog, trad, n_boot=5000)
                ci_lowers.append(lo)
                ci_uppers.append(hi)
            else:
                ci_lowers.append(val["cohens_d"] - 0.15)
                ci_uppers.append(val["cohens_d"] + 0.15)
        else:
            ci_lowers.append(val["cohens_d"] - 0.15)
            ci_uppers.append(val["cohens_d"] + 0.15)

    # Per-method — compute real bootstrap CIs if df is available
    method_labels = {
        "score_aspect_sentiment": "A: Aspect Sentiment",
        "score_stance": "B: Stance Classification",
        "score_keywords": "C: Keyword Analysis",
        "score_doc_sentiment": "D: Document Sentiment",
    }
    per_method = results.get("per_method", {})
    for method, val in per_method.items():
        if "cohens_d" not in val:
            continue
        labels.append(method_labels.get(method, method.replace("score_", "")))
        effect_sizes.append(val["cohens_d"])
        if df is not None and method in df.columns:
            prog = df.loc[df["prosecutor_type"] == "Progressive", method].dropna().values
            trad = df.loc[df["prosecutor_type"] == "Traditional", method].dropna().values
            lo, hi = _bootstrap_cohens_d(prog, trad, n_boot=5000)
            ci_lowers.append(lo)
            ci_uppers.append(hi)
        else:
            ci_lowers.append(val["cohens_d"] - 0.1)
            ci_uppers.append(val["cohens_d"] + 0.1)
        categories.append("method")

    # Theme attribution (from 10_theme_stats.json)
    # Note: theme d is positive (progressive > traditional in theme score),
    # but we negate it for the forest plot so all effects share the same
    # sign convention: negative = more negative coverage toward progressive.
    if THEME_STATS_JSON.exists():
        with open(THEME_STATS_JSON) as f:
            theme_stats = json.load(f)
        theme_overall = theme_stats.get("overall", {})
        if "cohens_d" in theme_overall:
            labels.append("Theme Attribution")
            raw_d = theme_overall["cohens_d"]
            effect_sizes.append(-raw_d)  # negate: higher themes = more negative coverage
            categories.append("theme")
            if df is not None and "ta_composite_score" in df.columns:
                prog = df.loc[df["prosecutor_type"] == "Progressive", "ta_composite_score"].dropna().values
                trad = df.loc[df["prosecutor_type"] == "Traditional", "ta_composite_score"].dropna().values
                lo, hi = _bootstrap_cohens_d(prog, trad, n_boot=5000)
                ci_lowers.append(-hi)   # negate and swap
                ci_uppers.append(-lo)
            else:
                ci_lowers.append(-raw_d - 0.05)
                ci_uppers.append(-raw_d + 0.05)

    if not labels:
        logger.warning("No effect sizes to plot")
        return

    fig, ax = plt.subplots(figsize=(10, max(5, len(labels) * 0.7)))

    y_pos = list(range(len(labels)))
    errors = [[abs(es - lo) for es, lo in zip(effect_sizes, ci_lowers)],
              [abs(hi - es) for es, hi in zip(effect_sizes, ci_uppers)]]

    # Improved color scheme — distinct, accessible
    cat_colors = {
        "overall": "#1a1a2e",   # dark navy
        "paired": "#e63946",    # red
        "method": "#457b9d",    # steel blue
        "theme": "#2a9d8f",     # teal-green
    }
    marker_colors = [cat_colors.get(c, "black") for c in categories]

    for i, (es, lo_err, hi_err, mc) in enumerate(
        zip(effect_sizes, errors[0], errors[1], marker_colors)
    ):
        ms = 10 if categories[i] == "theme" else 8  # bigger marker for theme
        ax.errorbar(es, i, xerr=[[lo_err], [hi_err]], fmt="o", color=mc,
                     ecolor=mc, elinewidth=1.5, capsize=5, markersize=ms, alpha=0.9)
        # Add effect size label
        ax.text(es + hi_err + 0.02, i, f"d = {es:.2f}",
                va="center", fontsize=9, color=mc, fontweight="bold")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=10)
    ax.axvline(0, color="gray", linestyle="--", alpha=0.7, linewidth=1.2)
    ax.axvspan(-0.2, 0.2, alpha=0.06, color="green", label="Negligible (|d| < 0.2)")

    # Add horizontal separator lines between sections
    section_breaks = []
    prev_cat = categories[0] if categories else None
    for i, cat in enumerate(categories):
        if cat != prev_cat:
            section_breaks.append(i - 0.5)
            prev_cat = cat
    for brk in section_breaks:
        ax.axhline(brk, color="gray", linestyle=":", alpha=0.4)

    ax.set_xlabel("Cohen's d (negative = more negative toward progressive)", fontsize=11)
    ax.set_title("Effect Size Forest Plot with 95% Bootstrap CIs", fontsize=13,
                 fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    ax.invert_yaxis()

    # Give some room for the d labels on the right
    x_max = max(abs(es) + hi_err for es, hi_err in zip(effect_sizes, errors[1])) + 0.15
    x_min = min(es - lo_err for es, lo_err in zip(effect_sizes, errors[0])) - 0.05
    ax.set_xlim(x_min, x_max)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "06_forest_plot.png", dpi=200)
    plt.close(fig)
    logger.info("Saved 06_forest_plot.png")


# ── Figure 7: Theme prevalence by type ────────────────────────────────────

def fig7_theme_prevalence(df: pd.DataFrame):
    """Bar chart of theme prevalence by prosecutor type."""
    theme_cols = [c for c in df.columns if c.startswith("theme_")]
    if not theme_cols:
        logger.warning("No theme columns — skipping theme prevalence plot")
        return

    # Calculate prevalence by type
    prog = df[df["prosecutor_type"] == "Progressive"]
    trad = df[df["prosecutor_type"] == "Traditional"]

    themes = []
    prog_pcts = []
    trad_pcts = []
    for tc in theme_cols:
        theme_name = tc.replace("theme_", "").replace("_", " ").title()
        themes.append(theme_name)
        prog_pcts.append(100 * prog[tc].mean() if len(prog) > 0 else 0)
        trad_pcts.append(100 * trad[tc].mean() if len(trad) > 0 else 0)

    # Sort by difference
    diffs = [p - t for p, t in zip(prog_pcts, trad_pcts)]
    order = np.argsort(diffs)

    fig, ax = plt.subplots(figsize=(10, max(4, len(themes) * 0.5)))

    y = np.arange(len(themes))
    height = 0.35

    ax.barh(y - height / 2, [prog_pcts[i] for i in order], height,
            label="Progressive", color=PROG_COLOR, alpha=0.7)
    ax.barh(y + height / 2, [trad_pcts[i] for i in order], height,
            label="Traditional", color=TRAD_COLOR, alpha=0.7)

    ax.set_yticks(y)
    ax.set_yticklabels([themes[i] for i in order])
    ax.set_xlabel("Prevalence (%)")
    ax.set_title("Anti-Prosecutor Theme Prevalence by Type")
    ax.legend()

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "07_theme_prevalence.png")
    plt.close(fig)
    logger.info("Saved 07_theme_prevalence.png")


# ── Figure 8: Source type distribution (Appendix A) ──────────────────────

def fig8_source_type_distribution(extraction_stats_path):
    """Grouped bar chart of source types by prosecutor ideology from Step 08."""
    if not extraction_stats_path.exists():
        logger.warning("Extraction stats not found — skipping source type figure")
        return

    with open(extraction_stats_path) as f:
        stats = json.load(f)

    src_dist = stats.get("source_type_distribution", {})
    if not src_dist or "Progressive" not in src_dist:
        logger.warning("No source type distribution — skipping")
        return

    prog = src_dist["Progressive"]
    trad = src_dist["Traditional"]

    # Exclude 'total'
    source_types = [k for k in prog.keys() if k != "total"]
    prog_counts = [prog.get(s, 0) for s in source_types]
    trad_counts = [trad.get(s, 0) for s in source_types]

    # Normalize to proportions
    prog_total = sum(prog_counts)
    trad_total = sum(trad_counts)
    prog_pcts = [100 * c / prog_total if prog_total > 0 else 0 for c in prog_counts]
    trad_pcts = [100 * c / trad_total if trad_total > 0 else 0 for c in trad_counts]

    # Sort by absolute difference
    diffs = [abs(p - t) for p, t in zip(prog_pcts, trad_pcts)]
    order = np.argsort(diffs)[::-1]

    labels = [source_types[i].replace("_", " ").title() for i in order]

    fig, ax = plt.subplots(figsize=(10, 6))
    y = np.arange(len(labels))
    height = 0.35

    bars_prog = ax.barh(y - height / 2, [prog_pcts[i] for i in order], height,
                         label=f"Progressive (n={prog_total})", color=PROG_COLOR, alpha=0.7)
    bars_trad = ax.barh(y + height / 2, [trad_pcts[i] for i in order], height,
                         label=f"Traditional (n={trad_total})", color=TRAD_COLOR, alpha=0.7)

    # Add count annotations
    for i, idx in enumerate(order):
        ax.text(prog_pcts[idx] + 0.3, i - height / 2, str(prog_counts[idx]),
                va="center", fontsize=8, color=PROG_COLOR)
        ax.text(trad_pcts[idx] + 0.3, i + height / 2, str(trad_counts[idx]),
                va="center", fontsize=8, color=TRAD_COLOR)

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Proportion of Sources (%)")
    ax.set_title("Source Type Distribution by Prosecutor Ideology\n(Appendix A: LLM Structural Extraction, n=4,763)")
    ax.legend(loc="lower right")

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "08_source_type_distribution.png")
    plt.close(fig)
    logger.info("Saved 08_source_type_distribution.png")


# ── Figure 9: Bias indicator distribution (Appendix B) ──────────────────

def fig9_bias_indicators(bias_stats_path):
    """Grouped bar chart of bias indicators by prosecutor ideology from Step 09."""
    if not bias_stats_path.exists():
        logger.warning("Bias stats not found — skipping bias indicator figure")
        return

    with open(bias_stats_path) as f:
        stats = json.load(f)

    per_ind = stats.get("per_indicator", {})
    if not per_ind:
        logger.warning("No per-indicator data — skipping")
        return

    # Select key indicators (exclude n_total)
    indicator_labels = {
        "n_ungrounded_claims": "Ungrounded Claims",
        "n_ungrounded_severe": "Ungrounded (Severe)",
        "n_systemic_blame": "Systemic Blame",
        "n_source_imbalance_crit": "Source Imbalance\n(Critical)",
        "n_source_imbalance_supp": "Source Imbalance\n(Supportive)",
        "n_loaded_language": "Loaded Language",
        "n_loaded_negative": "Loaded Language\n(Negative)",
        "n_loaded_headline": "Loaded Language\n(Headline)",
        "n_missing_context": "Missing Context",
    }

    indicators = []
    prog_means = []
    trad_means = []
    ds = []

    for key, label in indicator_labels.items():
        if key not in per_ind:
            continue
        indicators.append(label)
        prog_means.append(per_ind[key].get("mean_progressive", 0))
        trad_means.append(per_ind[key].get("mean_traditional", 0))
        ds.append(per_ind[key].get("cohens_d", 0))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6),
                                     gridspec_kw={"width_ratios": [2, 1]})

    # Left panel: grouped bar chart of mean counts
    y = np.arange(len(indicators))
    height = 0.35

    ax1.barh(y - height / 2, prog_means, height,
             label="Progressive (n=100)", color=PROG_COLOR, alpha=0.7)
    ax1.barh(y + height / 2, trad_means, height,
             label="Traditional (n=100)", color=TRAD_COLOR, alpha=0.7)

    ax1.set_yticks(y)
    ax1.set_yticklabels(indicators, fontsize=9)
    ax1.set_xlabel("Mean Count per Article")
    ax1.set_title("Bias Indicator Prevalence")
    ax1.legend(loc="lower right", fontsize=9)

    # Right panel: Cohen's d lollipop chart
    colors = ["#e74c3c" if d > 0 else "#3498db" for d in ds]
    ax2.hlines(y, 0, ds, colors=colors, linewidth=2, alpha=0.7)
    ax2.scatter(ds, y, color=colors, s=60, zorder=5)
    ax2.axvline(0, color="gray", linestyle="--", alpha=0.7)
    ax2.set_yticks(y)
    ax2.set_yticklabels([])  # shared with left panel
    ax2.set_xlabel("Cohen's d")
    ax2.set_title("Effect Size")

    # Add d-value annotations
    for i, d in enumerate(ds):
        ax2.text(d + 0.01 * np.sign(d), i, f"{d:.2f}", va="center", fontsize=8)

    fig.suptitle("LLM-Based Bias Indicator Extraction Results\n(Appendix B, n=200 articles)",
                 fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "09_bias_indicators.png", bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved 09_bias_indicators.png")


# ── Figure 10: Per-method comparison scatter ─────────────────────────────

def fig10_method_comparison(df: pd.DataFrame):
    """Sentiment vs. Stance scatter with overlaid density contours.

    Shows how Methods A and B capture different dimensions of coverage bias:
    - X-axis: aspect sentiment (Method A, tone around prosecutor mentions)
    - Y-axis: stance classification (Method B, evaluative framing)

    Falls back to keyword score (C) vs. theme attribution if transformer
    scores are unavailable.
    """
    from matplotlib.gridspec import GridSpec
    from scipy.stats import gaussian_kde

    # Choose axes: prefer sentiment vs stance; fall back to keywords vs themes
    use_transformer = (
        "score_aspect_sentiment" in df.columns
        and "score_stance" in df.columns
        and df["score_aspect_sentiment"].notna().sum() > 100
        and df["score_stance"].notna().sum() > 100
    )

    if use_transformer:
        x_col, y_col = "score_aspect_sentiment", "score_stance"
        x_label = "Aspect Sentiment (Method A: Tone)"
        y_label = "Stance Classification (Method B: Evaluation)"
        title = "Sentiment vs. Stance: The Tone–Evaluation Divergence"
        q_labels = {
            "tl": "Negative tone\nSupportive stance",
            "tr": "Positive tone\nSupportive stance",
            "bl": "Negative tone\nCritical stance",
            "br": "Positive tone\nCritical stance",
        }
    else:
        x_col = "score_keywords"
        y_col = "ta_composite_score"
        if x_col not in df.columns or y_col not in df.columns:
            logger.warning("Missing scores for method comparison — skipping")
            return
        x_label = "Keyword Bias Score (Method C: Tone)"
        y_label = "Theme Attribution Score (Narrative Framing)"
        title = "Keyword Bias vs. Theme Attribution: Two Dimensions of Critical Coverage"
        q_labels = {
            "tl": "Negative keywords\nThemes present",
            "tr": "Neutral keywords\nThemes present",
            "bl": "Negative keywords\nNo themes",
            "br": "Neutral keywords\nNo themes",
        }

    both = df[df[x_col].notna() & df[y_col].notna()].copy()
    if len(both) < 50:
        logger.warning("Too few articles with both scores — skipping")
        return

    prog = both[both["prosecutor_type"] == "Progressive"]
    trad = both[both["prosecutor_type"] == "Traditional"]
    logger.info(f"Figure 10: {len(prog)} progressive, {len(trad)} traditional articles")

    # ── Layout: y-marginal | main scatter | spacer | bar chart ──
    fig = plt.figure(figsize=(14, 6))
    gs = GridSpec(
        2, 4,
        width_ratios=[0.25, 3.5, 0.08, 1.5],
        height_ratios=[1, 0.25],
        hspace=0.05, wspace=0.05,
    )

    ax_main = fig.add_subplot(gs[0, 1])    # main contour scatter
    ax_margx = fig.add_subplot(gs[1, 1], sharex=ax_main)  # x marginal
    ax_margy = fig.add_subplot(gs[0, 0], sharey=ax_main)  # y marginal
    ax_bar = fig.add_subplot(gs[0:, 3])    # quadrant bar chart

    # ── Axis ranges ──
    pad = 0.08
    x_lo, x_hi = both[x_col].quantile(0.005) - pad, both[x_col].quantile(0.995) + pad
    y_lo, y_hi = both[y_col].quantile(0.005) - pad, both[y_col].quantile(0.995) + pad
    # Ensure zero is within range
    x_lo, x_hi = min(x_lo, -pad), max(x_hi, pad)
    y_lo, y_hi = min(y_lo, -pad), max(y_hi, pad)

    xi = np.linspace(x_lo, x_hi, 120)
    yi = np.linspace(y_lo, y_hi, 120)
    Xi, Yi = np.meshgrid(xi, yi)

    for group, color, marker, label in [
        (prog, PROG_COLOR, "D", "Progressive"),
        (trad, TRAD_COLOR, "s", "Traditional"),
    ]:
        xv = group[x_col].values
        yv = group[y_col].values

        # Faint scatter underneath
        ax_main.scatter(xv, yv, c=color, alpha=0.03, s=3,
                        rasterized=True, edgecolors="none")

        # KDE density contours
        valid = np.isfinite(xv) & np.isfinite(yv)
        if valid.sum() > 50:
            try:
                xy = np.vstack([xv[valid], yv[valid]])
                kde = gaussian_kde(xy, bw_method=0.3)
                Zi = kde(np.vstack([Xi.ravel(), Yi.ravel()])).reshape(Xi.shape)
                ax_main.contourf(Xi, Yi, Zi, levels=6, cmap=None,
                                 colors=[color]*6,
                                 alpha=0.10)
                ax_main.contour(Xi, Yi, Zi, levels=6, colors=color,
                                alpha=0.65, linewidths=1.0)
            except Exception:
                pass

        # Mean marker
        mx, my = np.nanmean(xv), np.nanmean(yv)
        ax_main.plot(mx, my, marker, color=color, markersize=10,
                     markeredgecolor="white", markeredgewidth=1.5,
                     zorder=10, label=f"{label} mean ({mx:.3f}, {my:.3f})")

        # Marginal x density
        try:
            kde_x = gaussian_kde(xv[np.isfinite(xv)], bw_method=0.3)
            xd = np.linspace(x_lo, x_hi, 200)
            ax_margx.fill_between(xd, kde_x(xd), alpha=0.25, color=color)
            ax_margx.plot(xd, kde_x(xd), color=color, linewidth=1.2)
        except Exception:
            pass

        # Marginal y density
        try:
            kde_y = gaussian_kde(yv[np.isfinite(yv)], bw_method=0.3)
            yd = np.linspace(y_lo, y_hi, 200)
            ax_margy.fill_betweenx(yd, kde_y(yd), alpha=0.25, color=color)
            ax_margy.plot(kde_y(yd), yd, color=color, linewidth=1.2)
        except Exception:
            pass

    # Reference lines at zero
    ax_main.axhline(0, color="gray", linestyle="--", alpha=0.3, linewidth=0.8)
    ax_main.axvline(0, color="gray", linestyle="--", alpha=0.3, linewidth=0.8)

    # Quadrant labels in corners
    kw = dict(fontsize=7.5, alpha=0.5, ha="center", va="center",
              style="italic", color="#555")
    ax_main.text(0.25, 0.92, q_labels["tl"], transform=ax_main.transAxes, **kw)
    ax_main.text(0.75, 0.92, q_labels["tr"], transform=ax_main.transAxes, **kw)
    ax_main.text(0.25, 0.08, q_labels["bl"], transform=ax_main.transAxes, **kw)
    ax_main.text(0.75, 0.08, q_labels["br"], transform=ax_main.transAxes, **kw)

    ax_main.set_xlim(x_lo, x_hi)
    ax_main.set_ylim(y_lo, y_hi)
    ax_main.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax_main.set_ylabel(y_label, fontsize=10)

    # Hide tick labels on marginals
    plt.setp(ax_main.get_xticklabels(), visible=False)
    ax_margx.set_xlabel(x_label, fontsize=10)
    ax_margx.set_yticks([])
    ax_margy.set_xticks([])
    ax_margy.invert_xaxis()
    plt.setp(ax_margy.get_yticklabels(), visible=False)

    # ── Panel (b): Quadrant distribution bar chart ──
    quadrants = [
        ("Neg tone\nCritical", lambda x, y: (x < 0) & (y < 0)),
        ("Neg tone\nSupportive", lambda x, y: (x < 0) & (y >= 0)),
        ("Pos tone\nSupportive", lambda x, y: (x >= 0) & (y >= 0)),
        ("Pos tone\nCritical", lambda x, y: (x >= 0) & (y < 0)),
    ]
    # For the fallback (keywords vs themes), y threshold is 0 (themes present/absent)
    if not use_transformer:
        quadrants = [
            ("Neg kw\n+ themes", lambda x, y: (x < 0) & (y > 0)),
            ("Neutral kw\n+ themes", lambda x, y: (x >= 0) & (y > 0)),
            ("Neg kw\nno themes", lambda x, y: (x < 0) & (y <= 0)),
            ("Neutral kw\nno themes", lambda x, y: (x >= 0) & (y <= 0)),
        ]

    q_names = [q[0] for q in quadrants]
    prog_pcts, trad_pcts = [], []
    for _, cond_fn in quadrants:
        prog_mask = cond_fn(prog[x_col].values, prog[y_col].values)
        trad_mask = cond_fn(trad[x_col].values, trad[y_col].values)
        prog_pcts.append(prog_mask.sum() / len(prog) * 100 if len(prog) else 0)
        trad_pcts.append(trad_mask.sum() / len(trad) * 100 if len(trad) else 0)

    y_pos = np.arange(len(q_names))
    bar_h = 0.35
    ax_bar.barh(y_pos + bar_h/2, prog_pcts, bar_h, color=PROG_COLOR,
                alpha=0.75, label="Progressive")
    ax_bar.barh(y_pos - bar_h/2, trad_pcts, bar_h, color=TRAD_COLOR,
                alpha=0.75, label="Traditional")

    # Percentage labels
    for i, (pp, tp) in enumerate(zip(prog_pcts, trad_pcts)):
        ax_bar.text(pp + 0.8, i + bar_h/2, f"{pp:.0f}%", va="center",
                    fontsize=7.5, color=PROG_COLOR, fontweight="bold")
        ax_bar.text(tp + 0.8, i - bar_h/2, f"{tp:.0f}%", va="center",
                    fontsize=7.5, color=TRAD_COLOR, fontweight="bold")

    ax_bar.set_yticks(y_pos)
    ax_bar.set_yticklabels(q_names, fontsize=8)
    ax_bar.set_xlabel("% of articles", fontsize=9)
    ax_bar.set_title("Quadrant Distribution", fontsize=10, fontweight="bold")
    ax_bar.legend(fontsize=7.5, loc="lower right", framealpha=0.9)
    ax_bar.invert_yaxis()

    # Highlight the key divergence quadrant (first row)
    ax_bar.axhspan(-0.5, 0.5, alpha=0.08, color="gold")

    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.98)
    fig.savefig(FIGURES_DIR / "10_method_comparison.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved 10_method_comparison.png")


# ── Figure 11: Regression coefficient plot ────────────────────────────────

def fig11_regression_coefficients(regression_csv):
    """Coefficient plot from OLS regression with 95% CIs."""
    if not regression_csv.exists():
        logger.warning("Regression CSV not found — skipping coefficient plot")
        return

    reg = pd.read_csv(regression_csv, index_col=0)

    # Rename for readability
    label_map = {
        "is_progressive": "Progressive prosecutor",
        "C(county)[T.San Francisco]": "County: San Francisco",
        "C(county)[T.San Mateo]": "County: San Mateo",
        "C(year)[T.2020]": "Year: 2020",
        "C(year)[T.2021]": "Year: 2021",
        "C(year)[T.2022]": "Year: 2022",
        "C(year)[T.2023]": "Year: 2023",
        "C(year)[T.2024]": "Year: 2024",
        "article_length": "Article length (words)",
    }

    # Skip intercept
    reg = reg.drop("Intercept", errors="ignore")

    labels = [label_map.get(idx, idx) for idx in reg.index]
    coefs = reg["coefficient"].values
    ci_lo = reg["ci_lower"].values
    ci_hi = reg["ci_upper"].values
    pvals = reg["p_value"].values

    fig, ax = plt.subplots(figsize=(10, 6))

    y = np.arange(len(labels))

    # Color by significance
    colors = []
    for p in pvals:
        if p < 0.01:
            colors.append("#2c3e50")  # dark — highly significant
        elif p < 0.05:
            colors.append("#e67e22")  # orange — significant
        else:
            colors.append("#95a5a6")  # gray — not significant

    # Plot coefficient dots with CI whiskers
    for i, (c, lo, hi, col) in enumerate(zip(coefs, ci_lo, ci_hi, colors)):
        ax.errorbar(c, i, xerr=[[c - lo], [hi - c]], fmt="o", color=col,
                     ecolor=col, elinewidth=1.5, capsize=5, markersize=8, alpha=0.85)

    # Highlight the key variable
    prog_idx = list(reg.index).index("is_progressive") if "is_progressive" in reg.index else None
    if prog_idx is not None:
        ax.axhspan(prog_idx - 0.4, prog_idx + 0.4, alpha=0.08, color=PROG_COLOR)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.axvline(0, color="gray", linestyle="--", alpha=0.7, linewidth=1.2)
    ax.set_xlabel("OLS Coefficient (95% CI, cluster-robust SEs)", fontsize=11)
    ax.set_title("Regression Coefficients: Composite Bias Score", fontsize=13)
    ax.invert_yaxis()

    # Legend for significance
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="#2c3e50", label="p < .01", linestyle="None", markersize=8),
        Line2D([0], [0], marker="o", color="#e67e22", label="p < .05", linestyle="None", markersize=8),
        Line2D([0], [0], marker="o", color="#95a5a6", label="p ≥ .05", linestyle="None", markersize=8),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "11_regression_coefficients.png")
    plt.close(fig)
    logger.info("Saved 11_regression_coefficients.png")


# ── Figure 12: Theme attribution per-theme differential ───────────────────

def fig12_theme_attr_differential(theme_stats_path):
    """Two-panel chart: prevalence bars + risk ratio lollipops for Step 10 themes."""
    if not theme_stats_path.exists():
        logger.warning("Theme stats JSON not found — skipping theme attribution differential")
        return

    with open(theme_stats_path) as f:
        stats = json.load(f)

    per_theme = stats.get("per_theme", {})
    if not per_theme:
        logger.warning("No per_theme data — skipping")
        return

    themes = list(per_theme.keys())
    prog_pcts = [100 * per_theme[t]["progressive_rate"] for t in themes]
    trad_pcts = [100 * per_theme[t]["traditional_rate"] for t in themes]
    risk_ratios = [per_theme[t]["risk_ratio"] for t in themes]
    p_values = [per_theme[t]["p_value"] for t in themes]

    # Sort by risk ratio descending
    order = np.argsort(risk_ratios)  # ascending for horizontal bars (bottom to top)
    labels = [t.replace("_", " ").title() for t in themes]

    def sig_stars(p):
        if p < 0.001: return "***"
        if p < 0.01: return "**"
        if p < 0.05: return "*"
        return ""

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6),
                                     gridspec_kw={"width_ratios": [2, 1]})

    # Left panel: grouped bars
    y = np.arange(len(themes))
    height = 0.35

    ax1.barh(y - height / 2, [prog_pcts[i] for i in order], height,
             label="Progressive", color=PROG_COLOR, alpha=0.7)
    ax1.barh(y + height / 2, [trad_pcts[i] for i in order], height,
             label="Traditional", color=TRAD_COLOR, alpha=0.7)

    ax1.set_yticks(y)
    ax1.set_yticklabels([f"{labels[i]} {sig_stars(p_values[i])}" for i in order], fontsize=10)
    ax1.set_xlabel("Prevalence (%)")
    ax1.set_title("Theme Prevalence by Prosecutor Type")
    ax1.legend(loc="lower right", fontsize=9)

    # Right panel: risk ratio lollipop
    rr_sorted = [risk_ratios[i] for i in order]
    # Cap infinite risk ratios for display
    rr_display = [min(rr, 6.0) for rr in rr_sorted]
    colors = [PROG_COLOR if rr > 1 else TRAD_COLOR for rr in rr_sorted]

    ax2.hlines(y, 1, rr_display, colors=colors, linewidth=2, alpha=0.7)
    ax2.scatter(rr_display, y, color=colors, s=60, zorder=5)
    ax2.axvline(1.0, color="gray", linestyle="--", alpha=0.7)
    ax2.set_yticks(y)
    ax2.set_yticklabels([])
    ax2.set_xlabel("Risk Ratio (Prog / Trad)")
    ax2.set_title("Risk Ratio")

    # Annotations
    for i, (rr, rr_d) in enumerate(zip(rr_sorted, rr_display)):
        label = f"{rr:.1f}×" if rr < 10 else f"{rr:.0f}×"
        ax2.text(rr_d + 0.05, i, label, va="center", fontsize=8)

    fig.suptitle("Prosecutor-Attributed Theme Analysis (Step 10, n=13,249)",
                 fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "12_theme_attribution_differential.png", bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved 12_theme_attribution_differential.png")


# ── Figure 13: Theme attribution per-prosecutor heatmap ───────────────────

def fig13_theme_attr_heatmap(theme_stats_path):
    """Heatmap of theme prevalence rates by prosecutor."""
    if not theme_stats_path.exists():
        logger.warning("Theme stats JSON not found — skipping theme attribution heatmap")
        return

    with open(theme_stats_path) as f:
        stats = json.load(f)

    per_prosecutor = stats.get("per_prosecutor", {})
    if not per_prosecutor:
        logger.warning("No per_prosecutor data — skipping")
        return

    # Build DataFrame
    rows = []
    for name, data in per_prosecutor.items():
        row = {"Prosecutor": name, "Ideology": data["ideology"]}
        for theme, rate in data["theme_rates"].items():
            row[theme.replace("_", " ").title()] = 100 * rate
        rows.append(row)

    df_heat = pd.DataFrame(rows).set_index("Prosecutor")
    ideology = df_heat["Ideology"]
    df_heat = df_heat.drop(columns=["Ideology"])

    # Sort: progressive first, then traditional
    prog_names = [n for n, i in ideology.items() if i == "Progressive"]
    trad_names = [n for n, i in ideology.items() if i == "Traditional"]
    df_heat = df_heat.loc[prog_names + trad_names]

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.heatmap(
        df_heat,
        annot=True,
        fmt=".1f",
        cmap="YlOrRd",
        ax=ax,
        linewidths=0.5,
        cbar_kws={"label": "Prevalence (%)"},
    )
    ax.set_title("Theme Prevalence (%) by Prosecutor — Prosecutor-Attributed Detection")
    ax.set_ylabel("")

    # Color row labels by ideology
    for i, label in enumerate(ax.get_yticklabels()):
        name = label.get_text()
        color = PROG_COLOR if name in prog_names else TRAD_COLOR
        label.set_color(color)
        label.set_fontweight("bold")

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "13_theme_attribution_heatmap.png")
    plt.close(fig)
    logger.info("Saved 13_theme_attribution_heatmap.png")


# ── Figure 14: Theme method agreement by prosecutor type ──────────────────

def fig14_theme_method_agreement(theme_attr_path):
    """Stacked bar chart of method agreement distribution by prosecutor type."""
    if not theme_attr_path.exists():
        logger.warning("Theme attribution parquet not found — skipping method agreement")
        return

    ta_df = load_parquet(theme_attr_path)

    if "ta_methods_detected" not in ta_df.columns or "prosecutor_type" not in ta_df.columns:
        logger.warning("Missing columns for method agreement — skipping")
        return

    fig, ax = plt.subplots(figsize=(10, 4))

    types = ["Progressive", "Traditional"]
    colors_grad = ["#f0f0f0", "#fdbe85", "#fd8d3c", "#e6550d", "#a63603"]
    labels = ["0 methods", "1 method", "2 methods", "3 methods", "4 methods"]

    for j, ptype in enumerate(types):
        subset = ta_df[ta_df["prosecutor_type"] == ptype]
        total = len(subset)
        if total == 0:
            continue
        left = 0
        for n_methods in range(5):
            count = (subset["ta_methods_detected"] == n_methods).sum()
            pct = 100 * count / total
            bar = ax.barh(j, pct, left=left, color=colors_grad[n_methods],
                          edgecolor="white", linewidth=0.5,
                          label=labels[n_methods] if j == 0 else "")
            if pct > 4:
                ax.text(left + pct / 2, j, f"{pct:.0f}%", ha="center", va="center", fontsize=9)
            left += pct

    ax.set_yticks(range(len(types)))
    ax.set_yticklabels(types, fontsize=11)
    ax.set_xlabel("Proportion of Articles (%)")
    ax.set_title("Theme Detection Method Agreement by Prosecutor Type")
    ax.legend(loc="upper right", fontsize=9, ncol=5, bbox_to_anchor=(1.0, -0.15))
    ax.set_xlim(0, 100)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "14_theme_method_agreement.png", bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved 14_theme_method_agreement.png")


# ── Main ───────────────────────────────────────────────────────────────────

# ── Figure 15: Temporal heterogeneity ──────────────────────────────────────

def fig15_temporal_heterogeneity(stats_path):
    """Quarterly Cohen's d over time — shows temporal heterogeneity in bias.

    Reads quarterly effect sizes from 06_stats_results.json and plots:
    - Overall quarterly d with 95% CIs
    - County-level quarterly d (where sufficient data exists)
    - Reference lines at d=0 and conventional thresholds
    - Tenure transition markers
    """
    if not stats_path.exists():
        logger.warning("Stats JSON not found — skipping temporal heterogeneity")
        return

    with open(stats_path) as f:
        results = json.load(f)

    qe = results.get("quarterly_effects", {})
    overall_q = qe.get("overall_quarterly", [])
    county_q = qe.get("county_quarterly", {})

    if not overall_q:
        logger.warning("No quarterly data — skipping temporal heterogeneity figure")
        return

    fig, axes = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={"height_ratios": [3, 1]})
    ax_main = axes[0]
    ax_n = axes[1]

    # Parse quarters to timestamps for plotting
    def q_to_ts(q_str):
        """Convert '2020Q1' to a timestamp at mid-quarter."""
        year = int(q_str[:4])
        qnum = int(q_str[-1])
        month = (qnum - 1) * 3 + 2  # mid-quarter month
        return pd.Timestamp(year=year, month=month, day=15)

    # ── Main panel: quarterly d with CIs ──
    xs = [q_to_ts(q["quarter"]) for q in overall_q]
    ds = [q["cohens_d"] for q in overall_q]
    ci_los = [q["ci_lower"] for q in overall_q]
    ci_his = [q["ci_upper"] for q in overall_q]
    ns_prog = [q["n_prog"] for q in overall_q]
    ns_trad = [q["n_trad"] for q in overall_q]

    # Fill between CIs
    ax_main.fill_between(xs, ci_los, ci_his, alpha=0.15, color="#1a1a2e")
    ax_main.plot(xs, ds, "o-", color="#1a1a2e", markersize=6, linewidth=2,
                 label="Overall quarterly d", zorder=3)

    # Add county-level data as lighter lines
    county_colors = {"San Francisco": PROG_COLOR, "Alameda": TRAD_COLOR}
    for county, cq_data in county_q.items():
        if not cq_data:
            continue
        c_xs = [q_to_ts(q["quarter"]) for q in cq_data]
        c_ds = [q["cohens_d"] for q in cq_data]
        c_color = county_colors.get(county, "gray")
        ax_main.plot(c_xs, c_ds, "s--", color=c_color, markersize=4,
                     linewidth=1, alpha=0.6, label=f"{county}")

    # Reference lines
    ax_main.axhline(0, color="gray", linestyle="-", alpha=0.5, linewidth=1)
    ax_main.axhspan(-0.2, 0.2, alpha=0.05, color="green", label="Negligible (|d| < 0.2)")
    ax_main.axhline(-0.5, color="orange", linestyle=":", alpha=0.3, linewidth=0.8)
    ax_main.axhline(0.5, color="orange", linestyle=":", alpha=0.3, linewidth=0.8)

    # Tenure transitions — position labels at top of axes using transform
    transitions = [
        (pd.Timestamp("2022-07-08"), "Jenkins\nreplaces Boudin", "#e74c3c", "right"),
        (pd.Timestamp("2023-01-03"), "Price\nreplaces O'Malley", "#3498db", "left"),
    ]
    for t_date, t_label, t_color, ha in transitions:
        ax_main.axvline(t_date, color=t_color, linestyle="--", alpha=0.5, linewidth=1.2)
        ax_main.text(t_date, 0.98, t_label, ha=ha, va="top", fontsize=8,
                     color=t_color, fontweight="bold",
                     transform=ax_main.get_xaxis_transform())

    ax_main.set_ylabel("Cohen's d\n(negative = more negative toward progressive)", fontsize=11)
    ax_main.set_title("Temporal Heterogeneity: Quarterly Effect Sizes", fontsize=14,
                      fontweight="bold")
    ax_main.legend(loc="lower left", fontsize=9, framealpha=0.9)
    ax_main.xaxis.set_major_locator(mdates.YearLocator())
    ax_main.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_main.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))
    ax_main.tick_params(axis="x", rotation=0)

    # ── Bottom panel: sample sizes ──
    bar_width = 20  # days
    for i, (x, np_, nt_) in enumerate(zip(xs, ns_prog, ns_trad)):
        ax_n.bar(x - pd.Timedelta(days=bar_width/2), np_, width=bar_width,
                 color=PROG_COLOR, alpha=0.6, label="Progressive" if i == 0 else "")
        ax_n.bar(x + pd.Timedelta(days=bar_width/2), nt_, width=bar_width,
                 color=TRAD_COLOR, alpha=0.6, label="Traditional" if i == 0 else "")

    ax_n.set_ylabel("N articles")
    ax_n.set_xlabel("Year")
    ax_n.legend(loc="upper right", fontsize=8)
    ax_n.xaxis.set_major_locator(mdates.YearLocator())
    ax_n.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_n.tick_params(axis="x", rotation=0)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "15_temporal_heterogeneity.png", dpi=200)
    plt.close(fig)
    logger.info("Saved 15_temporal_heterogeneity.png")


def fig16_per_method_regression(stats_path):
    """Per-method regression coefficients — shows which bias dimensions survive controls."""
    if not stats_path.exists():
        logger.warning("Stats JSON not found — skipping per-method regression figure")
        return

    with open(stats_path) as f:
        results = json.load(f)

    pmr = results.get("per_method_regression", {})
    if not pmr:
        logger.warning("No per-method regression data — skipping figure 16")
        return

    method_order = [
        "score_stance",
        "score_keywords",
        "score_aspect_sentiment",
        "score_doc_sentiment",
    ]
    labels = {
        "score_aspect_sentiment": "A: Aspect\nSentiment",
        "score_stance": "B: Stance\nClassification",
        "score_keywords": "C: Keyword\nAnalysis",
        "score_doc_sentiment": "D: Document\nSentiment",
    }

    fig, ax = plt.subplots(figsize=(10, 6))

    y_positions = []
    y_labels = []
    for i, col in enumerate(method_order):
        if col not in pmr or "error" in pmr[col]:
            continue
        data = pmr[col]
        coef = data["progressive_coef"]
        ci_lo = data["ci_lower"]
        ci_hi = data["ci_upper"]
        p = data["progressive_p"]
        r2 = data["r_squared"]

        y = len(method_order) - i - 1
        y_positions.append(y)
        y_labels.append(labels.get(col, col))

        # Color by significance
        if p < 0.001:
            color = "#1a1a2e"
            marker = "D"
        elif p < 0.05:
            color = "#e67e22"
            marker = "D"
        else:
            color = "#aaaaaa"
            marker = "o"

        ax.plot([ci_lo, ci_hi], [y, y], color=color, linewidth=2.5, solid_capstyle="round")
        ax.plot(coef, y, marker=marker, color=color, markersize=10, zorder=5)

        # Annotate with coefficient and p-value
        p_str = "p < .001" if p < 0.001 else f"p = {p:.3f}"
        ax.annotate(f"\u03b2 = {coef:.4f}, {p_str}\nR\u00b2 = {r2:.3f}",
                    xy=(ci_hi + 0.002, y), fontsize=8.5, va="center")

    ax.axvline(0, color="gray", linestyle="--", alpha=0.6, linewidth=1)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(y_labels, fontsize=11)
    ax.set_xlabel("Progressive prosecutor coefficient (\u03b2)\nwith cluster-robust 95% CI", fontsize=11)
    ax.set_title("Per-Method OLS Regression:\nDoes Ideology Predict Each Bias Dimension?",
                 fontsize=13, fontweight="bold")

    # Legend for significance
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="D", color="#1a1a2e", markersize=8, linestyle="None", label="p < .001"),
        Line2D([0], [0], marker="D", color="#e67e22", markersize=8, linestyle="None", label="p < .05"),
        Line2D([0], [0], marker="o", color="#aaaaaa", markersize=8, linestyle="None", label="p \u2265 .05"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=9)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "16_per_method_regression.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved 16_per_method_regression.png")


def fig17_per_method_temporal(stats_path):
    """Per-method quarterly d over time — shows stance is event-driven, sentiment stays flat."""
    if not stats_path.exists():
        logger.warning("Stats JSON not found — skipping per-method temporal figure")
        return

    with open(stats_path) as f:
        results = json.load(f)

    pmq = results.get("per_method_quarterly", {})
    if not pmq:
        logger.warning("No per-method quarterly data — skipping figure 17")
        return

    method_order = [
        "score_aspect_sentiment",
        "score_stance",
        "score_keywords",
        "score_doc_sentiment",
    ]
    labels = {
        "score_aspect_sentiment": "A: Aspect Sentiment",
        "score_stance": "B: Stance Classification",
        "score_keywords": "C: Keyword Analysis",
        "score_doc_sentiment": "D: Document Sentiment",
    }
    colors = {
        "score_aspect_sentiment": "#2ecc71",
        "score_stance": "#e74c3c",
        "score_keywords": "#3498db",
        "score_doc_sentiment": "#9b59b6",
    }

    def q_to_ts(q_str):
        year = int(q_str[:4])
        qnum = int(q_str[-1])
        month = (qnum - 1) * 3 + 2
        return pd.Timestamp(year=year, month=month, day=15)

    fig, axes = plt.subplots(4, 1, figsize=(14, 16), sharex=True)

    transitions = [
        (pd.Timestamp("2021-10-01"), "SF recall starts", "#f39c12"),
        (pd.Timestamp("2022-07-08"), "Jenkins replaces Boudin", "#e74c3c"),
        (pd.Timestamp("2023-01-03"), "Price replaces O'Malley", "#3498db"),
    ]

    for idx, col in enumerate(method_order):
        ax = axes[idx]
        quarterly = pmq.get(col, [])
        if not quarterly:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            ax.set_ylabel(labels.get(col, col), fontsize=10)
            continue

        xs = [q_to_ts(q["quarter"]) for q in quarterly]
        ds = [q["cohens_d"] for q in quarterly]
        ci_los = [q["ci_lower"] for q in quarterly]
        ci_his = [q["ci_upper"] for q in quarterly]

        c = colors.get(col, "gray")
        ax.fill_between(xs, ci_los, ci_his, alpha=0.15, color=c)
        ax.plot(xs, ds, "o-", color=c, markersize=5, linewidth=1.8)

        # Reference lines
        ax.axhline(0, color="gray", linestyle="-", alpha=0.4, linewidth=0.8)
        ax.axhspan(-0.2, 0.2, alpha=0.04, color="green")

        # Transitions
        for t_date, t_label, t_color in transitions:
            ax.axvline(t_date, color=t_color, linestyle="--", alpha=0.4, linewidth=1)

        # SD annotation
        sd = float(np.std(ds))
        d_range = f"[{min(ds):.2f}, {max(ds):.2f}]"
        ax.text(0.02, 0.95, f"SD = {sd:.2f}, range = {d_range}",
                transform=ax.transAxes, fontsize=8.5, va="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        ax.set_ylabel("Cohen's d", fontsize=10)
        ax.set_title(labels.get(col, col), fontsize=11, fontweight="bold", loc="left")
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))

    # Transition labels only on top panel — rotated 90° to avoid overlap
    for t_date, t_label, t_color in transitions:
        axes[0].text(t_date, 1.02, t_label, ha="left", va="bottom", fontsize=7.5,
                     color=t_color, fontweight="bold", rotation=90,
                     transform=axes[0].get_xaxis_transform())

    axes[-1].set_xlabel("Year", fontsize=11)
    fig.suptitle("Per-Method Temporal Heterogeneity: Quarterly Effect Sizes",
                 fontsize=14, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(FIGURES_DIR / "17_per_method_temporal.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved 17_per_method_temporal.png")


def main() -> None:
    setup_logging()
    setup_style()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    df = load_parquet(BIAS_PARQUET)

    # Merge frames if available
    if FRAMES_PARQUET.exists():
        frames = load_parquet(FRAMES_PARQUET)
        frame_cols = [c for c in frames.columns if c.startswith("frame_") or c == "dominant_frame"]
        if frame_cols:
            df = df.merge(
                frames[["article_id"] + frame_cols],
                on="article_id",
                how="left",
                suffixes=("", "_frame"),
            )

    # Merge theme attribution scores if available
    if THEME_ATTR_PARQUET.exists():
        ta = load_parquet(THEME_ATTR_PARQUET)
        if "ta_composite_score" in ta.columns:
            df = df.merge(
                ta[["article_id", "ta_composite_score"]],
                on="article_id",
                how="left",
            )

    # Filter to articles with analysis data
    analysis_df = df[
        df["primary_prosecutor"].notna()
        & df["composite_bias_score"].notna()
    ].copy()
    logger.info(f"Articles for visualization: {len(analysis_df):,}")

    # Generate all figures
    with timer("Figure 1: Violin by type"):
        fig1_violin_by_type(analysis_df)

    with timer("Figure 2: Per-prosecutor"):
        fig2_per_prosecutor(analysis_df)

    with timer("Figure 3: Paired county"):
        fig3_paired_county(analysis_df)

    with timer("Figure 4: Time series"):
        fig4_time_series(analysis_df)

    with timer("Figure 5: Framing heatmap"):
        fig5_framing_heatmap(analysis_df)

    with timer("Figure 6: Forest plot"):
        fig6_forest_plot(STATS_JSON, df=analysis_df)

    with timer("Figure 7: Theme prevalence"):
        fig7_theme_prevalence(analysis_df)

    with timer("Figure 8: Source type distribution (Appendix A)"):
        fig8_source_type_distribution(EXTRACTION_STATS_JSON)

    with timer("Figure 9: Bias indicators (Appendix B)"):
        fig9_bias_indicators(BIAS_STATS_JSON)

    with timer("Figure 10: Method comparison scatter"):
        fig10_method_comparison(analysis_df)

    with timer("Figure 11: Regression coefficients"):
        fig11_regression_coefficients(REGRESSION_CSV)

    with timer("Figure 12: Theme attribution differential (Step 10)"):
        fig12_theme_attr_differential(THEME_STATS_JSON)

    with timer("Figure 13: Theme attribution heatmap (Step 10)"):
        fig13_theme_attr_heatmap(THEME_STATS_JSON)

    with timer("Figure 14: Theme method agreement (Step 10)"):
        fig14_theme_method_agreement(THEME_ATTR_PARQUET)

    with timer("Figure 15: Temporal heterogeneity"):
        fig15_temporal_heterogeneity(STATS_JSON)

    with timer("Figure 16: Per-method regression coefficients"):
        fig16_per_method_regression(STATS_JSON)

    with timer("Figure 17: Per-method temporal heterogeneity"):
        fig17_per_method_temporal(STATS_JSON)

    logger.info(f"\nAll figures saved to {FIGURES_DIR}")
    logger.info("Done.")


if __name__ == "__main__":
    main()
