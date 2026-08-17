# DEF-HERMES-EARNINGS-GAP

**Severity:** P2 · **Filed:** 2026-08-17 · **Status:** OPEN
**Surface:** `hub_get_hermes_alerts` (catalyst system)

## Symptom
2026-08-04 read with 120h lookback + 10d forward across the whole market
returned exactly two records (NFP, CPI) — zero earnings entries — during peak
Q2 earnings season, on the exact days earnings drove the tape (PLTR +29.5%,
W +29%, ZBRA +25%, IT +24% on 2026-08-03; hyperscaler prints Jul 30–31 set up
the melt-up).

## Why it matters
Hermes is the committee's catalyst-awareness input (DAEDALUS DTE selection,
THALES trigger #1). An earnings-blind Hermes silently degrades every
committee pass and any future STRIKE signal that should be earnings-gated
(SPEC-02 continuation signals must NOT fire into the underlier's own print).

## Verification / fix path
1. Confirm intended coverage: is earnings ingestion designed-in and broken, or
   never built? (Check Hermes ingestion job + source API entitlement.)
2. If UW earnings endpoints are entitled on the Basic plan, wire
   premarket/afterhours earnings into Hermes with expected_impact by market
   cap; else evaluate alternative source.
3. Acceptance: Hermes returns the week's earnings calendar for the SPEC-02
   universe with ≥95% coverage vs a manual spot-check week.
