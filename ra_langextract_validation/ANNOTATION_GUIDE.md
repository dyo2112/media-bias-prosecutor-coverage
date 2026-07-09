# Annotation Guide

This guide covers the Step 08 structural extraction validation workflow.

You will receive up to four CSV files, each with your coder id in the folder or
file name (e.g. `generated/ra1/01_article_validation_sample.csv`). Every file
contains article content columns plus empty `ra_*` columns. Fill only the
`ra_*` columns. Do not add, remove, rename, or reorder columns.

Important: code each row on the text alone. You are the benchmark; there are
no "expected" answers, and your labels are compared against other information
only after you finish. Do not try to guess what the study is looking for.

## Scope

Include:

- the four generated CSV files listed below

Exclude:

- anything produced by `09_bias_extraction.py`
- any other pipeline output files

## File 1: Article Validation

File:

- `generated/<your coder id>/01_article_validation_sample.csv`

Focus:

- the article's overall stance toward the named prosecutor
- the article's dominant frame
- flags for difficult discourse conditions

### `ra_article_stance`

Use one of:

- `critical`
- `neutral`
- `mixed`
- `supportive`

Rule:

- label the article's overall treatment of the prosecutor, not just one quoted
  speaker
- if the article contains both criticism and support with no clear dominant
  direction, use `mixed`

### `ra_dominant_frame`

Use one of:

- `accountability`
- `conflict`
- `consequences`
- `human_interest`
- `reform`
- `mixed`
- `other`

Definitions:

- `accountability`
  - the prosecutor is blamed or held responsible
- `conflict`
  - the article centers disagreement among actors
- `consequences`
  - the article centers downstream outcomes or impacts
- `human_interest`
  - the story centers a person, family, victim, or defendant
- `reform`
  - the article is about reform politics, ideology, or tough/soft-on-crime

### `ra_dominant_frame_forced`

Always fill this one too, even when you used `mixed` or `other` above.

Pick the single closest of the five substantive frames only:

- `accountability`
- `conflict`
- `consequences`
- `human_interest`
- `reform`

If `ra_dominant_frame` is already one of the five, repeat it here. If you used
`mixed` or `other`, choose the one frame that comes closest anyway. This
forced choice is required for every row.

### `ra_primary_issue`

Short free text:

- e.g. `retail theft`, `recall politics`, `homicide plea deal`,
  `office staffing`, `drug diversion`

### `ra_prosecutor_is_subject`

Use:

- `yes` - the named prosecutor is a main subject of the article
- `no` - the prosecutor is only mentioned in passing
- `unclear`

### Discourse-condition flags

Use:

- `yes`
- `no`
- `unclear`

Fields:

- `ra_quoted_criticism`
  - criticism is clearly quoted or attributed to a source rather than asserted
    as the article's own voice
- `ra_balanced_reporting`
  - the article meaningfully presents both supportive and critical positions
- `ra_implicit_causal_claim`
  - the article implies that prosecutor action caused an outcome without saying
    it directly

## File 2: Extraction Review

File:

- `generated/<your coder id>/02_extraction_review_sample.csv`

Each row shows one machine-extracted span (`extraction_text`), its predicted
class and attributes, and a context excerpt from the article. Judge the
extraction on its own merits.

### `ra_present_in_text`

Use:

- `yes`
- `no`
- `partial`
- `unclear`

Meaning:

- `yes`
  - the extracted text is clearly present in the article excerpt
- `partial`
  - the extraction loosely matches the text but is truncated, blended, or not a
    clean exact span

### `ra_class_correct`

Use:

- `yes`
- `no`
- `unclear`

Judge whether the extraction belongs to the predicted class:

- `source_attribution`
- `causal_claim`
- `claim_against_prosecutor`
- `policy_action`
- `comparison`

### `ra_attribute_correct`

Use:

- `yes`
- `no`
- `partly`
- `unclear`

Judge whether the attributes fit the text.

### `ra_corrected_class`

Only fill when `ra_class_correct = no`.

### `ra_corrected_attributes_json`

Use a compact JSON object or semicolon-separated key/value notes.

Examples:

