# Phase 0 Brief — PYTHAGORAS Feed: `hub_get_chart_indicators`

**Date:** 2026-06-10 | **Author:** Architecture layer | **Builder:** Claude Code
**Mode:** READ-ONLY INVESTIGATION (probe scripts that only read are fine).
**Gate:** Produce `docs/phase0-pythagoras-feed-findings.md`, then STOP.
**Queue position:** starts AFTER sub-brief 3 Chunk 3 (ADX job) lands — see
"Sequencing constraint" below. Drafted now so it's ready the day the gate clears.

---

## Context

PYTHAGORAS (trend / structure / technical-analysis specialist) is the last
committee agent without a live data feed: DAEDALUS got the options chain,
PYTHIA got the Market Profile feed (B4). PYTHAGORAS still works from whatever
Nick pastes or screenshots. The planned tool is `hub_get_chart_indicators` —
real-time indicator values (RSI, MACD, ATR, key MAs, VWAP, ADX, volume
context) for any ticker the committee analyzes.

## The load-bearing architectural question (Phase 0's main job)

B4 used a TradingView webhook because Market Profile computation was complex
and already lived in Pine. PYTHAGORAS's indicators are different: they are
**deterministic textbook math over OHLCV bars** — and the hub already pulls
OHLCV from UW (data hierarchy: UW PRIMARY for everything incl. bars), and
sub-brief 3 Chunk 3 is right now building a UW-bars ADX computation job.

So Phase 0 must decide between two architectures with evidence, not vibes:
- **(A) Server-side compute from UW bars** — on-demand for ANY ticker, no TV
  alert to maintain, no re-arm, no watchlist cap, reuses Chunk 3's bar-fetch +
  Wilder-smoothing code. Architecture-layer prior: this wins.
- **(B) TV webhook push (B4 pattern)** — values match what Nick sees on his
  TV charts exactly, but adds another alert to maintain, caps coverage at the
  PREY LIST, and inherits TV alert fragility (the B4 dead-feed lesson).

The prior is (A), but it must survive T2's rate-limit math and T3's parity
check before it's a decision. If (A) wins, this feed needs NO TradingView
re-arm at all — a meaningful simplification vs B4.

---

## Hard rules
1. Read-only against prod (probe scripts may call UW + read DB; nothing
   writes, nothing deploys).
2. UW rate budget respected even during probing (120/min, 20K/day shared
   with production — keep probe volume trivial).
3. Verify UW response shapes against live data, never the api_spec (the
   call_gamma/call_gex precedent).
4. STOP at the gate report.

## Sequencing constraint (file-collision guard)
Sub-brief 3 Chunk 3 is building `backend/jobs/adx_regime_job.py` + UW bar
fetching NOW. This Phase 0's probing may run anytime (read-only), but the
**build** must not start until Chunk 3 lands — the two share the bar-fetch
+ indicator-math territory, and the build should REUSE Chunk 3's code, not
race it. Note in the findings which Chunk 3 functions are reusable.

---

## T1 — PYTHAGORAS's data contract (demand side)
a. Read `skills/pythagoras/SKILL.md` + references: which indicators does the
   agent actually reason with? Expected: RSI(14), MACD, ATR(14), SMA/EMA
   20/50/120/200, VWAP, ADX(14), swing highs/lows, relative volume. Build
   the definitive list from the skill, not assumption.
b. Which timeframes per bucket: B1 thesis (daily/weekly), B2 tactical
   (daily + 4h), B3 scalp (15m + 5m?). The tool contract likely needs a
   `timeframe` parameter — enumerate the minimum viable set.
c. What does PYTHAGORAS's skill currently tell it to do without data? Find
   the equivalent of PYTHIA's "MP data not provided" disclaimer — the
   Chunk-D-style skill rewrite will need the same three-state treatment.

## T2 — Supply side: the (A) vs (B) evidence
a. **UW bars inventory:** which UW endpoints serve daily and intraday OHLCV
   (exact endpoint, granularity, history depth, fields) — verify shapes
   live. Confirm intraday granularity supports the T1 timeframe set.
b. **Rate-limit math for (A):** calls per `hub_get_chart_indicators`
   invocation (bars fetch + cache hit rate), expected committee usage
   (passes/day × tickers × agents), against the 120/min · 20K/day budget
   alongside existing production load. Show the arithmetic.
c. **(B) reality check, briefly:** what a TV-push design would require
   (new Pine, alert capacity, payload size for ~10 indicators × N
   timeframes, PREY LIST coverage cap) — enough to compare honestly, no
   more.
d. **Chunk 3 reuse audit:** once Chunk 3's `adx_regime_job.py` exists, which
   pieces (bar fetch, Wilder smoothing, Redis write pattern) generalize to
   a shared indicator library vs SPY-specific code.

## T3 — Computation parity check (the trust question)
a. Probe: compute RSI(14), ATR(14), ADX(14), SMA(20/50) from UW daily bars
   for ~5 liquid tickers (SPY, QQQ, META, AMD, one mid-cap). Compare against
   two independent references (e.g., TradingView's displayed values + one
   public charting source). Document deltas and their causes (session
   handling, adjusted vs unadjusted closes, smoothing variant).
b. Acceptance frame: PYTHAGORAS needs values Nick can cross-check against
   his own TV charts without confusion. If UW-computed RSI reads 58 while
   his chart shows 62, that mismatch must be explained (and documented in
   the tool's response or the skill) or architecture (A) loses points.
c. VWAP special case: intraday VWAP needs intraday bars + session anchoring
   — confirm UW data supports it or mark VWAP as a phase-2 field
   (explicit null at launch, PYTHIA single_prints precedent).

## T4 — Tool contract draft
a. `hub_get_chart_indicators(ticker, timeframe?)` envelope per hub
   conventions (status / data / staleness / schema_version): the field set
   from T1, per-field nulls with reasons (no unlabeled zeros — sb3
   convention), `as_of` + bar-close timestamps, and the computed-vs-pushed
   provenance field (post-B4 backlog item #4 taught us provenance matters).
b. Caching design: indicator values per (ticker, timeframe) with a TTL
   matched to bar cadence (daily indicators don't change intraday except
   the developing bar — decide and document how the developing bar is
   handled: include-partial vs last-closed-bar-only. Prior: last-closed
   plus a separate `developing` block, never silently mixed).
c. Registration: 14th hub MCP tool, same FastMCP pattern as
   `market_profile.py` — name the files.

## T5 — Olympus impact + rollout shape
a. PYTHAGORAS SKILL.md current Context-A call list (it has one — quote,
   composite, flow radar, positions per the PYTHIA precedent) — where the
   new tool slots, and the three-state (ok/stale/unavailable) caveat
   rewrite, mirroring B4 Chunk D's five-edit pattern.
b. Mandatory post-build full-committee regression on a known-good ticker
   (B4 precedent — SPY). Spec the pass criteria now: real indicator values
   used + labeled, nulls never fabricated, other agents unchanged,
   PYTHAGORAS stays in the trend/structure lane (no MP claims — that is
   PYTHIA's).
c. Recommended Phase 1 chunks, smallest-first, each shadow-safe. Expected
   shape if (A) wins: (1) shared indicator library + parity tests, (2) the
   read-only MCP tool, (3) skill wiring + regression. No webhook, no
   cutover night, no re-arm.

---

## Gate report — required output
`docs/phase0-pythagoras-feed-findings.md`: (1) data contract from the skill,
(2) the (A)/(B) decision with rate-limit math + parity evidence, (3) Chunk 3
reuse map, (4) tool contract draft, (5) skill-wiring + regression plan,
(6) open questions. Then **STOP** for architecture review.
