# DEF-TRITON-GRADER-NO-SKIP-REASON

**Severity:** P3 · **Filed:** 2026-09-02 (R-IV.151(c)) · **Status:** OPEN
**Surface:** Triton shadow grader — no failure/skip/error field exists on
`triton_flow_shadow`

## Symptom

**The grader records no reason for not grading a row.** Confirmed twice by CC-QUERY: no
such column in `information_schema`, and `raw`'s eleven top-level keys are all UW alert
payload (`alert_rule · expiry · id · open_interest · rule_id · sector · strike ·
total_ask_side_prem · total_bid_side_prem · type · volume`), present on all 126 residue
rows.

An ungraded row is therefore indistinguishable from a row that was never reached.

## Why it costs

The 72-row index-symbol cause — SPX/SPXW/RUT/RUTW/VIX have no backward price series, so
`prior_5d_ret` is NULL at fire time and `fwd_ret_*` is uncomputable at grade time — was
established **by inference from pre-fire fields, not by lookup.** It took a full census to
answer a question a single column would have answered directly, and the next residue
question will cost the same again.

## Design note

**Every skip records its reason.** A component that declines to act on a row should say
why on that row. The absence of a reason field is what forces the next investigator to
reconstruct intent from side effects — and reconstruction is where wrong causes get
attributed confidently.

## Deliberately not folded into the P1

Filed separately per the residue census's own recommendation. This is a design gap in what
the grader records, not a cause of `DEF-TRITON-GRADER-DARK`. Folding it in would let a P3
ride a P1's urgency, and would blur the P1's diagnosis — "the grader records no reason" is
not an explanation for why it stopped.

## Fix shape

A nullable `skip_reason TEXT` (or equivalent) written whenever the grader passes over a
row, with at least: no price series · window not closed · upstream error. Documentary
vocabulary, no CHECK constraint, per the `strategy_tag` / `flow_type` precedent.
