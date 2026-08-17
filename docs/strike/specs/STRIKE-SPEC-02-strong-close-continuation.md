# STRIKE-SPEC-02 — Strong Close Continuation

**Status:** DRAFT-FILED (pre-Titans) · **Family:** A (Strong Close Continuation)
**Raschke basis:** Rule 2 (afternoon strength/weakness follows through next
day), Rule 7 (consecutive strong closes → uptrend continues; morning rally +
weak close → trend likely ending), Rule 8 (high volume on a strong close →
next-morning continuity).
**Build class:** Nightly batch job on daily bars. Zero new data infrastructure.
No UI. Titans review — ATLAS lead.

---

## 1. Problem

The Aug 3–4 melt-up was a textbook Rule-2/7 sequence: two consecutive strong
closes, then a third up day to record highs. The system had every input in
daily bars and emitted nothing. This family converts close-location arithmetic
into next-morning continuation signals — long **and** short — with zero new
data dependencies.

## 2. Definitions

- **CLV (close location value):** `(close − low) / (high − low)`, range 0–1.
- **Strong up close:** CLV ≥ 0.75 **and** day change > 0.
- **Strong down close:** CLV ≤ 0.25 **and** day change < 0.
- **Streak:** consecutive sessions with same-direction strong closes.
- **RVOL:** day volume / 30d average volume.

Thresholds (0.75/0.25, RVOL 1.2) are provisional and shadow-tunable; changes
after shadow collection begins require a spec amendment (no silent retuning).

## 3. Scope

Nightly post-close job over the liquid-optionable universe (reuse the existing
watchlist/universe table — confirm name in build brief):

- **Continuation signal (both directions):** strong close + RVOL ≥ 1.2 →
  emit next-morning continuation signal in close direction.
  - Entry: next-session open (recorded at emission as prior close; shadow row
    updated with actual open at next nightly run for slippage measurement).
  - Stop: prior session's opposite extreme (long → prior low; short → prior
    high). Targets: t1 = entry ± 1.0 × ATR14; t2 = entry ± 1.5 × ATR14.
  - Score inputs: streak length (2 → +5, 3+ → +0 and see exhaustion below),
    RVOL band (≥1.5 → +10), gap alignment at next open (Family C1 modifier).
- **Exhaustion flag (Rule 7b), emitted as a tag not a trade:**
  streak ≥ 3 **and** session pattern = morning strength (high in first half)
  with weak close (CLV ≤ 0.4) → emit `EXHAUSTION_WATCH` tag on the ticker.
  Family E consumers cap continuation scores while the tag is live (2
  sessions). This is the defined climax detector (Principle Three: trends end
  in a climax) — it replaces discretionary top-picking, which the operator's
  logged failure modes (early parabolic shorts) specifically require.

## 4. Non-goals

No intraday data, no live scoring, no UI, no universe changes beyond reusing
the existing list, no touching existing strategy jobs.

## 5. Friction note (lane law)

Continuation entries at next-open on liquid underliers are the lowest-friction
expression in the STRIKE families: no chase, definable risk, and structure
selectable by DAEDALUS (shares vs narrow debit spread) per clip size. Shadow
rows must record the underlier's option spread snapshot when feasible so the
friction model uses real quotes, not assumptions (feasibility depends on the
`b2_options_resolver` audit in STRIKE-Q1 §Q7).

## 6. Promotion gate

n ≥ 75 shadow signals across both directions and ≥ 4 weeks (universe breadth
makes this fast); slippage measurement (recorded open vs prior close) reviewed;
exhaustion-tag hit pattern reviewed qualitatively; Titans re-review + Nick GO.

## 7. Open questions for ATLAS review

1. Universe table of record for "liquid optionables."
2. Where nightly jobs schedule from (Railway cron vs VPS OpenClaw cron) and
   collision windows with the existing nightly outcome walk.
3. Signals schema: does a tag-only emission (`EXHAUSTION_WATCH`) fit the
   existing table or does it need a sidecar table? (Prefer sidecar to avoid
   polluting signal rows.)
