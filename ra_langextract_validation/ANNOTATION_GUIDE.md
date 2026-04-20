# Annotation Guide

This guide covers only the Step 08 structural extraction workflow.

## Scope

Include:

- Section 4.8 structural results
- Appendix A structural extraction

Exclude:

- Appendix B pilot bias-indicator extraction
- anything produced by `09_bias_extraction.py`

## File 1: Article Validation

File:

- `generated/01_article_validation_sample.csv`

Focus:

- human validation of overall article stance
- human validation of dominant frame
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

Use the manuscript's frame logic:

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

### `ra_primary_issue`

Short free text:

- e.g. `retail theft`, `recall politics`, `homicide plea deal`,
  `office staffing`, `drug diversion`

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

- `generated/02_extraction_review_sample.csv`

Focus:

- source attribution quality
- causal claim quality
- off-schema values
- ambiguous cases

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
- source roles that fall outside the prompt schema
- blended multi-role outputs like comma-separated source types

## File 3: Case-Type Coding

File:

- `generated/03_case_type_coding_sample.csv`

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

## General Coding Rules

- Read enough context to understand who is speaking and what is being claimed.
- Do not assume the article voice matches a quoted speaker's stance.
- When uncertain, keep the main label conservative and explain the uncertainty in
  `ra_notes`.
- Fill only `ra_*` columns.
- Do not overwrite model outputs or metadata columns.

## Quality Control

When in doubt:

1. prefer `unclear` over a forced label
2. leave a short note
3. flag repeated failure modes consistently across files

Useful recurring note tags:

- `quoted criticism`
- `balanced story`
- `unclear source role`
- `implicit causality`
- `comparison not explicit`
- `policy vs claim`
