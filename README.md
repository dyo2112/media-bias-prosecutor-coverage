# Measuring Media Bias Toward Reform Prosecutors

This repository contains the analysis pipeline and manuscript assets for a multi-method NLP study of Bay Area prosecutor coverage.

The current publication workflow is:
- run core NLP scoring and statistics
- run theme attribution and segmented ITS robustness
- run full-corpus structural extraction for Appendix A
- regenerate manuscript LaTeX macros from JSON outputs

## Current Execution Modes

`run_pipeline.py` is intentionally focused on the downstream analysis stack (starts at Step 04).
On this Windows setup, use `py -3` rather than assuming `python` is on `PATH`.

- `py -3 run_pipeline.py`
  - Runs Steps 04-07 (bias scoring, framing, statistics, figures).
- `py -3 run_pipeline.py --paper`
  - Runs Steps 04-07 plus Step 10 (theme attribution), Step 12 (segmented ITS), and `paper/build_stats_tex.py`.
- `py -3 run_pipeline.py --paper --with-langextract`
  - Adds Step 08 structural extraction (Appendix A) to the paper run.

Steps 01-03 (load/clean/filter/attribution) are still part of the full pipeline, but are run directly when a fresh upstream rebuild is needed.

## Latest Results Snapshot

Values below reflect current outputs in:
- `output/06_stats_results.json`
- `output/08_extraction_stats.json`
- `output/10_theme_stats.json`
- `output/12_segmented_its_results.json`

Main quantitative findings (post July-2026 measurement fixes: token-based
negation, word-boundary matching, ITS transition-month correction, quote-span
masking, time-symmetric attribution filter):
- CORPUS COMPOSITION (`01_clean.parquet`): 136,313 articles across exactly 21 publications — NOT 21 Bay Area publications. Nineteen are Bay Area outlets (sfgate.com 40,888; kron4.com 14,863; San Francisco Chronicle 13,680; East Bay Times 12,264; sanfrancisco.cbslocal.com 9,572; nbcbayarea.com 9,276; abc7news.com 8,504; San Mateo Daily Journal 5,432; sfist.com 3,835; sfexaminer.com 3,011; missionlocal.org 3,004; kqed.org 2,836; berkeleyside.org 1,390; sfbayview.com 1,132; oaklandside.org 913; ktvu.com 264; alamedapost.com 169; sfstandard.com 52; independentnews.com 5). Two are NATIONAL outlets: **nytimes.com 3,884 and politico.com 1,339** (5,223 articles, 3.8% of the corpus; 395 of the 12,827 attributed articles, 3.1%). The national slice is not neutrally distributed: 306/395 (77%) are progressive-attributed vs 51% corpus-wide, and 292 concern Boudin. The paper previously named "Mercury News", "cbsnews.com", and "Palo Alto Online" as example outlets — none are in the corpus — and misspelled berkeleyside.org as berkeleyside.com; all corrected.
- 21 vs 20 OUTLETS: the full corpus spans 21 publications, but only 20 contribute at least one prosecutor-attributed article (independentnews.com, 5 articles, contributes none). That is why the publication-cluster bootstrap resamples 20 clusters, not 21. Both counts are now reconciled explicitly in the paper's Data subsection.
- Attribution fix (Step 03): the Jenkins/Price false-positive filters are now time-symmetric — every period requires the first name somewhere in the article or a title adjacent to the surname. This removed 126 post-tenure false positives (102 Jenkins, 24 Price; articles about other people with those surnames) and reassigned 26 articles; corpus is now `12,827` (Progressive 6,585 / Traditional 6,242). The old asymmetric attribution is archived at `output/archive_03_asymmetric/`.
- Composite NLP difference (Progressive minus Traditional) remains negative: Cohen d = -0.151, Welch p = 1.07e-17 (`n=6,585` vs `n=6,242`); TOST-equivalent at |d| < 0.2 (p = .0028); publication-cluster bootstrap (20 outlets) mean-difference CI [-0.0475, -0.0074], two-sided p ~ 0.011.
- Method-level pattern is stable:
  - Aspect sentiment (A): d = +0.047, p = 0.018 (nominally significant but TOST-equivalent at |d| < 0.2, p < .001 — a tiny positive tone difference bounded within equivalence)
  - Stance (B): d = -0.337, p = 4.90e-63 (TOST fails)
  - Keyword salience (C): d = -0.203, p = 7.92e-31 (TOST fails)
  - Document sentiment (D): d = +0.049, p = 0.0052 (TOST-equivalent)
