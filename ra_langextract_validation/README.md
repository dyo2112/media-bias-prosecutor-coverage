# RA Langextract Validation Workspace

This folder is for manual validation and follow-up analysis of the Step 08
structural extraction only:

- Main text Section 4.8
- Appendix A (`LLM-Based Structural Content Extraction`)

Do not use this folder for Step 09 / Appendix B (`09_bias_extraction.py`).

If you cloned this repository from GitHub and cannot find the article-level
files, see `DATA_ACCESS.md` first. Those files are intentionally excluded from
GitHub because they contain licensed article text or article excerpts.

## What This Folder Is For

The goal is to help a research assistant validate the structural extraction
results that feed the manuscript's source ecology and causal-content claims.
The priorities below match the current manuscript needs.

## Order Of Importance

### 1. Article-level validation of stance and framing

Start here.

Use `generated/01_article_validation_sample.csv` after running the packet
builder. This packet samples prosecutor-attributed articles and includes:

- headline, publication, date, prosecutor, ideology
- article excerpts pulled from the local licensed corpus
- existing model outputs from Step 04 and Step 05:
  - `score_stance`
  - `model_stance_bucket`
  - `dominant_frame`
- Step 08 structural counts:
  - source counts
  - claim counts
  - causal counts

What to do:

- Read the article excerpts.
- Label the overall article stance toward the prosecutor.
- Label the dominant frame.
- Flag quoted criticism, balanced reporting, and implicit causal language.

Why this matters:

- It gives a direct human benchmark for the model-based stance/frame outputs.
- It helps interpret whether Step 08 structural asymmetries line up with the
  broader evaluative patterns reported in Section 4.

### 2. Targeted error analysis of Step 08 extractions

Use `generated/02_extraction_review_sample.csv`.

This packet is designed to focus on the most manuscript-relevant failure modes:

- quoted criticism reported by journalists
- balanced articles containing both supportive and critical voices
- implicit or speculative causal claims
- schema drift / off-schema attribute values
- ambiguous source-role assignments

What to do:

- Check whether each extraction is actually present in the text.
- Check whether the extraction class is correct.
- Check whether the attributes are correct.
- When incorrect or ambiguous, write the corrected class/attributes in
  `ra_corrected_*` fields or `ra_corrected_attributes_json`.

Why this matters:

- Section 4.8 and Appendix A rely on source-type and causal-claim structure.
- If the model struggles in systematic ways, that changes how strongly the
  structural findings should be interpreted.

### 3. Case-type coding for subgroup checks

Use `generated/03_case_type_coding_sample.csv`.

This packet supports a later robustness check: whether observed patterns still
hold within comparable case mixes rather than only in the pooled corpus.

What to do:

- Label whether the article is mainly about:
  - `violent`
  - `non_violent`
  - `mixed`
  - `no_specific_offense`
  - `unclear`
- Add a more specific category when possible.
- Note whether the article is about a specific case or a more general
  policy/politics story.

Why this matters:

- Progressive/traditional coverage may differ partly because the case mix
  differs.
- A clean case-type-coded subset makes within-group comparisons possible later.

## Files In This Folder

- `ANNOTATION_GUIDE.md`
  - Coding rules and label definitions.
- `DATA_ACCESS.md`
  - Explains where the article-level files and generated RA packets should come
    from.
- `scripts/build_ra_packets.py`
  - Generates local review packets from the licensed `output/` files.
- `scripts/summarize_ra_labels.py`
  - Summarizes completed RA coding sheets into simple agreement/error tables.
- `templates/`
  - Header-only templates showing the expected output columns.
- `generated/`
  - Local review packets with article excerpts. Ignored by Git.
- `completed/`
  - RA-completed files. Ignored by Git.
- `summary/`
  - Local summaries from the review results. Ignored by Git.

## Important Data Boundary

The repository does not version raw article text for licensing reasons.

That means:

- the committed folder includes instructions, scripts, and templates
- the actual review packets are generated locally from the existing
  `output/*.parquet` and `output/08_extractions.jsonl` files
- the generated CSVs include article excerpts and therefore stay out of Git

## Required Local Inputs

These files must exist locally before you build packets:

- `output/03_attributed.parquet`
- `output/04_bias_scores.parquet`
- `output/05_frames.parquet`
- `output/08_extractions.jsonl`
- `output/08_extractions_summary.parquet`

## How To Generate The Packets

From the repository root:

```bash
py -3 ra_langextract_validation/scripts/build_ra_packets.py
```

This writes three local CSVs:

- `ra_langextract_validation/generated/01_article_validation_sample.csv`
- `ra_langextract_validation/generated/02_extraction_review_sample.csv`
- `ra_langextract_validation/generated/03_case_type_coding_sample.csv`

You can also override the sample sizes:

```bash
py -3 ra_langextract_validation/scripts/build_ra_packets.py \
  --article-sample-size 100 \
  --extraction-sample-size 160 \
  --case-sample-size 120
```

## How To Work

1. Build the packets.
2. Duplicate each generated CSV into `completed/` before editing it.
3. Fill only the `ra_*` columns.
4. Do not overwrite the model columns.
5. Keep difficult cases and uncertainty in `ra_notes`.

Suggested completed filenames:

- `completed/01_article_validation_completed.csv`
- `completed/02_extraction_review_completed.csv`
- `completed/03_case_type_coding_completed.csv`

## How To Summarize Completed Coding

After the RA finishes a round of coding:

```bash
py -3 ra_langextract_validation/scripts/summarize_ra_labels.py
```

This writes local summaries to `ra_langextract_validation/summary/`.

## Current Manuscript Context

The Step 08 structural extraction supports the claim that progressive-prosecutor
coverage has a different source ecology and more harm-attribution content.
The specific manuscript-facing priorities are:

- validate source-type extraction quality
- validate source stance extraction quality
- validate causal-claim extraction quality
- identify recurring failure modes
- create a case-type-coded subset for later subgroup checks

If there is a tradeoff in time, prioritize:

1. `01_article_validation_sample.csv`
2. `02_extraction_review_sample.csv`
3. `03_case_type_coding_sample.csv`
