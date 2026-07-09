# RA Langextract Validation Workspace

This folder is for manual validation and follow-up analysis of the Step 08
structural extraction only:

- Main text Section 4.8
- Appendix A (`LLM-Based Structural Content Extraction`)

Do not use this folder for Step 09 / Appendix B (`09_bias_extraction.py`).

If you cloned this repository from GitHub and cannot find the article-level
files, see `DATA_ACCESS.md` first. Those files are intentionally excluded from
GitHub because they contain licensed article text or article excerpts.

## Blinding Design (Read First)

The RA is blinded to the study hypotheses and to all model outputs:

- RA-facing packets (`generated/<coder_id>/*.csv`) contain only article or
  extraction content plus empty `ra_*` columns. They contain NO
  `prosecutor_type`, NO stance/frame/bias model outputs, NO structural counts,
  NO heuristic flags, and NO sampling-bucket labels.
- All of those go to PI-side key files:
  `generated/keys/<packet>_KEY_<coder_id>.csv`, joined back on `packet_id` by
  `scripts/summarize_ra_labels.py` at summary time.
- Key files, `summary/`, and `adjudication/` must NEVER be shared with the RA.
- `ANNOTATION_GUIDE.md` is the only document the RA should see from this
  folder. It does not mention the hypothesis groups; keep it that way.
- `build_ra_packets.py` hard-fails (`assert_blinded`) if a forbidden column
  ever ends up in an RA-facing packet.

## The Four Packets

### 1. `01_article_validation_sample.csv` - stance and framing

~100 articles. The RA labels overall article stance, dominant frame (plus a
forced choice among the five model frames), primary issue, whether the
prosecutor is a main subject, and discourse-condition flags (quoted criticism,
balanced reporting, implicit causal language).

Sampling: two purposive buckets (high-contestation / high-self-quote) and two
random buckets, recorded only in the key file. Headline agreement figures come
from the random buckets; purposive buckets are reported separately.

### 2. `02_extraction_review_sample.csv` - extraction precision

Extraction-level audit. Buckets (sizes are CLI flags): schema drift (40),
source_attribution (60), causal_claim (60), claim_against_prosecutor (20),
policy_action (20), comparison (20). Each class bucket is half purposive
(priority heuristics) and half random. An extraction sampled into one bucket
is excluded from later pools, so no duplicate rows.

### 3. `03_case_type_coding_sample.csv` - case-type subgroup coding

~120 articles for offense-mix coding, supporting later within-case-mix
robustness checks.

### 4. `04_extraction_recall_sample.csv` - missed content (recall)

~40 articles sampled at article level, stratified by prosecutor type (stratum
recorded in the key file only). The RA sees a long excerpt plus ALL model
extractions for the article and counts missed sources and missed causal
claims. The summarizer turns these into per-class false-negative rates.

## Multi-Coder Workflow

- Build each coder's packets with `--coder-id` (files land in
  `generated/<coder_id>/`).
- A seeded overlap subset (`--overlap-fraction`, default 0.2) of every random
  bucket is identical across coders; purposive rows are deterministic and also
  shared. `packet_id` is derived from `article_id` (+ extraction index), so
  the same unit matches across coders.
- When completed files from 2+ coders exist, `summarize_ra_labels.py` computes
  inter-coder Cohen's kappa on the shared rows and writes disagreements to
  `adjudication/<packet>_disagreements.csv` with empty `adjudicated_*` columns
  for the PI to fill.

## Files In This Folder

- `ANNOTATION_GUIDE.md`
  - Coding rules and label definitions. RA-facing; contains no hypothesis or
    model information.
- `DATA_ACCESS.md`
  - Data-sharing rules, including which files may never reach the RA.
- `scripts/build_ra_packets.py`
  - Generates blinded RA packets + PI-side key files from the licensed
    `output/` files.
- `scripts/summarize_ra_labels.py`
  - Joins completed sheets with key files; reports per-bucket agreement,
    Cohen's kappa with seeded bootstrap CIs, threshold sensitivity, recall
    false-negative rates, and inter-coder reliability.
- `templates/`
  - Header-only templates showing the expected RA-facing columns.
- `generated/`
  - Local packets (`<coder_id>/`) and PI-side keys (`keys/`). Ignored by Git.
