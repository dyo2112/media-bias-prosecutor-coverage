# Measuring Media Bias Toward Reform Prosecutors

This repository contains the analysis pipeline and manuscript assets for a multi-method NLP study of Bay Area prosecutor coverage.

The current publication workflow is:
- run core NLP scoring and statistics
- run theme attribution and segmented ITS robustness
- run full-corpus structural extraction for Appendix A
- regenerate manuscript LaTeX macros from JSON outputs

## Current Execution Modes

`run_pipeline.py` is intentionally focused on the downstream analysis stack (starts at Step 04).

- `python run_pipeline.py`
  - Runs Steps 04-07 (bias scoring, framing, statistics, figures).
- `python run_pipeline.py --paper`
  - Runs Steps 04-07 plus Step 10 (theme attribution), Step 12 (segmented ITS), and `paper/build_stats_tex.py`.
- `python run_pipeline.py --paper --with-langextract`
  - Adds Step 08 structural extraction (Appendix A) to the paper run.

Steps 01-03 (load/clean/filter/attribution) are still part of the full pipeline, but are run directly when a fresh upstream rebuild is needed.

## Latest Results Snapshot

Values below reflect current outputs in:
- `output/06_stats_results.json`
- `output/08_extraction_stats.json`
- `output/10_theme_stats.json`
- `output/12_segmented_its_results.json`

Main quantitative findings:
- Composite NLP difference (Progressive minus Traditional) remains negative: Cohen d = -0.157, Welch p = 4.05e-19 (`n=6,601` vs `n=6,352`).
- Method-level pattern is stable:
  - Aspect sentiment (A): d = +0.037, p = 0.058
  - Stance (B): d = -0.341, p = 1.08e-64
  - Keyword salience (C): d = -0.218, p = 1.91e-35
  - Document sentiment (D): d = +0.047, p = 0.008
- Framing differs by prosecutor type (dominant-frame chi-square = 443.75, dof = 4, p = 9.77e-95; Cramers V = 0.225).
- Theme attribution (separate model, not part of A-D composite) is higher for progressive-prosecutor coverage: d = +0.425, p = 3.42e-128.
- Full-corpus Appendix A extraction covers `12,953` articles with `135,178` extracted instances; source-type distribution differs strongly by ideology (chi-square = 1720.27, dof = 9, p ~ 0).
- Segmented ITS (monthly, HAC-robust) shows a +0.063 12-month composite effect after the SF transition (p = 0.001) and a -0.065 effect after the Alameda transition (p = 0.025).
- Sensitivity excluding fallback-assigned articles strengthens the composite effect (d = -0.310; excluded 6,630 of 12,953, 51.2%).

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
- `pip install -r requirements.txt`
- `LANGEXTRACT_API_KEY` set for Steps 08 and 09

## Typical Commands

Core run:

```bash
python run_pipeline.py
```

Publication lock run (recommended for manuscript refresh):

```bash
python run_pipeline.py --paper --with-langextract
```

If extraction is resumed over multiple runs:

```bash
python 08_langextract_analysis.py --resume --max-articles 1800 --delay 0.5
```

## Manuscript Build

Stats macros are generated from JSON outputs:

```bash
python paper/build_stats_tex.py
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
- `paper/generated_stats.tex` is generated; do not edit by hand.