- Composite OLS regression (county, year, length controls; publication-clustered SEs): is_progressive coef = -0.0205, SE = 0.0126, p = 0.104 — no longer marginally significant. Stance (coef -0.128, p < .001) and keywords (coef -0.010, p < .001) survive controls; sentiment methods do not.
- Framing differs by prosecutor type (dominant-frame chi-square = 395.66, dof = 4; Cramers V = 0.214). 51.9% of frame rows (6,652 of 12,827) come from the keyword fallback (`frame_method` column) — disclosed as a mixture-of-instruments limitation. Zero-shot-only sensitivity (6,175 model-classified articles): every differential strengthens (chi-square = 492.1, V = 0.282; reform d = 0.607, accountability d = 0.249, human-interest d = -0.413 toward traditional, conflict d = -0.119) and all five probability-score contrasts align in sign with the dominant-frame rates — the fallback attenuates and distorts, so headline framing results are conservative.
- Theme attribution (separate model, not part of A-D composite) is higher for progressive-prosecutor coverage: d = +0.418, p = 5.15e-124; quote-masked variant d = +0.404 (robust to quoted-speech exclusion); recall theme risk ratio 4.47 (18.3% vs 4.1%); 7/9 themes BH-robust.
- THEME EVENT-DECOMPOSITION (`10_theme_stats.json` -> `event_decomposition`) — the theme finding is substantially event-driven and REVERSES SIGN. All values in the progressive-minus-traditional direction (positive = higher attributed-theme load for progressives):
  - Full sample: d = +0.418, p = 5.15e-124 (n = 6,585 / 6,242)
  - Excluding articles flagged RECALL (11.4% of sample): d = +0.096, p = 5.24e-07 (n = 5,379 / 5,986)
  - Excluding articles flagged CRIME_RISING (16.2%): d = +0.300, p = 3.59e-52 (n = 5,221 / 5,525)
  - Excluding EITHER (22.9%): **d = -0.088, p = 9.24e-06 (n = 4,519 / 5,374) — sign reversal; traditional prosecutors carry a marginally higher attributed-theme load in the remaining coverage**
  - Excluding the two recall-campaign date windows (2021-06-01..2022-06-30 SF/Boudin; 2023-08-01..2024-12-31 Alameda/Price; 39.1% of sample): d = +0.197, p = 1.98e-16 (n = 3,311 / 4,503)
  - The other seven leave-one-theme-out fits are all within 0.04 of the full-sample value: +0.396 (public_safety_failure, 1.6% dropped) to +0.456 (case_dismissal, 4.9% dropped)
  - Substantive reading: both progressive prosecutors faced actual recall campaigns and no traditional prosecutor did, so recall coverage is not evidence of differential treatment; crime-rising tracks a real contemporaneous debate over crime trends. The theme layer measures event responsiveness, not like-for-like framing. Paper reframed accordingly (no longer "the study's largest effect" without qualification).
  - "LARGEST EFFECT" RECONCILED: d = +0.418 is the largest raw effect among the POOLED contrasts only. The largest raw effect anywhere in the paper is the Alameda within-county paired theme contrast, **d = 0.680** (`10_theme_stats.json` -> `paired_county/Alameda/cohens_d`; SF pair is 0.267). Every surviving "largest" claim in the manuscript — including the Figure 1 caption — is now scoped to "among the pooled contrasts" and names the 0.68 within-county value.
