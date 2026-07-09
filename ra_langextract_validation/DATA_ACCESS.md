# Data Access For RA Validation

The article-level files needed by `scripts/build_ra_packets.py` are not stored
on GitHub.

This is intentional. Files such as `output/03_attributed.parquet` and generated
RA packet files contain article text or article excerpts from the licensed
corpus. They should not be committed to GitHub, including this folder's
`generated/`, `completed/`, `summary/`, or `adjudication/` subdirectories.

Only share article-level files or generated packets with people who are covered
by the relevant data access terms for the underlying corpus. If the RA is not
covered, send an ID-only assignment sheet and have her access the articles
through an approved licensed source instead.

## Blinding Rules (Apply In Every Workflow)

The validation design blinds the RA to the study hypotheses and model outputs.
Regardless of licensing status:

- Share with the RA ONLY:
  - `ANNOTATION_GUIDE.md`
  - the files in `generated/<coder_id>/` built for that coder
- NEVER share with the RA:
  - anything in `generated/keys/` (prosecutor ideology, model stance/frame/
    bias scores, sampling buckets, heuristic flags)
  - anything in `summary/` or `adjudication/`
  - `output/04_bias_scores.parquet`, `output/05_frames.parquet`, or other
    pipeline outputs containing model scores
  - the manuscript or README of this folder (they describe the hypotheses)
- Do not tell the RA which prosecutors are classified as progressive or
  traditional, or that articles were sampled by those groups.
- With two coders, tell them not to discuss rows until both have finished.

## Preferred Workflow, If The RA Is Covered

The PI generates the packets locally, once per coder, and sends only that
coder's `generated/<coder_id>/` files through the approved private channel. Do
not upload them to GitHub.

From the repository root:

```bash
py -3 ra_langextract_validation/scripts/build_ra_packets.py --coder-id ra1
py -3 ra_langextract_validation/scripts/build_ra_packets.py --coder-id ra2  # optional second coder
```

This creates, per coder:

- `ra_langextract_validation/generated/<coder_id>/01_article_validation_sample.csv`
- `ra_langextract_validation/generated/<coder_id>/02_extraction_review_sample.csv`
- `ra_langextract_validation/generated/<coder_id>/03_case_type_coding_sample.csv`
- `ra_langextract_validation/generated/<coder_id>/04_extraction_recall_sample.csv`

and PI-only key files under `ra_langextract_validation/generated/keys/`.

The RA returns completed versions, which go locally in either layout:

- `ra_langextract_validation/completed/<coder_id>/<packet>_completed.csv`
- `ra_langextract_validation/completed/<packet>_completed_<coder_id>.csv`

Then run `py -3 ra_langextract_validation/scripts/summarize_ra_labels.py`,
which joins the key files back on `packet_id` and, with 2+ coders, writes
disagreement sheets to `adjudication/` for PI adjudication.

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

Caution: this workflow weakens blinding, because building packets also writes
the `generated/keys/` files and the inputs contain model scores and
prosecutor classifications. Prefer the PI-generated workflow whenever the
blinded design matters; if the RA must self-generate, instruct her not to open
`generated/keys/` or the Step 04/05 parquet files.

## If The RA Is Not Covered

Do not send generated packet files with article excerpts.

Use an ID-only workflow instead:

- send article IDs, headlines, publication names, dates, and the empty `ra_*`
  assignment fields (from `templates/`), but no model outputs and no
  prosecutor classifications
- have the RA retrieve the article text through an approved licensed source
- keep completed coding files off GitHub if they include quoted text or article
  excerpts

## Why Summary Files Are On GitHub

Small aggregate outputs, such as `output/08_extraction_stats.json`, are kept in
the repository because they support manuscript reproducibility without exposing
article text. The article-level files are excluded by `.gitignore`, as are
this folder's `generated/`, `completed/`, `summary/`, and `adjudication/`
directories.