- `completed/`
  - RA-completed files. Ignored by Git.
- `summary/`
  - PI-side summaries. Ignored by Git.
- `adjudication/`
  - PI-side inter-coder disagreement sheets. Ignored by Git.

## Important Data Boundary

The repository does not version raw article text for licensing reasons.

That means:

- the committed folder includes instructions, scripts, and templates
- the actual review packets are generated locally from the existing
  `output/*.parquet` and `output/08_extractions.jsonl` files
- the generated CSVs include article excerpts and therefore stay out of Git

## Required Local Inputs

These files must exist locally before you build packets:

- `output/03_attributed.parquet` (articles, prosecutor attribution)
- `output/04_bias_scores.parquet` (key files only: `score_stance`,
  `composite_bias_score`)
- `output/05_frames.parquet` (key files only: `dominant_frame`,
  `frame_method` when present)
- `output/08_extractions.jsonl`
- `output/08_extractions_summary.parquet`

RA-facing content comes from Step 03 + Step 08; Step 04/05 model outputs are
used only in the PI-side key files.

## How To Generate The Packets

From the repository root:

```bash
py -3 ra_langextract_validation/scripts/build_ra_packets.py --coder-id ra1
```

This writes:

- `ra_langextract_validation/generated/ra1/01_article_validation_sample.csv`
- `ra_langextract_validation/generated/ra1/02_extraction_review_sample.csv`
- `ra_langextract_validation/generated/ra1/03_case_type_coding_sample.csv`
- `ra_langextract_validation/generated/ra1/04_extraction_recall_sample.csv`
- `ra_langextract_validation/generated/keys/<packet>_KEY_ra1.csv` (PI-only)

For a second coder:

```bash
py -3 ra_langextract_validation/scripts/build_ra_packets.py --coder-id ra2
```

Useful flags: `--article-sample-size`, `--case-sample-size`,
`--recall-sample-size`, `--drift-sample-size`, `--source-sample-size`,
`--causal-sample-size`, `--claim-sample-size`, `--policy-sample-size`,
`--comparison-sample-size`, `--seed`, `--overlap-fraction`.

## How The RA Works

1. The PI sends the RA only `generated/<coder_id>/*.csv` and
   `ANNOTATION_GUIDE.md` (see `DATA_ACCESS.md` for licensing constraints).
2. The RA fills only the `ra_*` columns.
3. Completed files go to `completed/`, keeping the coder id, as either
   `completed/<coder_id>/<packet>_completed.csv` or
   `completed/<packet>_completed_<coder_id>.csv`.
   A bare `completed/<packet>_completed.csv` is treated as coder `ra1`.

## How To Summarize Completed Coding

```bash
py -3 ra_langextract_validation/scripts/summarize_ra_labels.py
```

Writes `summary/ra_validation_summary.md` plus per-coder CSV tables
(confusions, per-bucket agreement, threshold sensitivity) and, with 2+ coders,
`adjudication/<packet>_disagreements.csv`.

Reporting conventions:

- Headline agreement figures use the RANDOM buckets only
  (corpus-representative); purposive buckets are reported separately.
- Cohen's kappa (hand-rolled, dependency-free) is shown next to percent
  agreement, with seeded bootstrap 95% CIs.
- RA frame labels of `mixed`/`other` are excluded from the exact-match frame
  rate (share reported separately); `ra_dominant_frame_forced` gives the
  head-to-head five-frame comparison.
- The stance bucket thresholds (+/-0.15 default, sensitivity at
  +/-0.10/0.15/0.20) are validation-harness definitions declared in
  `build_ra_packets.py`, not pipeline definitions.
- `unclear` answers are excluded from agreement rates and counted separately.
- Labels are normalized (lowercase, trimmed) and validated; invalid values are
  reported and excluded.

## Current Manuscript Context

The Step 08 structural extraction supports the claim that coverage differs
across prosecutor groups in source ecology and harm-attribution content. The
specific manuscript-facing priorities are:

- validate source-type extraction quality
- validate source stance extraction quality
- validate causal-claim extraction quality (precision AND recall)
- identify recurring failure modes
- create a case-type-coded subset for later subgroup checks

If there is a tradeoff in time, prioritize packets in numeric order
(01, 02, 03, 04).