- Full-corpus Appendix A extraction covers `12,827` articles (12,821 after excluding 6 extraction-error articles) with `134,604` extracted instances; source-type distribution differs strongly by ideology (chi-square = 1802.11, dof = 9, p ~ 0).
- Segmented ITS (monthly, HAC-robust; transition month classified as post): SF composite level +0.031 is no longer significant (p = 0.070) — the previously nominal level shift sat exactly where the removed post-tenure false positives lived; SF composite slope p = 0.031 (BH 0.078, not robust); SF composite 12-month effect +0.069 (p = 0.0004; BH 0.0016 — survives); SF stance slope p = 0.0003 and 12-month horizon p < 0.0001 (BH-robust); Alameda composite level -0.067 (p = 0.035; BH 0.080, not robust); Alameda stance level -0.238 (p = 0.0004) and 12-month horizon -0.292 (BH-robust).
- Controlled ITS vs San Mateo (untreated county): SF level shift not distinguishable from county-general trends (+0.0285, p = 0.26; SF stance p = 0.096); Alameda shift survives the control (-0.087, p = 0.0028; Alameda stance -0.242, p = 0.0001). Stance effects remain the robust temporal finding; composite-level shifts are suggestive.
- Sensitivity excluding fallback-assigned articles strengthens the composite effect (d = -0.294; excluded 6,651 of 12,827, 51.9%). Quote-masked composite is essentially unchanged (d = -0.151). Prosecutor-focused subsample d = -0.260.
- FALLBACK OVERLAP — the framing fallback and the attribution fallback are the SAME ARTICLES, so the two corresponding sensitivity analyses are NOT independent. Crosstab of `04_bias_scores.parquet:assigned_via_generic_da_fallback` against `05_frames.parquet:frame_method` over all 12,827 analyzed articles: attribution fallback n = 6,651; framing keyword fallback n = 6,652; overlap = 6,637; only 29 articles fall on one side and not the other. Jaccard = 0.996; P(keyword frame | fallback attribution) = 0.998; P(keyword frame | named-mention attribution) = 0.002. MECHANISM: an article with no named prosecutor mention gives the frame classifier no mention window (forcing the keyword fallback) and gives name-based attribution nothing to match (forcing county-and-date assignment) — one condition, two flags. CONSEQUENCE: the zero-shot-only framing sensitivity (6,175 model-classified articles) and the exclude-fallback composite sensitivity (6,176 named-mention articles) are two instruments on one subsample, not independent corroboration. Both remain informative; the paper no longer counts them as two converging checks.
- Appendix B (Step 09 bias-indicator extraction) upsized from the 200-article pilot to a 1,000-article stratified sample (999 analyzed: 500 Progressive / 499 Traditional; 200 prior extractions reused + 800 newly drawn, seed 42; same valence-aware schema): the primary contrast is now affirmatively TOST-equivalent within |d| < 0.2 (d = -0.039, Welch p = .54, TOST p = .0055). NEW paired-county finding: Alameda Price vs O'Malley d = -0.433, p = .0095 (Price's coverage carries substantially more anti-prosecutor indicators; modest cells, n = 66/119), while the SF pair is null (d = +0.087, p = .26) — the overall equivalence masks offsetting county patterns, cohering with the controlled-ITS localization of robust effects in Alameda. A modest loaded-unfavorable differential re-emerges at this power (0.54 vs 0.36 per article, d = +0.13) but does not produce net signed-score asymmetry; convergent validity with the main pipeline is r = 0.245 (p < .001, n = 999).
- Weighting sensitivity: composite d ranges from -0.282 (evaluative-only) to +0.025 (drop-stance, p = 0.15 — a null). The composite is not robust to removing the stance method; the differential is carried by stance and keyword salience.
- Sample-composition sensitivities: prosecutor-focused subsample (>=2 named mentions or headline mention; keeps 3,999 of 12,827) d = -0.260 (p = 1.1e-16); mention-dominance subsample (>=2 mentions or headline AND primary named more often than all other prosecutors combined, including prominent non-study prosecutors; keeps 3,781 of 12,827) d = -0.267 (p = 1.3e-16); tenure-period-only (excludes 279 pre-tenure articles) d = -0.192 (p = 8.8e-27). All three relevance-based restrictions (fallback exclusion -0.294, prosecutor-focused -0.260, mention-dominance -0.267) roughly double the full-sample effect (-0.151) in the same direction. NOT independent: the three subsamples are NESTED — mention-dominance (3,781) is by construction a subset of prosecutor-focused (3,999), which is a near-subset of non-fallback (3,991 of 3,999, since >=2 named mentions implies >=1). This is one restriction at three severities, so the agreement shows the effect is monotone in relevance, not that three independent tests concur; the paper no longer calls it "convergence". NOTE also: this applies to relevance restrictions only and does NOT generalize to group composition — see the leave-one-prosecutor-out bullet below.
- LEAVE-ONE-PROSECUTOR-OUT (`06_stats_results.json` -> `leave_one_prosecutor_out`) — the pooled composite is NOT uniformly robust. Composite d, full sample = -0.151:
  - drop Chesa Boudin (Prog, SF): d = -0.150 (99% of full), stance -0.437, keywords -0.210 (n = 802 / 6,242)
  - drop Pamela Price (Prog, Alameda): d = -0.154 (102%), stance -0.330, keywords -0.207 (n = 5,783 / 6,242)
  - drop Brooke Jenkins (Trad, SF): d = -0.233 (154%), stance -0.467, keywords -0.306 (n = 6,585 / 3,145)
  - drop Nancy O'Malley (Trad, Alameda): d = -0.173 (115%), stance -0.371, keywords -0.160 (n = 6,585 / 4,745)
  - drop Steve Wagstaffe (Trad, San Mateo): **d = -0.070 (46% of full), p = 2.4e-04 — roughly halves the effect; stance drops -0.337 -> -0.206, keywords -0.203 -> -0.162** (n = 6,585 / 4,594)
  - Range across leave-one-out: [-0.233, -0.070]. Sign and direction robust in all five fits; magnitude is not. `_summary.robust_all_preserve_or_increase = false`.
  - MECHANISM: Wagstaffe is not a representative traditional prosecutor. Per-prosecutor mean composite (`04_bias_scores.parquet`): Wagstaffe +0.0396 (n=1,648) vs Jenkins -0.0175 (3,097), O'Malley -0.0156 (1,497), Price -0.0294 (802), Boudin -0.0305 (5,783). Mean stance: Wagstaffe 0.473 vs 0.279 / 0.278 (other traditionals) and 0.189 / 0.147 (progressives). He is the only San Mateo prosecutor, the only county with no transition, and supplies 26% of the traditional baseline; including him widens the pooled gap.
  - CONVERGENCE (now the organizing point in the paper): three routes that avoid cross-county comparison agree — drop-Wagstaffe d = -0.070; SF within-county (Boudin/Jenkins) d = -0.068 (p = .0020); Alameda within-county (Price/O'Malley) d = -0.069 (p = .1376). The pooled -0.151 is roughly double; the excess is cross-county heterogeneity, not ideology. d ~ -0.07 is the estimate the credible designs support; the pooled figure is an upper bound.
  - TENSION TO DISCLOSE: San Mateo/Wagstaffe both anchors ~half the pooled cross-sectional effect and is the untreated comparison series in the controlled ITS (`12_segmented_its.py`: `CONTROL_PROSECUTORS = ("Steve Wagstaffe",)`). Different estimands (the controlled ITS differences out a time trend rather than comparing levels), so not strictly circular — but one county is load-bearing in both places and there is no second untreated county.
  - Paper previously reported only the leave-Jenkins-out check (which strengthens the effect) and asserted robustness checks "all preserve or increase effect magnitudes". That assertion was false and has been corrected.
- Human validation (RA; four completed packets covering 373 distinct articles, non-blind to model labels). First-stage packet 01 (100-article stratified sample): relevance rule validated with 100% recall/precision vs the RA's 28 low-relevance articles (centrality AUC = 0.90); article-level stance agreement no better than chance (kappa = 0.049, CI [-0.08, 0.18], n = 84; model over-assigns "supportive"), but the continuous stance score is monotonically ordered in human labels (AUC = 0.69) — stance supports aggregate contrasts only, not article-level or absolute readings. Dominant-frame kappa = 0.173. Second-stage extraction audit (160 extractions, adversarially sampled so rates are conservative): span grounding 98.8% (158/160 verbatim after re-checking full article text), class precision 96.6% (source attributions 100%), attribute precision 72.4% overall with causal claims at 62.5% — class-level counts robust, attribute-based ratios noisier. Harm-label downgrades to "ambiguous": 18% progressive vs 12% traditional (no significant asymmetry — the harm differential is not manufactured by extraction error). Third-stage packet 03 (120-article stratified case-type coding, 30 per prosecutor-type x sampling-bucket cell): case-type composition does NOT differ by prosecutor type — 24/60 progressive vs 25/59 traditional articles are case-centered (Fisher exact p = .853, OR 1.10), ruling out a composition confound (progressive coverage is not disproportionately policy coverage). Coding internally consistent: binary case-centered judgment agrees with the specific-case-present indicator on 112/120 (93.3%); 7 of the 8 mismatches are case-present-but-policy-framed boundary calls the coder flagged, now under an explicit adjudication rule. Within-case-type contrasts are NOT reported: ~25-36 articles per cell gives ~0.2 power against the corpus effect, so the subgroup nulls are uninformative. Pooled relevance benchmark — now REPRODUCIBLE via `ra_langextract_validation/scripts/build_relevance_benchmark.py`, which rebuilds the flag set from the completed coding sheets under a documented note-matching rule and writes `generated/pooled_relevance_benchmark.csv`. Its output supersedes the earlier ad-hoc figures (which said 57 flagged and 20 of 57 naming a non-study prosecutor). Current values: **55 flagged articles of the 333 distinct articles covered by packets 01-03** (28 from packet 01, 15 from 02, 12 from 03); the simple rule (>=2 mentions or headline) drops 70.9% of flagged articles (Wilson CI [57.9, 81.2]) at 91.4% precision on the 185 articles it keeps, vs 100%/100% on the clean 28-article packet-01 benchmark; residual failures are articles naming the attributed prosecutor repeatedly while being about another prosecutor (Gascon/Harris/Rosen named in **19 of the 55**). The stricter mention-dominance rule reaches 83.6% dropped (CI [71.7, 91.1]) at 94.5% precision on the 163 articles it keeps, matching perfect packet-01 separation, and yields the d = -0.267 sensitivity (3,781 articles retained corpus-wide) — but it was developed on these same flags, so it is in-sample; out-of-sample confirmation pending. Fourth-stage packet 04 (40-article extraction-RECALL audit, 20 progressive / 20 traditional; the only packet measuring false negatives — the coder saw an article excerpt plus the model's extraction list and counted attributed sources and causal claims in the excerpt the model failed to capture): 80 missed sources vs only 9 missed causal claims (90% of all missed items are source attributions), with 30/40 articles containing at least one missed source — the recall problem is concentrated in source capture, not causal-claim capture. False-negative rate for sources is bracketed at 28-34% because the denominator is ambiguous: 27.7% naive (all 209 model extractions counted as true positives) vs 33.6% corrected (only the 158 extractions verifiably inside the visible excerpt count; 95% Wilson CI [27.9, 39.8]); causal claims 31-39% (naive 31.0%, corrected 39.1%, CI [22.2, 59.2], on only 9 missed items so imprecise). Symmetry is the load-bearing test and it is a null: missed sources per article 1.55 (Progressive, n=20) vs 2.45 (Traditional, n=20), Welch p = .310; missed causal claims 0.15 vs 0.30, p = .268 — no detectable asymmetry, so differential recall failure does not appear to manufacture the Appendix A source-ecology differential (point estimates run toward MORE missed sources in traditional coverage, which if real would inflate rather than create the gap, but 20 per group is badly underpowered). WHAT gets missed is systematic: unnamed and documentary attribution ("authorities", "investigators", "officials", court records, jail records, court testimony, the motion, the suit, newspaper reports, the coroner), while named directly-quoted individuals are reliably captured — so absolute source-type composition shares understate documentary/institutional attribution while between-group ratios stay robust. Packet-builder bug the coder caught independently: Step 08 ran the model on the first ~3,000 words but the packet displayed only the first 8 paragraphs (max 6,000 chars), so 101 of 359 listed extractions (28.1%) lay outside the visible text; all 101 were verified present in the full article (consistent with the 98.8% packet-02 grounding result), so this is packet construction, not ungrounded extraction. `scripts/build_ra_packets.py` now lists only extractions grounded in the displayed excerpt; this bug is why the recall rate is bracketed rather than point-estimated. Verify with `py -3 scripts/analyze_completed_04.py` from `ra_langextract_validation/`.
- Manuscript figures that had NO source file and are now computed (previously hand-typed):
  - Table 3 source-stance Cohen's d. `08_extraction_stats.json` contains no `cohens_d` field at all; the paper's 0.14 / 0.22 / -0.20 were unsourced. Recomputed as pooled-SD Cohen's d on per-article stance-labeled source counts from `08_extractions_summary.parquet` (12,821 non-error articles; 6,585 Progressive / 6,236 Traditional): critical **+0.146**, supportive **+0.217**, neutral **-0.212** (printed as +0.15 / +0.22 / -0.21). Per-article means match the existing macros (1.71/1.28, 1.42/0.95, 3.18/3.89).
  - Police-vs-prosecutor mention rates in the literature review (was "82% vs 15%", no source, no script). Computed over the 107,713 relevance-filtered articles in `03_all_relevant_attributed.parquet`, matching headline+body with word boundaries: police/officer(s)/sheriff/deputy/deputies/law enforcement/detective(s)/highway patrol = 89,471 (**83.1%**); district attorney / D.A. / DA's office = 16,717 (**15.5%**). Tighter police definition gives 79.4%; broadening the prosecutor side to include "prosecutor(s)" gives 24.7%. Operationalization is stated in a footnote in the paper.
  - Appendix C theme example: the kron4.com "Boudin Blunders" article (2022-06-08) scores **17.19**, not 21.3, and is NOT the corpus maximum — that is **17.50**, for the San Francisco Chronicle article "Boudin might be in trouble if poll holds" (2022-03-16). No article in `10_theme_attribution.parquet` scores 21.3.
  - Appendix C Method C example: the berkeleyside.org O'Malley article (article_id 1, 2021-07-18) triggers **two** themes, not three — releasing_criminals and recall. soft_on_crime does not fire: the article's phrase is "light sentences" (plural) and the dictionary entry is the singular "light sentence" under word-boundary matching.
  - Appendix C frame table, Reform row: "As new D.A., Jenkins vows to be tougher than Boudin" has frame_reform = 0.9741 but `dominant_frame` = **accountability**, so it did not belong in a dominant-frame exemplar table. Replaced with "Contrasting front-runners for D.A. stake out stances..." (San Francisco Chronicle, 2019-11-01, Boudin), whose dominant_frame IS reform (frame_reform = 0.9981).