- `{"source_type":"journalist","stance_toward_prosecutor":"neutral"}`
- `{"effect":"public_safety_decline","causal_strength":"implied"}`
- `source_type=politician; stance_toward_prosecutor=critical`

### `ra_ambiguity_type`

Use one short label when applicable:

- `quoted_criticism`
- `balanced_reporting`
- `implicit_causality`
- `source_role_ambiguity`
- `schema_drift`
- `comparison_scope`
- `other`

### What To Flag Aggressively

Flag these even if you are not fully sure:

- a quote attributed to a critic being treated as article-level criticism
- a lawsuit/report/court filing being coded as a person-like source
- vague or non-comparative statements being coded as `comparison`
- causal claims where causality is only implied
- source roles that fall outside the class list above
- blended multi-role outputs like comma-separated source types

## File 3: Case-Type Coding

File:

- `generated/<your coder id>/03_case_type_coding_sample.csv`

Focus:

- offense mix / case-type subgroup coding

### `ra_case_type_binary`

Use one of:

- `violent`
- `non_violent`
- `mixed`
- `no_specific_offense`
- `unclear`

### `ra_case_type_detailed`

Use the closest one:

- `homicide`
- `gun`
- `assault`
- `sexual_offense`
- `domestic_violence`
- `robbery`
- `burglary_or_theft`
- `drug`
- `juvenile`
- `white_collar_or_corruption`
- `public_order`
- `general_policy`
- `recall_or_politics`
- `other`
- `unclear`

### `ra_primary_offense_or_issue`

Short free text.

Examples:

- `organized retail theft`
- `homicide plea deal`
- `fentanyl prosecution`
- `recall campaign`
- `sentencing reform`

### `ra_specific_case_present`

Use:

- `yes`
- `no`
- `unclear`

`yes` means the article is substantially about a specific incident, case, or
defendant rather than general prosecutor politics or policy.

## File 4: Extraction Recall (Missed Content)

File:

- `generated/<your coder id>/04_extraction_recall_sample.csv`

Each row shows a longer article excerpt (`article_excerpt`) and the complete
list of machine extractions for that article (`model_extractions`, one per
line, with the class in brackets). Here you look for content the machine
MISSED, judging only against the excerpt shown.

### `ra_n_missed_sources`

Whole number (0, 1, 2, ...).

Count quoted or clearly attributed voices in the excerpt (a person, office,
organization, report, or filing that is quoted or paraphrased about the
prosecutor or the case) that do NOT appear anywhere in the
`model_extractions` list as a `source_attribution`.

- count distinct sources, not distinct quotes from the same source
- if the machine captured the source under a different class, still count it
  as missed for this column
- enter `0` when nothing was missed

### `ra_n_missed_causal_claims`

Whole number (0, 1, 2, ...).

Count statements in the excerpt that assert or imply the prosecutor's actions
caused some outcome (crime up or down, cases dismissed, community impact) that
do NOT appear in the `model_extractions` list as a `causal_claim`.

- include implied causation ("since she took office, thefts have soared")
- enter `0` when nothing was missed

### `ra_missed_notes`

Short free text quoting or paraphrasing the missed items, so they can be
checked later. Separate multiple items with `;`.

## General Coding Rules

- Read enough context to understand who is speaking and what is being claimed.
- Do not assume the article voice matches a quoted speaker's stance.
- When uncertain, keep the main label conservative and explain the uncertainty
  in `ra_notes` (`ra_missed_notes` in File 4). Exception:
  `ra_dominant_frame_forced` must always get one of the five frames.
- Fill only `ra_*` columns.
- Do not modify the pre-filled content columns.
- Code independently: do not discuss rows with anyone else who is coding the
  same files until both of you have finished.

## Quality Control

When in doubt:

1. prefer `unclear` over a forced label (except in the forced-choice column)
2. leave a short note
3. flag repeated failure modes consistently across files

Useful recurring note tags:

- `quoted criticism`
- `balanced story`
- `unclear source role`
- `implicit causality`
- `comparison not explicit`
- `policy vs claim`

## Returning Files

Save each finished file as `<original name with _sample replaced by
_completed>` and return it through the channel the PI gave you, e.g.
`01_article_validation_completed.csv`. Keep your coder id in the folder or
file name.
