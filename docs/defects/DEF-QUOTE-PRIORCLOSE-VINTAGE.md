# DEF-QUOTE-PRIORCLOSE-VINTAGE

**Severity:** P1 (fake-healthy family) · **Filed:** 2026-08-17 · **Status:** OPEN
**Surface:** `hub_get_quote` — `prior_close` / `pct_change` fields, `status:"live"`

## Symptom
`prior_close` serves a value that is not the prior session's close; `pct_change`
is computed off that wrong base while the payload reports `status:"live"`.

## Evidence (three sightings)
1. **2026-08-04 post-market:** SPY `prior_close` 771.33 vs verified Monday
   close ~759.3 (SPX 7,600.50 per CNBC/Investrade chain). Displayed SPY
   "+0.19%"/QQQ "−0.15%" on a day the S&P rose +1.79% and Nasdaq +2.59%.
   NVDA reconciled correctly in the same read (prior_close 211.94 = verified
   Monday close) — per-ticker inconsistency.
2. **2026-08-05 09:08Z-ish (open):** SPY `prior_close` still 771.33; true prior
   close 772.76. Stale base persisted across the session roll.
3. **2026-08-17 20:04Z (post-market):** SPY `prior_close` 772.68 = the day's
   OPEN exactly; `pct_change` −0.01% rendered as a daily change.

## Hypothesis (unverified)
UW `/stock-state` prior-close field rolls to an intra-session reference (open
or T+0 anchor) for index ETFs under some condition; or hub-side caching serves
a mixed-vintage snapshot. NVDA correctness in sighting 1 argues against a
single global mechanism.

## Interim rule (already operating law)
Cross-source verification mandatory before quoting daily changes for
SPY/QQQ/SMH from `hub_get_quote`. `spot` field has reconciled in all sightings
and may be used; `prior_close`/`pct_change` may not.

## Verification / fix path
1. Log raw UW `/stock-state` responses for SPY/QQQ/SMH/NVDA at 4:05p, 8:05p,
   and next-day 9:35a ET for two sessions; diff prior_close against UW daily
   bar close.
2. If upstream: derive prior_close hub-side from the daily bars table instead
   of trusting /stock-state; if hub cache: fix vintage keying.
3. Close only on two clean session rolls across all four tickers.
