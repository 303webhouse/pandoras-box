# STRIKE-SPEC-01 — IB-Break Feed Conversion

**Status:** DRAFT-FILED (pre-Titans) · **Family:** C2 (Opening Structure)
**Raschke basis:** Rules 9 ("first hour's range establishes the framework") and
10 (trade aggressively on early signs of a strong trend day).
**Build class:** Backend pipeline wiring. No UI (MOCKUP GATE n/a). Titans
review required — ATLAS lead (feed integrity), AEGIS touch (webhook payload
trust boundary).

---

## 1. Problem

The PYTHIA Pine v2.4 webhook already computes and emits Initial Balance break
events (`ib_break_up` / `ib_break_down`, with `price_at_event`, VA levels, and
`volume_quality`). Proven live: SPY `ib_break_up` @ 765.39 during the Aug 3–4
melt-up. **Nothing downstream consumes these events.** They are display-only in
`hub_get_market_profile`. This is the smallest instance of the convicted
conversion-layer gap: a real-time, structurally sound 1–3 DTE trigger the
system already detects and then swallows.

## 2. Scope (what gets built)

A converter job that turns qualifying IB-break events into **shadow signal
rows** in the existing signals pipeline:

- **Trigger:** first `ib_break_up` or `ib_break_down` event per ticker per
  session from the PYTHIA webhook store. Subsequent same-direction breaks in
  the same session are ignored (no re-fire); an opposite-direction break in the
  same session emits a second signal tagged `ib_reversal=true`.
- **Direction:** long on `ib_break_up`, short on `ib_break_down`. Bidirectional
  by construction; no macro-bias gate (Horse Rule).
- **Entry:** `price_at_event`.
- **Stop:** IB midpoint (default). Conservative alternative (opposite IB
  extreme) recorded in the shadow row's metadata for later comparison —
  collect both, decide at promotion review.
- **Targets:** t1 = break price ± 0.5 × IB height; t2 = break price ± 1.0 × IB
  height (measured-move convention). IB height = `ib_high − ib_low`.
- **Score inputs (shadow score, not fed to live feed):**
  - Gap-vs-ATR modifier (Family C1): opening gap ≥ 0.5 × ATR14 in break
    direction → +10 (Rule 4: larger gaps favor continuation).
  - `volume_quality` from the event: `thin` → −10 (PYTHAGORAS C.05 volume-lie
    caution), `strong` → +10.
  - Morning-window bonus (Family E): event before 11:00 ET → +5; event after
    14:00 ET → −10.
- **Emission:** existing signals schema (entry/stop/t1/t2, risk_reward,
  timeframe='1-3D', adx/rsi/rvol where computable from UW daily context),
  `status='SHADOW'` (or the pipeline's equivalent non-live flag — confirm
  exact enum against schema during build), `source='STRIKE_IB_BREAK'`.

## 3. Non-goals (scope fence)

- No new Pine scripts, no webhook endpoint changes, no UI, no live scoring, no
  auto-trading, no changes to existing PYTHIA event ingestion. Defects found
  during the build are ticketed, not fixed in-scope.

## 4. Data dependencies

- PYTHIA webhook event store (exact table name confirmed by STRIKE-Q1 §Q0
  preflight before build brief is finalized).
- UW daily bars for ATR14 and prior-close gap math (UW primary; yfinance
  fallback only, provenance-labeled).

## 5. Promotion gate (shadow → live)

n ≥ 50 shadow signals collected, spanning ≥ 3 weeks and both directions;
manual review of stop-variant comparison (IB-mid vs opposite-extreme);
friction model applied at $100–300 clip size on the actual optionable
underliers; then Titans re-review + explicit Nick GO. No exceptions.

## 6. Open questions for ATLAS review

1. Which table/queue is the canonical webhook event store, and does it carry
   per-ticker session identifiers or only SPY?
2. Ticker coverage: PYTHIA Pine fleet currently emits which tickers? If
   SPY-only, SPEC-01 ships SPY-only and expansion is a separate scope.
3. Signals table `status` enum values — correct shadow designation.
4. Idempotency: converter must not double-emit on webhook replays.