- Multiple comparisons: BH-adjusted p-values reported per test family. Frames (4/5) and themes (7/9) survive; segmented-ITS composite level/slope effects do NOT survive BH across the 30-test family (SF composite level is now non-significant even before BH, p = 0.070; the others land at p_BH ~ 0.078-0.080) — the surviving ITS effects are the stance/keyword slope and 12-month horizon effects plus the SF composite 12-month effect.

Interpretation note: negative composite values indicate relatively more critical coverage in this scoring convention.

## Pipeline Map

```text
01_load_and_clean.py         -> output/01_clean.parquet
02_filter_relevant.py        -> output/02_relevant.parquet
03_attribute_prosecutors.py  -> output/03_attributed.parquet
04_bias_detection.py         -> output/04_bias_scores.parquet
05_framing_analysis.py       -> output/05_frames.parquet
06_statistics.py             -> output/06_stats_results.json, output/06_regression_tables.csv
07_visualize.py              -> output/figures/01..17 png files
08_langextract_analysis.py   -> output/08_extractions.jsonl + output/08_extraction_stats.json
09_bias_extraction.py        -> output/09_bias_extractions.jsonl + output/09_bias_stats.json
10_theme_attribution.py      -> output/10_theme_attribution.parquet + output/10_theme_stats.json
11_extract_examples.py       -> output/11_appendix_c_examples.md
12_segmented_its.py          -> output/12_segmented_its_results.json + output/12_segmented_its_table.csv + paper/figures/18_segmented_its.png
paper/build_stats_tex.py     -> paper/generated_stats.tex
```

