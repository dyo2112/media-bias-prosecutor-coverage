"""
Build the salience figure for the Center talk from gdelt_boudin_pull.py output.

Two panels:
  A. Daily share of US news coverage mentioning "Chesa Boudin", and the
     recall-framed subset, Jan 2021 - Dec 2022, with the three dates that
     matter marked.
  B. Local Bay Area vs national outlets among recall articles, by week --
     the "did it escape the market?" question.

Panel B is skipped if articles.csv is missing or too sparse to be honest.
"""

import csv
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

OUTDIR = "gdelt_output_boudin"
INK = "#14161F"
RED = "#A31621"
SLATE = "#2B3A55"
MUTED = "#6B7280"
GRID = "#E3E6EC"

EVENTS = [
    (datetime(2021, 12, 11), "Dec 11-12, 2021\nburst (unexplained)"),
    # The mid-Feb bump is NOT the DA recall and NOT the Feb 2 MOU withdrawal:
    # it is the San Francisco SCHOOL BOARD recall, which a near20:"Boudin recall"
    # proximity query picks up because coverage of that vote asked whether
    # Boudin was next. 11% of that week's articles name the school board in the
    # headline alone, against 1.1% across the rest of the corpus.
    (datetime(2022, 2, 15), "Feb 15, 2022\nSchool board recall\n(a different recall)"),
    (datetime(2022, 6, 7), "Jun 7, 2022\nRecall election"),
]

# Bay Area outlets. Everything not on this list is counted as "outside the Bay
# Area" -- a local list is finite and checkable, whereas trying to enumerate
# every national outlet and aggregator leaves most of the corpus unclassified.
BAY_AREA_DOMAINS = {
    "sfchronicle.com", "sfgate.com", "sfexaminer.com", "sfstandard.com",
    "sfist.com", "missionlocal.org", "kqed.org", "kalw.org", "kron4.com",
    "ktvu.com", "abc7news.com", "nbcbayarea.com", "sanfrancisco.cbslocal.com",
    "sfbayview.com", "ebar.com", "oaklandside.org", "berkeleyside.org",
    "eastbaytimes.com", "mercurynews.com", "marinij.com", "smdailyjournal.com",
    "alamedapost.com", "sfweekly.com", "48hills.org", "richmondsfblog.com",
    "hoodline.com", "padailypost.com", "paloaltoonline.com", "sanjoseinside.com",
    "sfpublicpress.org", "elladolatino.com", "sfbay.ca",
}


def read_timeline():
    path = os.path.join(OUTDIR, "timeline_daily.csv")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.strptime(r["date"][:8], "%Y%m%d")
            except (ValueError, KeyError):
                continue

            def num(key):
                v = r.get(key)
                return float(v) if v not in (None, "", "None") else 0.0

            rows.append({
                "date": d,
                "boudin_pct": num("chesa_boudin_pct_of_us") ,
                "recall_pct": num("boudin_recall_pct_of_us"),
                "boudin_n": num("chesa_boudin_matches"),
                "recall_n": num("boudin_recall_matches"),
            })
    rows.sort(key=lambda r: r["date"])
    return rows


