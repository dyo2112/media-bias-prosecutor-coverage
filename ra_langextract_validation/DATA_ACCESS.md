# Data Access For RA Validation

The article-level files needed by `scripts/build_ra_packets.py` are not stored
on GitHub.

This is intentional. Files such as `output/03_attributed.parquet` and generated
RA packet files contain article text or article excerpts from the licensed
corpus. They should not be committed to GitHub, including this folder's
`generated/`, `completed/`, or `summary/` subdirectories.

Only share article-level files or generated packets with people who are covered
by the relevant data access terms for the underlying corpus. If the RA is not
covered, send an ID-only assignment sheet and have her access the articles
through an approved licensed source instead.

## Preferred Workflow, If The RA Is Covered

The PI should generate the RA packets locally and send the generated files
through the approved private channel. Do not upload them to GitHub.

From the repository root:

```bash
py -3 ra_langextract_validation/scripts/build_ra_packets.py
```

This creates:

- `ra_langextract_validation/generated/01_article_validation_sample.csv`
- `ra_langextract_validation/generated/02_extraction_review_sample.csv`
- `ra_langextract_validation/generated/03_case_type_coding_sample.csv`

The RA can then place completed versions locally in:

- `ra_langextract_validation/completed/01_article_validation_completed.csv`
- `ra_langextract_validation/completed/02_extraction_review_completed.csv`
- `ra_langextract_validation/completed/03_case_type_coding_completed.csv`

## Alternative Workflow

If the RA is covered by the data access terms and needs to generate packets
herself, the PI must privately provide the following local files in the same
relative paths:

- `output/03_attributed.parquet`
- `output/04_bias_scores.parquet`
- `output/05_frames.parquet`
- `output/08_extractions.jsonl`
- `output/08_extractions_summary.parquet`

These should not be added to GitHub.

## If The RA Is Not Covered

Do not send generated packet files with article excerpts.

Use an ID-only workflow instead:

- send article IDs, headlines, publication names, dates, and assignment fields
- have the RA retrieve the article text through an approved licensed source
- keep completed coding files off GitHub if they include quoted text or article
  excerpts

## Why Summary Files Are On GitHub

Small aggregate outputs, such as `output/08_extraction_stats.json`, are kept in
the repository because they support manuscript reproducibility without exposing
article text. The article-level files are excluded by `.gitignore`.