## Measurement Layers (How Methods Relate)

- Methods A-D (`04_bias_detection.py`) are the directional evaluative layer used for the main composite:
  - A: aspect sentiment
  - B: stance classification
  - C: keyword-based anti-prosecutor thematic salience
  - D: document sentiment baseline
- Composite score is built from A-D only with fixed weights:
  - A 0.35, B 0.30, C 0.20, D 0.15
- Framing (`05_framing_analysis.py`) is a separate categorical layer and is not included in the composite.
- Theme attribution (`10_theme_attribution.py`) is a separate prosecutor-linked theme model and is not included in the composite.
- Structural extraction (`08_langextract_analysis.py`) is a separate content-structure layer (sources, claims, causal links, policy actions, comparisons).
- Temporal robustness is modeled with segmented ITS (`12_segmented_its.py`), with full coefficients in JSON/CSV outputs.

## Setup

Requirements:
- Python 3.10+
- `py -3 -m pip install -r requirements.txt`
- `LANGEXTRACT_API_KEY` set for Steps 08 and 09

## Typical Commands

Core run:

```bash
py -3 run_pipeline.py
```

Publication lock run (recommended for manuscript refresh):

```bash
py -3 run_pipeline.py --paper --with-langextract
```

If extraction is resumed over multiple runs:

```bash
py -3 08_langextract_analysis.py --resume --max-articles 1800 --delay 0.5
```

## Manuscript Build

Stats macros are generated from JSON outputs:

```bash
py -3 paper/build_stats_tex.py
```

Compile manuscript:

```bash
cd paper
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

## Repository Notes

- The raw corpus TSV is not included in this repository due to licensing restrictions.
- Output JSON files in `output/` are the source of truth for current reported values.
- The manuscript prefers figures from `output/figures/` and falls back to tracked copies in `paper/figures/`.
- `paper/generated_stats.tex` is generated; do not edit by hand.
