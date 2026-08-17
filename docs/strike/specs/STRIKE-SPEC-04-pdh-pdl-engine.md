# STRIKE-SPEC-04 — PDH/PDL Engine

**Status:** DRAFT-FILED (pre-Titans) · **Family:** B (Prior-Day Pivot Engine)
**Raschke basis:** Rule 5 (how the market trades around the previous day's
high/low indicates strength/weakness) and Rule 6 (PDH/PDL are the definitive
pivot points — look for test-and-reverse or push-through-and-continue).
**Build class:** LARGEST of the four — new Pine alert fleet + webhook payload
type + converter. Sequenced last deliberately. Full Titans review — ATLAS
(pipeline) + AEGIS (new webhook surface, secret handling) mandatory.

---

## 1. Problem

PDH/PDL are the two levels every intraday participant watches, they cost
nothing to compute, and they generate **two opposite signal types from one
anchor** — which makes the engine inherently bidirectional:

- **Continuation:** push through the level and hold (acceptance).
- **Reversal:** sweep beyond the level and reclaim (the E.02 sweep-and-reclaim
  trigger, M.04 trapped-trader fuel, anchored at a free level).

## 2. Scope

**2a. Levels (trivial, nightly):** PDH/PDL computed from daily bars for the
universe; stored alongside SPEC-02/03 nightly outputs.

**2b. Intraday detection (the build):** one new Pine script on the existing
TradingView → webhook pattern (same transport as PYTHIA v2.4 and the circuit-
breaker fleet):

- **Acceptance event:** two consecutive 5-minute closes beyond PDH (long) /
  PDL (short) → `pdh_accept` / `pdl_accept`.
- **Sweep-reclaim event:** intrabar violation of the level by ≥ 0.1 × ATR14
  followed by a 5-minute close back inside within 30 minutes →
  `pdh_reject` (short) / `pdl_reject` (long).
- Payload: ticker, event type, level value, event price, bar timestamp (UTC),
  shared-secret signature per the CB-webhook enforce runbook
  (`docs/codex-briefs/2026-07-29-runbook-cb-webhook-enforce.md`).

**2c. Converter:** same architecture as SPEC-01 (which is why SPEC-01 ships
first — its converter is this one's template). Entries at event price; stops:
acceptance → the level itself (failed acceptance = exit); sweep-reclaim → the
sweep extreme. Targets in ATR multiples as SPEC-02. Morning-window weighting
per Family E: **reversal-type events (`*_reject`) score −15 after 12:00 ET**
(Rule 3: best reversals happen in the morning); acceptance events are
time-neutral.

## 3. Non-goals

No new tickers beyond the existing TradingView alert fleet's capacity; no
changes to PYTHIA v2.4; no live scoring; no options auto-selection.

## 4. Sequencing dependency

Blocked behind SPEC-01 (converter template + webhook-store schema knowledge
from its build) and behind the STRIKE-Q1 §Q4 webhook-receipt audit (we do not
add a second webhook consumer until the first one's delivery reliability is
measured).

## 5. Promotion gate

n ≥ 60 shadow signals with both event types represented; sweep-depth and
reclaim-window parameters reviewed against collected distribution (0.1 × ATR
and 30 min are provisional); friction model at clip size; Titans re-review +
Nick GO.

## 6. Open questions for Titans review

1. TradingView plan alert-slot budget — does a per-ticker PDH/PDL fleet fit,
   or does this ship index-ETFs-only (SPY/QQQ/IWM/SMH) in v1? (Recommend
   index-ETFs-only v1; single-name expansion is a separate scope.)
2. Webhook endpoint: extend the existing route with a new event type (AEGIS:
   same secret? separate secret per fleet?) vs a new route.
3. 5-minute bar source of truth inside Pine vs converter-side validation —
   how much payload trust does the converter extend (AEGIS boundary question).
