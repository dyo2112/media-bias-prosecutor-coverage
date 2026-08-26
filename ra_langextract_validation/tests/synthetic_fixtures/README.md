# Synthetic test fixtures — NOT real coder output

These `ra1/` and `ra2/` directories contain **fabricated** packet files used to
exercise the multi-coder and adjudication code paths in
`scripts/summarize_ra_labels.py`. They were generated during a dry run and were
originally left in `completed/`, where the summarizer's file discovery
(`<coder>/<stem>_completed.csv`) would have picked them up and produced
inter-rater reliability statistics from invented data.

How to recognise them:
- label distributions are near-uniform across categories (real coding is skewed)
- every free-text column is empty (the real coder wrote extensive notes)
- `ra_case_type_binary` holds offence types instead of 0/1
- they contain the literal string `BADVALUE`, planted to test input validation

The genuine completed coding lives in `completed/*.csv` at the top level:
`01_article_validation_sample.csv`, `01_low_relevance_benchmark.csv`,
`02_extraction_review_sample.csv`, `03_case_type_coding_sample.csv`,
`04_extraction_recall_sample.csv`.

Do not move these back into `completed/`, and never cite any statistic
computed from them.
