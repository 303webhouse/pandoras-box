# NEMESIS | Washout Reversal: the March-approved WRR Buy/Sell Day (N4)

The name means this spec only (R-IV.843(d)). The June "Nemesis v0.2" acceleration spec is
**IMPULSE (v0.2, 2026-06-16)**, SPEC-ONLY (`docs/codex-briefs/2026-06-16-nemesis-spec.md`).

| field | value |
|---|---|
| signal_type / strategy keys | approved: `WRR_LONG`, `WRR_SHORT`, lane `COUNTERTREND` (`docs/approved-strategies/wrr-buy-model.md:45-46`). **No code emits either.** |
| emitting code | **none.** The coded `NEMESIS_LONG` is a different rule set with its own card: [phoenix.md](phoenix.md) |
| side | BOTH (approved) |
| grid cell | **BEFORE THE TURN**, LONG and SHORT. It fades a 3+ day move at an extreme bias with RSI(3) at an extreme, on the reversal bar, with no trend confirmation |
| incumbent it would replace | none named |
| schedule / trigger | approved: once daily after the close, 4:15 PM ET (`docs/build-plans/phase-5-countertrend-lane.md:51`) |
| status | **SPEC-ONLY**. Not implemented on either side; never counts as coverage (R-IV.830(e)) |
| bucket ceiling | **B3 or TAIL** (before-the-turn, R-IV.823(c)3). **SHORT side carries the no-fly flag "entering parabolic shorts too early".** |
| lifetime tries counter | **3** (V-SPEC variants a/b/c, 2026-10-10) |

## Rules as approved
Olympus 2026-03-16 "APPROVED with conditions" (`wrr-buy-model.md:9`); Titans 2026-03-17 (`:62`).

**Countertrend lane** (`:11-18`): whitelisted strategy only; composite bias ≤ 25 for longs and
≥ 75 for shorts, on the March 0–100 bias scale (`:14`); confluence threshold 90 (`:15`); half size
(`:16`); 24–48 h expiry (`:17`).

**Long, Buy Day** (`:22-29`), all of:
1. composite bias ≤ 25 (`:23`);
2. 3+ consecutive down days OR a new 20-day low (`:24`);
3. daily RSI(3) ≤ 15 (`:25`);
4. a reversal candle: bullish engulfing, hammer, or doji with lower wick > 2× body (`:26`);
5. reversal-bar volume ≥ 1.5× the 20-day average (`:27`);
6. within 1 ATR of key support: prior swing low, VWAP or round number (`:28`);
7. ROC(10) "deeply negative". **No number given** (`:29`).

**Short, Sell Day** (`:32`): "Mirror: composite bias ≥ 75, 3+ up days or new 20-day high,
RSI(3) ≥ 85, bearish reversal candle, volume spike at resistance." No ROC figure and no ATR
wording for the short side.

**Risk** (`:37-42`): stop at the reversal low − 0.5 ATR (short: high + 0.5 ATR). TP1 1.5R, take
half; TP2 the 3-day SMA or VWAP reversion. **Max hold 2–3 days. Not a swing trade.**

## Rules as coded
None. See [phoenix.md](phoenix.md) for what was built under this name and the 22-point
difference list.

## For the replay (R-IV.809(g), Task 5)
Before any result, the replay must declare mechanical forms of:
- **"key support"** (`:28`);
- **"deeply negative" ROC** (`:29`);
- **the short side's missing ROC and ATR terms** (`:32`).

The bias condition is replayed only if a stored composite history covers the window; otherwise it
is recorded as not replayable. The March scale (0–100) is not the live composite's (−1..+1;
`backend/signals/pipeline.py:725-740`), so any mapping is itself a declared choice.

## Evidence so far
None. No implementation has ever emitted `WRR_LONG` or `WRR_SHORT`.
- **Task 5 replay (R-IV.850(e); `C:\temp\cc-query-handoff\lab
emesis-replay-TASK5-RESULTS.md`, results sha256 `2964fc9e…`): yfinance daily 2007-01-03 → 2026-09-30, 196 names (survivorship-biased), next-open entry, market-adjusted, date-clustered t. REPLAY, not a verdict.** V-SPEC without the bias condition (not replayable), three declared ROC variants. LONG positive at h3 in all three (date-mean +0.28 to +0.66%, t 1.9–2.5; same-date difference +0.19 to +0.55, t 1.4–2.2), concentrated with SPY below its 200-day and in STACK transition, negative in range. SHORT weak (variant c h1 +0.26, t 2.33 only). Three variants tried: a registration candidate, never a result. Stage 2 owed (needs a ruling on single-name IV).

## Kill rule
LAB proposal (SPINE and QUERY decide): if the V-SPEC replay fails stage 1 market-adjusted at the
1–3 day horizons on both sides, the spec is retired without being built.

## Change log
- 2026-03-16: approved (Olympus). 2026-03-17: Titans; data source edited to Polygon-first (d246794).
- 2026-10-09: card v0 (R-IV.823(g)). Status SPEC-ONLY.
- 2026-10-10: named NEMESIS | Washout Reversal; the June spec renamed IMPULSE (R-IV.843(d)(e)).
