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
- Full-corpus Appendix A extraction covers `12,827` articles (12,821 after excluding 6 extraction-error articles) with `134,604` extracted instances; source-type distribution differs strongly by ideology (chi-square = 1802.11, dof = 9, p ~ 0).
- Segmented ITS (monthly, HAC-robust; transition month classified as post): SF composite level +0.031 is no longer significant (p = 0.070) — the previously nominal level shift sat exactly where the removed post-tenure false positives lived; SF composite slope p = 0.031 (BH 0.078, not robust); SF composite 12-month effect +0.069 (p = 0.0004; BH 0.0016 — survives); SF stance slope p = 0.0003 and 12-month horizon p < 0.0001 (BH-robust); Alameda composite level -0.067 (p = 0.035; BH 0.080, not robust); Alameda stance level -0.238 (p = 0.0004) and 12-month horizon -0.292 (BH-robust).
- Controlled ITS vs San Mateo (untreated county): SF level shift not distinguishable from county-general trends (+0.0285, p = 0.26; SF stance p = 0.096); Alameda shift survives the control (-0.087, p = 0.0028; Alameda stance -0.242, p = 0.0001). Stance effects remain the robust temporal finding; composite-level shifts are suggestive.
- Sensitivity excluding fallback-assigned articles strengthens the composite effect (d = -0.294; excluded 6,651 of 12,827, 51.9%). Quote-masked composite is essentially unchanged (d = -0.151). Prosecutor-focused subsample d = -0.260.
- Appendix B (Step 09 bias-indicator extraction) upsized from the 200-article pilot to a 1,000-article stratified sample (999 analyzed: 500 Progressive / 499 Traditional; 200 prior extractions reused + 800 newly drawn, seed 42; same valence-aware schema): the primary contrast is now affirmatively TOST-equivalent within |d| < 0.2 (d = -0.039, Welch p = .54, TOST p = .0055). NEW paired-county finding: Alameda Price vs O'Malley d = -0.433, p = .0095 (Price's coverage carries substantially more anti-prosecutor indicators; modest cells, n = 66/119), while the SF pair is null (d = +0.087, p = .26) — the overall equivalence masks offsetting county patterns, cohering with the controlled-ITS localization of robust effects in Alameda. A modest loaded-unfavorable differential re-emerges at this power (0.54 vs 0.36 per article, d = +0.13) but does not produce net signed-score asymmetry; convergent validity with the main pipeline is r = 0.245 (p < .001, n = 999).
- Weighting sensitivity: composite d ranges from -0.282 (evaluative-only) to +0.025 (drop-stance, p = 0.15 — a null). The composite is not robust to removing the stance method; the differential is carried by stance and keyword salience.
- Sample-composition sensitivities: prosecutor-focused subsample (>=2 named mentions or headline mention; keeps 3,999 of 12,827) d = -0.260 (p = 1.1e-16); mention-dominance subsample (>=2 mentions or headline AND primary named more often than all other prosecutors combined, including prominent non-study prosecutors; keeps 3,781 of 12,827) d = -0.267 (p = 1.3e-16); tenure-period-only (excludes 279 pre-tenure articles) d = -0.192 (p = 8.8e-27). All three relevance-based restrictions (fallback exclusion -0.294, prosecutor-focused -0.260, mention-dominance -0.267) roughly double the full-sample effect (-0.151) in the same direction.
- Human validation (RA; four completed packets covering 373 distinct articles, non-blind to model labels). First-stage packet 01 (100-article stratified sample): relevance rule validated with 100% recall/precision vs the RA's 28 low-relevance articles (centrality AUC = 0.90); article-level stance agreement no better than chance (kappa = 0.049, CI [-0.08, 0.18], n = 84; model over-assigns "supportive"), but the continuous stance score is monotonically ordered in human labels (AUC = 0.69) — stance supports aggregate contrasts only, not article-level or absolute readings. Dominant-frame kappa = 0.173. Second-stage extraction audit (160 extractions, adversarially sampled so rates are conservative): span grounding 98.8% (158/160 verbatim after re-checking full article text), class precision 96.6% (source attributions 100%), attribute precision 72.4% overall with causal claims at 62.5% — class-level counts robust, attribute-based ratios noisier. Harm-label downgrades to "ambiguous": 18% progressive vs 12% traditional (no significant asymmetry — the harm differential is not manufactured by extraction error). Third-stage packet 03 (120-article stratified case-type coding, 30 per prosecutor-type x sampling-bucket cell): case-type composition does NOT differ by prosecutor type — 24/60 progressive vs 25/59 traditional articles are case-centered (Fisher exact p = .853, OR 1.10), ruling out a composition confound (progressive coverage is not disproportionately policy coverage). Coding internally consistent: binary case-centered judgment agrees with the specific-case-present indicator on 112/120 (93.3%); 7 of the 8 mismatches are case-present-but-policy-framed boundary calls the coder flagged, now under an explicit adjudication rule. Within-case-type contrasts are NOT reported: ~25-36 articles per cell gives ~0.2 power against the corpus effect, so the subgroup nulls are uninformative. Pooled relevance benchmark (RA flagged low-relevance/wrong-target articles unprompted in each of the first three packets — 57 flagged of the 333 distinct articles those three cover): the simple rule (>=2 mentions or headline) drops 72% of flagged articles at 91% precision (share of retained articles genuinely prosecutor-focused), vs 100%/100% on the clean 28-article packet-01 benchmark; residual failures are articles naming the attributed prosecutor repeatedly while being about another prosecutor (Gascon/Harris/Rosen named in 20 of the 57). The stricter mention-dominance rule reaches 84% dropped at 94% precision, matching perfect packet-01 separation, and yields the new d = -0.267 sensitivity (3,781 articles retained) — but it was developed on these same flags, so it is in-sample; out-of-sample confirmation pending. Fourth-stage packet 04 (40-article extraction-RECALL audit, 20 progressive / 20 traditional; the only packet measuring false negatives — the coder saw an article excerpt plus the model's extraction list and counted attributed sources and causal claims in the excerpt the model failed to capture): 80 missed sources vs only 9 missed causal claims (90% of all missed items are source attributions), with 30/40 articles containing at least one missed source — the recall problem is concentrated in source capture, not causal-claim capture. False-negative rate for sources is bracketed at 28-34% because the denominator is ambiguous: 27.7% naive (all 209 model extractions counted as true positives) vs 33.6% corrected (only the 158 extractions verifiably inside the visible excerpt count; 95% Wilson CI [27.9, 39.8]); causal claims 31-39% (naive 31.0%, corrected 39.1%, CI [22.2, 59.2], on only 9 missed items so imprecise). Symmetry is the load-bearing test and it is a null: missed sources per article 1.55 (Progressive, n=20) vs 2.45 (Traditional, n=20), Welch p = .310; missed causal claims 0.15 vs 0.30, p = .268 — no detectable asymmetry, so differential recall failure does not appear to manufacture the Appendix A source-ecology differential (point estimates run toward MORE missed sources in traditional coverage, which if real would inflate rather than create the gap, but 20 per group is badly underpowered). WHAT gets missed is systematic: unnamed and documentary attribution ("authorities", "investigators", "officials", court records, jail records, court testimony, the motion, the suit, newspaper reports, the coroner), while named directly-quoted individuals are reliably captured — so absolute source-type composition shares understate documentary/institutional attribution while between-group ratios stay robust. Packet-builder bug the coder caught independently: Step 08 ran the model on the first ~3,000 words but the packet displayed only the first 8 paragraphs (max 6,000 chars), so 101 of 359 listed extractions (28.1%) lay outside the visible text; all 101 were verified present in the full article (consistent with the 98.8% packet-02 grounding result), so this is packet construction, not ungrounded extraction. `scripts/build_ra_packets.py` now lists only extractions grounded in the displayed excerpt; this bug is why the recall rate is bracketed rather than point-estimated. Verify with `py -3 scripts/analyze_completed_04.py` from `ra_langextract_validation/`.
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
