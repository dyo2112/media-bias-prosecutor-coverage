# Data Access For RA Validation

The article-level files needed by `scripts/build_ra_packets.py` are not stored
on GitHub.

This is intentional. Files such as `output/03_attributed.parquet` and the
generated RA packet CSVs contain article text or article excerpts from the
licensed corpus, so they should be shared privately rather than committed to
the repository.

## Preferred Workflow

The PI should generate the RA packets locally and send the generated CSVs
through the approved private channel.

From the repository root:

```bash
py -3 ra_langextract_validation/scripts/build_ra_packets.py
```

This creates:

- `ra_langextract_validation/generated/01_article_validation_sample.csv`
- `ra_langextract_validation/generated/02_extraction_review_sample.csv`
- `ra_langextract_validation/generated/03_case_type_coding_sample.csv`

The RA can then place completed versions in:

- `ra_langextract_validation/completed/01_article_validation_completed.csv`
- `ra_langextract_validation/completed/02_extraction_review_completed.csv`
- `ra_langextract_validation/completed/03_case_type_coding_completed.csv`

## Alternative Workflow

If the RA needs to generate packets herself, the PI must privately provide the
following local files in the same relative paths:

- `output/03_attributed.parquet`
- `output/04_bias_scores.parquet`
- `output/05_frames.parquet`
- `output/08_extractions.jsonl`
- `output/08_extractions_summary.parquet`

These should not be added to GitHub.

## Why Summary Files Are On GitHub

Small aggregate outputs, such as `output/08_extraction_stats.json`, are kept in
the repository because they support manuscript reproducibility without exposing
article text. The article-level files are excluded by `.gitignore`.