def read_articles():
    path = os.path.join(OUTDIR, "articles.csv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sd = (r.get("seendate") or "")[:8]
            try:
                d = datetime.strptime(sd, "%Y%m%d")
            except ValueError:
                continue
            out.append({"date": d, "outlet_type": r.get("outlet_type"), "domain": r.get("domain")})
    return out


def main():
    tl = read_timeline()
    arts = read_articles()
    if not tl:
        raise SystemExit("No timeline rows -- did the pull finish?")

    # Panel B needs the article-level pull to be COMPLETE. Pass --no-panel-b to
    # force the salience-only figure while that pull is still running.
    have_b = len(arts) >= 50 and "--no-panel-b" not in sys.argv
    fig, axes = plt.subplots(2 if have_b else 1, 1, figsize=(11.5, 6.6 if have_b else 4.2),
                             sharex=False,
                             gridspec_kw={"height_ratios": [1.35, 1]} if have_b else None)
    axes = axes if have_b else [axes]

    # ── Panel A: salience ──────────────────────────────────────────────
    ax = axes[0]
    dates = [r["date"] for r in tl]

    def roll(key, w=7):
        """Centred w-day mean. News volume is bursty by weekday; the ramp is
        invisible in raw daily counts."""
        vals = [r[key] for r in tl]
        half = w // 2
        out = []
        for i in range(len(vals)):
            lo, hi = max(0, i - half), min(len(vals), i + half + 1)
            out.append(sum(vals[lo:hi]) / (hi - lo))
        return out

    b_s, r_s = roll("boudin_pct"), roll("recall_pct")
    ax.fill_between(dates, b_s, color=SLATE, alpha=0.20, linewidth=0)
    ax.plot(dates, b_s, color=SLATE, lw=1.5, label="All coverage naming Chesa Boudin")
    ax.plot(dates, r_s, color=RED, lw=1.8, label="Recall-framed coverage")

    ymax = max(max(b_s), max(r_s))
    # (x-offset, y as fraction of ymax, horizontal alignment) per event
    placement = [(6, 0.80, "left"), (6, 0.46, "left"), (-8, 0.62, "right")]
    for (when, label), (dx, fy, ha) in zip(EVENTS, placement):
        if dates[0] <= when <= dates[-1]:
            ax.axvline(when, color=INK, lw=0.9, ls=(0, (4, 3)), alpha=0.7)
            ax.annotate(label, xy=(when, ymax * fy), xytext=(dx, 0),
                        textcoords="offset points", fontsize=9, color=INK,
                        ha=ha, va="top", linespacing=1.35)

    # Callout on the election-week peak, anchored in the empty upper-left
    pk_i = max(range(len(b_s)), key=lambda i: b_s[i])
    counts = [r["boudin_n"] for r in tl]
    base21 = [r["boudin_n"] for r in tl if r["date"].year == 2021]
    peak_week = counts[max(0, pk_i - 3):pk_i + 4]
    mult = (sum(peak_week) / len(peak_week)) / (sum(base21) / len(base21))
    ax.annotate(f"Election week:\nabout {mult:.0f}x the 2021 average",
                xy=(dates[pk_i], b_s[pk_i]), xytext=(-16, 4),
                textcoords="offset points", fontsize=9.5, color=RED,
                fontweight="bold", ha="right", va="top", linespacing=1.35,
                arrowprops=dict(arrowstyle="-", color=RED, lw=1.0,
                                connectionstyle="arc3,rad=-0.25"))

    ax.set_ylabel("Share of all US news coverage\nGDELT monitored (%, 7-day average)",
                  fontsize=9.5, color=SLATE)
    ax.set_ylim(0, ymax * 1.20)
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")
    # No chart title: the slide it lands on supplies one, and two stacked
    # headings read as a mistake.

    # ── Panel B: local vs national ─────────────────────────────────────
    if have_b:
        ax2 = axes[1]
        by_week = defaultdict(Counter)
        for a in arts:
            d = a["date"]
            key = d - timedelta(days=d.weekday())  # Monday of that week
            dom = (a["domain"] or "").lower()
            if dom.startswith("www."):      # not lstrip(): that strips characters, not a prefix
                dom = dom[4:]
            by_week[key]["bay" if dom in BAY_AREA_DOMAINS else "away"] += 1
        # Plot the SHARE, not raw counts: election week is ~1,250 articles
        # against ~20 in a quiet week, so a stacked count chart is one giant
        # bar and 30 invisible ones. The share is what answers "how far did it
        # travel" -- and the raw multipliers go in the caption instead.
        weeks = sorted(by_week)
        elec = datetime(2022, 6, 6)  # Monday of election week
        share, colors = [], []
        for w in weeks:
            b, a = by_week[w]["bay"], by_week[w]["away"]
            share.append(100 * b / (b + a) if (b + a) else 0)
            colors.append(RED if w == elec else SLATE)
        ax2.bar(weeks, share, width=5.4, color=colors)

        other = [(by_week[w]["bay"], by_week[w]["away"]) for w in weeks if w != elec]
        base = 100 * sum(b for b, _ in other) / sum(b + a for b, a in other)
        ax2.axhline(base, color=INK, lw=1.0, ls=(0, (4, 3)), alpha=0.8)
        ax2.annotate(f"{base:.0f}% in every other week", xy=(weeks[1], base),
                     xytext=(0, 5), textcoords="offset points",
                     fontsize=9, color=INK, va="bottom")
        if elec in by_week:
            # Park the label in the empty upper band; at a small offset it
            # lands on top of the neighbouring bars.
            ax2.annotate(f"Election week: {share[weeks.index(elec)]:.0f}%",
                         xy=(elec, share[weeks.index(elec)]), xytext=(-6, 108),
                         textcoords="offset points", fontsize=10, color=RED,
                         fontweight="bold", ha="center",
                         arrowprops=dict(arrowstyle="-", color=RED, lw=1.1))

        ax2.set_ylabel("Share of that week's\ncoverage from Bay Area outlets", fontsize=9.5, color=SLATE)
        ax2.set_ylim(0, max(share) * 1.35)
        ax2.set_title(f"How far it travelled  ({weeks[0]:%b %Y} - {weeks[-1]:%b %Y})",
                      fontsize=11.5, color=INK, fontweight="bold", loc="left", pad=8)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))  # %-d is not portable to Windows
        ax2.xaxis.set_major_locator(mdates.MonthLocator())

    for a in axes:
        a.spines[["top", "right"]].set_visible(False)
        a.spines[["left", "bottom"]].set_color(GRID)
        a.grid(axis="y", color=GRID, lw=0.7)
        a.set_axisbelow(True)
        a.tick_params(colors=MUTED, labelsize=9)
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    axes[0].xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    fig.tight_layout()
    out = os.path.join(OUTDIR, "boudin_salience.png")
    fig.savefig(out, dpi=200, facecolor="white")
    print(f"wrote {out}")

    # ── Numbers for the slide ──────────────────────────────────────────
    peak = max(tl, key=lambda r: r["recall_pct"])
    peak_all = max(tl, key=lambda r: r["boudin_pct"])
    base = [r for r in tl if r["date"] < datetime(2022, 1, 1)]
    base_mean = sum(r["recall_pct"] for r in base) / len(base) if base else 0
    print(f"peak recall-framed day : {peak['date']:%Y-%m-%d}  {peak['recall_pct']:.4f}% "
          f"({int(peak['recall_n'])} articles)")
    print(f"peak all-Boudin day    : {peak_all['date']:%Y-%m-%d}  {peak_all['boudin_pct']:.4f}% "
          f"({int(peak_all['boudin_n'])} articles)")
    print(f"2021 baseline (recall) : {base_mean:.5f}%   -> peak is {peak['recall_pct']/base_mean:.0f}x baseline"
          if base_mean else f"2021 baseline (recall) : 0")

    if arts:
        types = Counter(a["outlet_type"] for a in arts)
        print(f"articles: {len(arts)}  " + "  ".join(f"{k}={v}" for k, v in types.most_common()))
        doms = Counter(a["domain"] for a in arts)
        print("top domains: " + ", ".join(f"{d} ({n})" for d, n in doms.most_common(12)))


if __name__ == "__main__":
    main()
