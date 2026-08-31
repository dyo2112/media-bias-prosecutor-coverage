# Project status — 27 August 2026

Working notes on where the manuscript stands, what the load-bearing findings
are, and what is still open. Written to be readable by a co-author or RA, not
just by whoever last touched the code.

Current location: `C:\Users\dviry\research\media_bias_python` (moved off Google
Drive on 2026-08-27; the raw corpus sits alongside at `C:\Users\dviry\research\`).
`config.py` derives all paths from its own location, so the repository is
portable — set `MEDIA_BIAS_DATA_DIR` if the corpus lives somewhere else.

## The manuscript

`paper/main.tex`, 92 pages, builds with zero undefined references or citations.
It has been through a full adversarial audit and several rounds of correction.
Every number in the text is now traceable to a file in `output/`.

Headline figures after all fixes:

| Measure | *d* | Note |
|---|---|---|
| Composite (pooled) | −0.151 | upper bound; see finding 1 |
| Composite (credible designs) | ≈ −0.07 | what the clean estimates agree on |
| Stance | −0.337 | carries the composite |
| Keyword salience | −0.203 | −0.264 where the instrument can measure (`sensitivity_no_fallback.keyword_zero_inflation`) |
| Theme attribution | +0.418 | substantially event-driven; see finding 2 |
| Framing (zero-shot only) | V = 0.282 | pooled version withdrawn; see finding 3 |

## Three findings that shape how the paper should be read

**1. The pooled composite is roughly double what the clean designs support.**
Dropping Wagstaffe gives *d* = −0.070; the within-county comparisons give −0.068
(San Francisco) and −0.069 (Alameda). Wagstaffe's coverage is a large outlier
(+0.040 composite versus −0.016 to −0.018 for the other traditional
prosecutors) and he is the only prosecutor from San Mateo, the one county with
no transition. The pooled −0.151 is inflated by cross-county heterogeneity. The
paper now presents it as an upper bound with *d* ≈ −0.07 as the credible
estimate. Note the tension: San Mateo both supplies much of the pooled contrast
and serves as the untreated comparison series in the controlled ITS.

**2. The theme effect is substantially event-driven.** *d* = +0.418 on the full
sample, +0.096 excluding recall-themed articles, +0.300 excluding crime-rising,
and **−0.088 (sign reversal, p = 9.2e-06) excluding either**. Both progressive
prosecutors faced real recall campaigns; no traditional prosecutor did. Coverage
of a real recall is not evidence that comparable officials are treated
differently. Reproduce with the `event_decomposition` block in
`output/10_theme_stats.json`.

**3. Pooled frame-probability contrasts were an artifact.** The `frame_*` scores
mix two instruments on roughly thirtyfold different scales (zero-shot
probabilities ≈ 0.87, keyword-fallback pattern fractions ≈ 0.03), and instrument
assignment correlates with group (50.2% of progressive articles zero-shot-scored
versus 45.9% of traditional). For two frames the pooled *d* falls outside the
range spanned by both subgroups, which a genuine weighted combination cannot do.
Zero-shot-only is now the primary framing analysis. Diagnostic:
`output/06_stats_results.json` → `framing` → `instrument_mixing_diagnostic`.

## Human validation

A research assistant completed four packets (article stance and frame,
extraction audit, case-type coding, extraction recall) covering 373 distinct
articles. Key results, all reported in the manuscript:

- Article-level stance agreement with the model is no better than chance
  (Cohen's κ = 0.049); within the 84 articles carrying both labels the
  classifier over-assigns "supportive" (45 model-supportive versus 18
  human-supportive).
  The continuous score is monotone in human labels, so stance supports aggregate
  contrasts but not article-level or absolute claims.
- Extraction: 98.8% of spans are textually grounded, class precision 96.6%, but
  attribute precision only 72.4% (62.5% for causal claims).
- Recall: the model misses 28–34% of sources visible in an excerpt, concentrated
  in unnamed and documentary attribution. Miss rates do not differ significantly
  by prosecutor type, so this does not appear to manufacture the source-ecology
  differential.
- Case-type composition does not differ by prosecutor type (Fisher *p* = .853),
  ruling out a story-type confound.
- Her observations produced the relevance rule now used in two sensitivity
  analyses, and she found two genuine bugs in this codebase.

**Caution:** `ra_langextract_validation/tests/synthetic_fixtures/` contains
FABRICATED packets and fabricated κ tables left over from a dry run. Never
compute or quote inter-rater reliability from them. The genuine coding is in
`ra_langextract_validation/completed/*.csv`.

## Open decisions

1. **Theme sign convention.** The paper reports theme *d* as −0.42 in some
   places and +0.418 in others, following two different conventions. Fixing it
   changes printed signs, so it needs an explicit decision.
2. **Second coder / inter-rater reliability.** The one gap that cannot be closed
   by writing. Blinded `ra2` packets are built and unused.
3. **Human-validation section** is about 38% of Results and is organised by
   packet number rather than by finding. Reorganisation was deliberately
   deferred as a whole-section rewrite.
4. **The Price recall no longer supports the two-event framing.** Those quarters
   are among the shallowest after 2021. The recall-amplification argument now
   rests on the Alameda segmented ITS and the within-county theme contrast.
5. **RA credit.** Four completed packets, two bugs found, results in the
   methods, results, and two appendices. Worth settling before submission.

## Deferred audit items

Reproducibility packaging (dependency and HuggingFace revision pinning, a corpus
schema for replicators), story-level clustering for the syndication problem, and
the absence of a quote-masked variant of the stance classifier — the quoted-speech
confound is tested on the keyword and theme layers but not on the method carrying
the main result. Roughly 17 audit findings were never adversarially verified;
they are recorded in the session transcripts.

## Housekeeping

- `run_extraction.bat` holds a Google API key in plaintext and now exists in two
  locations. Gitignored in both. Worth rotating and moving to an environment
  variable.
- The old Google Drive copy is intentionally still in place as a safety net.
  Archive it once this location has been used comfortably.
