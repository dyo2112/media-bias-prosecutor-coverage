# Measuring Media Bias Toward Reform Prosecutors

**A Multi-Method NLP Analysis of Bay Area News Coverage, 2019–2024**

This repository contains the complete analysis pipeline for a research paper measuring systematic differences in how Bay Area news media covers progressive versus traditional district attorneys. The pipeline processes 136,313 news articles across 21 publications and applies five complementary NLP methods to five prosecutors spanning the progressive–traditional spectrum.

## Key Findings

- **Evaluative framing differs, emotional tone does not.** Progressive prosecutors receive substantially more critical *stance* coverage (Cohen's *d* = −0.34) but nearly identical *sentiment* scores (*d* = 0.037). Media bias is not unitary — tone and framing are empirically independent dimensions.
- **Accountability framing is 2× more frequent** for progressive prosecutors. Traditional prosecutors receive more human-interest framing. The press covers reform prosecutors differently *in kind* rather than in degree.
- **Effects surge during recall campaigns** and are confirmed by within-county comparisons (same outlet, same jurisdiction, different prosecutor).
- **Source ecology drives structural differences.** Progressive prosecutor coverage draws on 2× more advocacy group sources, 1.9× more expert sources, and 1.8× more politician quotes — the empirical fingerprint of institutional mobilization ("toplash").

## Prosecutors Analyzed

| Prosecutor | County | Ideology | Tenure |
|---|---|---|---|
| Chesa Boudin | San Francisco | Progressive | Jan 2020 – Jul 2022 |
| Brooke Jenkins | San Francisco | Traditional | Jul 2022 – present |
| Pamela Price | Alameda | Progressive | Jan 2023 – 2025 |
| Nancy O'Malley | Alameda | Traditional | Sep 2009 – Jan 2023 |
| Steve Wagstaffe | San Mateo | Traditional | Apr 2010 – present |

## Pipeline Architecture

The pipeline is a sequence of 11 Python scripts, each reading the previous step's output and producing structured artifacts (parquet files, JSON stats, figures). Steps 01–07 form the core NLP pipeline; Steps 08–11 produce appendix-level analyses.

```
Raw TSV corpus (136K articles)
    │
    ├── 01_load_and_clean.py        → 01_clean.parquet
    │     Deduplication, date parsing, text normalization
    │
    ├── 02_filter_relevant.py       → 02_relevant.parquet
    │     BART-MNLI zero-shot classifier: "This article is about
    │     crime, criminal justice, or law enforcement" (threshold 0.5)
    │
    ├── 03_attribute_prosecutors.py  → 03_attributed.parquet
    │     Name-variant matching with temporal windowing +
    │     disambiguation logic (e.g., bare "Price" near Alameda context)
    │
    ├── 04_bias_detection.py        → 04_bias_scores.parquet
    │     Three sub-methods per article:
    │     A) RoBERTa aspect-based sentiment (3-sentence windows)
    │     B) BART-MNLI zero-shot stance ("critical of" / "supportive of")
    │     C) Enhanced keyword theme detection (9 anti-prosecutor themes
    │        matched within 3-sentence windows, with negation filtering)
    │
    ├── 05_framing_analysis.py      → 05_frames.parquet
    │     BART-MNLI zero-shot framing across 5 media frames:
    │     accountability, conflict, human interest, economic, morality
    │
    ├── 06_statistics.py            → 06_stats_results.json
    │     Cohen's d, t-tests, Mann-Whitney U, bootstrap CIs,
    │     OLS/logistic regression, paired-county comparisons,
    │     temporal heterogeneity analysis
    │
    ├── 07_visualize.py             → 17 publication-quality figures
    │     Violin plots, forest plots, heatmaps, time series,
    │     regression coefficient plots, method comparison dashboards
    │
    ├── 08_langextract_analysis.py  → 08_extractions.jsonl  [Appendix A]
    │     Gemini 2.5 Flash structured extraction via langextract:
    │     source attributions, claims, causal assertions, policy
    │     actions, prosecutor comparisons — all grounded to text spans
    │
    ├── 09_bias_extraction.py       → 09_bias_extractions.jsonl  [Appendix B]
    │     LLM-based bias indicator detection: ungrounded claims,
    │     source prominence imbalance, loaded language, missing context
    │     (pilot study, n=200)
    │
    ├── 10_theme_attribution.py     → 10_theme_attribution.parquet
    │     Multi-method theme detection (keywords + BART-MNLI + hybrid)
    │     with per-prosecutor paired Cohen's d
    │
    └── 11_extract_examples.py      → 11_appendix_c_examples.md  [Appendix C]
          Extracts illustrative examples at score extremes for each
          method to make the measurement pipeline tangible
```

## NLP Methods

### Method A: Aspect-Based Sentiment Analysis
**Model:** `cardiffnlp/twitter-roberta-base-sentiment-latest`

Extracts 3-sentence context windows around each prosecutor mention and scores sentiment on a continuous negative–positive scale. Captures *emotional tone* — how charged the surrounding language is — regardless of argumentative direction.

### Method B: Zero-Shot Stance Classification
**Model:** `facebook/bart-large-mnli`

Classifies each article's stance toward the named prosecutor using hypothesis templates:
- *"This article is critical of [Prosecutor]"*
- *"This article is supportive of [Prosecutor]"*

The stance score (critical − supportive probability) captures *evaluative framing* — whether the article positions the prosecutor favorably or unfavorably — independent of emotional tone.

### Method C: Enhanced Keyword Theme Detection
Matches 9 anti-prosecutor themes (crime rising, soft on crime, releasing criminals, case dismissal, victim neglect, police conflict, office dysfunction, recall, public safety failure) within 3-sentence windows around prosecutor mentions. Includes negation filtering to avoid false positives from defensive/rebuttal language.

### Method D: Document-Level Sentiment
**Model:** `cardiffnlp/twitter-roberta-base-sentiment-latest`

Whole-article sentiment analysis for each prosecutor-attributed article. Provides a broad emotional-tone baseline at the document level.

### Method E: Media Framing Analysis
**Model:** `facebook/bart-large-mnli`

Zero-shot classification across five standard media frames (accountability, conflict, human interest, economic consequences, morality). Each article receives a dominant frame assignment plus continuous probability scores.

### Composite Score
A normalized, equally-weighted average of Methods A–E that integrates all measurement dimensions into a single per-article bias indicator.

## LLM-Based Extraction (Appendices A & B)

Steps 08 and 09 use [langextract](https://github.com/google/langextract) with Gemini 2.5 Flash for structured information extraction. Every extraction is grounded to an exact text span in the source article.

**Appendix A** (structural extraction) decomposes articles into discrete elements:
- **Source attributions** — who is quoted, their role, and stance toward the prosecutor
- **Claims against the prosecutor** — type, specificity, and evidence quality
- **Causal claims** — linking prosecutor actions to outcomes
- **Policy actions** — concrete decisions with domain and framing
- **Comparisons** — between current and predecessor prosecutors

**Appendix B** (bias indicator pilot) detects journalistic quality violations:
- **Ungrounded negative claims** — assertions without adequate evidence
- **Source prominence imbalance** — disproportionate sourcing
- **Loaded language** — presuppositional verbs, ideological framing, hyperbole
- **Missing context** — material omissions that distort the story

Both extraction schemas include carefully designed few-shot examples and calibration guidance. Full prompts and examples are documented in the paper's appendices.

## Repository Structure

```
├── 01_load_and_clean.py          # Step 1: data loading and deduplication
├── 02_filter_relevant.py         # Step 2: relevance filtering (BART-MNLI)
├── 03_attribute_prosecutors.py   # Step 3: prosecutor name attribution
├── 04_bias_detection.py          # Step 4: sentiment, stance, keywords
├── 05_framing_analysis.py        # Step 5: media frame classification
├── 06_statistics.py              # Step 6: statistical analysis
├── 07_visualize.py               # Step 7: figure generation
├── 08_langextract_analysis.py    # Step 8: structural extraction (App. A)
├── 09_bias_extraction.py         # Step 9: bias indicators (App. B)
├── 10_theme_attribution.py       # Step 10: theme detection
├── 11_extract_examples.py        # Step 11: illustrative examples (App. C)
├── config.py                     # Paths, models, prosecutor metadata, keywords
├── utils.py                      # Logging, I/O helpers
├── requirements.txt              # Python dependencies
├── run_pipeline.py               # End-to-end pipeline runner
├── paper/
│   ├── main.tex                  # LaTeX manuscript source
│   ├── main.pdf                  # Compiled paper
│   ├── references.bib            # Bibliography
│   └── figures/                  # All 17 publication figures
└── output/
    ├── 06_stats_results.json     # Full statistical results
    ├── 06_regression_tables.csv  # Regression coefficients
    ├── 08_extraction_stats.json  # Langextract aggregate stats
    ├── 09_bias_stats.json        # Bias indicator stats
    └── 10_theme_stats.json       # Theme attribution stats
```

## Setup

### Requirements
- Python 3.10+
- GPU recommended for transformer steps (02, 04, 05); CPU works but is slow
- Gemini API key for steps 08–09 (set `LANGEXTRACT_API_KEY` env var)

### Installation

```bash
pip install -r requirements.txt
```

### Data

The raw corpus (`24.07.29_complete_corpus_api_lexis_combined.tsv`) contains 136,313 articles from 21 Bay Area publications, collected via LexisNexis Academic and news APIs. The corpus is not included in this repository due to licensing restrictions. Paths are configured in `config.py`.

### Running the Pipeline

**Full pipeline:**
```bash
python run_pipeline.py
```

**Individual steps:**
```bash
python 01_load_and_clean.py
python 02_filter_relevant.py
python 03_attribute_prosecutors.py
python 04_bias_detection.py              # keywords only: --keywords-only
python 05_framing_analysis.py
python 06_statistics.py
python 07_visualize.py                   # specific figures: --figures 1 2 3
python 08_langextract_analysis.py        # resume: --resume; cap: --max-articles 1800
python 09_bias_extraction.py --sample 200
python 10_theme_attribution.py
python 11_extract_examples.py
```

**LLM extraction with RPD limits:**
```bash
# Gemini 2.5 Flash has a 10K requests/day limit (~2K articles/day).
# Use --max-articles and --resume for multi-day extraction:
python 08_langextract_analysis.py --resume --max-articles 1800 --delay 0.5
```

## Citation

Paper citation forthcoming. For now:

```bibtex
@unpublished{mediabias2026,
  title={Measuring Media Bias Toward Reform Prosecutors:
         A Multi-Method {NLP} Analysis of Bay Area News Coverage, 2019--2024},
  author={[Author]},
  year={2026},
  note={Working paper}
}
```

## License

Analysis code is provided for academic reproducibility. The underlying news article corpus is subject to LexisNexis and individual publisher licensing terms and is not redistributable.
