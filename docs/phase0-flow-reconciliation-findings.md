# Phase 0 Findings — Flow Reconciliation (Chunk 2, read-only)

**Date:** 2026-06-10 | **Analyst:** Claude Code | **Mode:** Read-only (code reads + SELECTs)
**Origin:** Chunk 2 of sub-brief 3. 2b DELETE was **cancelled** — 2a refuted "P4A subsumes P2" (delete would blind 627 signals; the two disagree on direction ~26% of the time). This characterizes the disagreement and proposes reconciliation options **without choosing**. Both paths stay live as-is; no delete, no scoring change.

---

## TL;DR
The two live flow paths measure **different instruments over different windows**, so directional disagreement is structural — not a sign-convention bug. But the **43 opposite-sign cases are dominated by one checkable pattern**: P2's *single ~14-DTE volume* P/C ratio reads **near-term hedging flow as directional conviction**, firing large false-bearish penalties (XLK pc=**13.31** → −13 on a LONG) exactly where P4A's premium-weighted all-expiry view reads BULLISH (+10). Net: where they oppose, **P2 is the more error-prone path for *direction***; P4A is more robust but can be **stale** (4-hour window). Both are summed live today → contradictory bonuses partially cancel or double-count.

---

## 1. How each path works (code map)

| | **P2 — yfinance** (`flow_enrichment.py`) | **P4A — UW** (`uw_flow_poller.py` → `pipeline.py`) |
|---|---|---|
| Instrument | **Single** ~14-DTE expiry (first expiry ≥ 14d), strikes ±20% | **All** expiries summed |
| Window | yfinance live, 30-min Redis cache | flow_events, 5-min poller, **4-hour** lookback (latest row) |
| Direction basis | `net_premium = call_prem − put_prem` sign **+** *volume* P/C banding | `sentiment` from P/C (0.7/1.3) **+** premium-2× override |
| Bonus | scorer `:545-581`, **±13** (P/C bands + dir-align ±3/−5) | pipeline `:412-441`, requires **$2M+** premium, **−3…+6** |
| Refs | `:89-95` expiry, `:104-110` strikes, `:115` P/C, `:124-125` dir | poller `:52-83` agg, `:96-107` sentiment; pipeline `:392-394` window |

Neither sign convention is internally wrong: P2 (more puts = bearish), P4A (more puts = bearish) are individually consistent.

---

## 2. The 43 opposite-sign cases (10-day sample, live `triggering_factors`)

282 signals had both bonuses; **43 (~26%) opposed in sign.** Top by combined magnitude:

| Ticker | Dir | P2 P/C | P2 dir | P2 bonus | P4A bonus | P4A sentiment |
|---|---|---|---|---|---|---|
| MSFT | LONG | 3.11 | bearish | **−13** | **+10** | BULLISH |
| XLK | LONG | **13.31** | bearish | −13 | +6 | BULLISH |
| AMD | LONG | 2.65 | bearish | −13 | +2 | NEUTRAL |
| XOM | LONG | 6.94 | bearish | −13 | +2 | NEUTRAL |
| BAC | LONG | 2.62 | bearish | −13 | +2 | NEUTRAL |
| XOM | LONG | 1.05 | bearish | −5 | +10 | BULLISH |
| COIN | SHORT | 1.89 | bearish | +8 | −3 | BULLISH |
| PLTR | SHORT | 2.78 | bearish | +8 | −3 | BULLISH |
| XLF | LONG | 0.34 | bullish | +8 | −3 | BEARISH |

### Disagreement taxonomy
- **(A) Near-term put skew misread as direction — the dominant + most checkable bucket.** Extreme ~14-DTE P/C (XLK 13.3, XOM 6.9, MSFT 3.1, AMD 2.6, BAC 2.6) → P2 −13 false-bearish on LONGs, while P4A's all-expiry premium reads BULLISH/NEUTRAL. A 14-DTE P/C of 13 is **hedging volume**, not conviction. P2's *volume*-based P/C on a single front expiry structurally conflates the two. **This is the strongest "checkably wrong" signal — against P2 for direction.**
- **(B) P4A $2M-threshold gap.** Mid-range P/C (~1.0–1.5) where P2 fires a penalty but P4A is NEUTRAL/+2 (premium under the $2M bar). A coverage/threshold mismatch, not a contradiction of fact.
- **(C) Genuine timeframe split.** COIN/PLTR shorts: P2 (near-term bearish) confirms the short; P4A (all-expiry bullish) contradicts. Real near-term-vs-structural disagreement — neither provably wrong.

### Checkable-wrong verdict
- **P2:** *volume* P/C on a single ~14-DTE expiry is the more error-prone path for **direction** (bucket A). Its premium-direction field (`call−put` sign) is fine; the **volume P/C banding** is the conflation source. Not "broken," but measuring conviction with a hedging-contaminated proxy.
- **P4A:** more robust for direction (premium-weighted, all-expiry) but the **4-hour lookback can carry stale sentiment** after an intraday reversal — a real freshness risk to verify in any merge.

---

## 3. Reconciliation options (NOT choosing — for the eventual build brief)

- **(A) P4A-primary + P2 gap-fill.** Use P4A where present; fall back to P2 only when P4A is absent (covers the 627 P2-only signals). Caveat: gap-fill should likely use a **premium-weighted** P2 variant, not raw volume P/C (bucket A).
- **(B) Weighted blend with disagreement dampening.** Combine both (premium-weight P4A higher); when they **oppose**, shrink both toward zero rather than summing contradictions.
- **(C) Expiry-bucketed merge (separate factors).** Stop treating them as one "flow" sum. P2 = a *near-term* (~14-DTE) flow factor; P4A = a *structural* (all-expiry) factor. Near-term hedging vs structural positioning are different signals and should score independently.
- **(D) Fix P2's conflation in place.** Switch P2 direction to premium-based and damp obvious hedging (extreme P/C with offsetting premium) before it ever bands.

Leading combinations to weigh later: **(C)+(A)** (bucket the timeframes, P4A-primary for structural) and **(D)** (de-contaminate P2). Decision deferred with evidence.

---

## 4. Live state / risk note (no change made)
Per ruling, **both paths remain live, summed, unchanged.** Standing risk while in this state: on the ~26% opposing signals the two bonuses partially cancel (e.g., MSFT −13 vs +10) or, on agreeing signals, double-count (Chunk 2a: avg combined |bonus| 11.61). Flagged, not acted on — reconciliation is a future chunk.

---

## 5. Open questions for review
1. Endorse the read that **P2's single-expiry *volume* P/C is the directional weak link** (bucket A)? That steers toward (C)/(D).
2. Is the **P4A 4-hour staleness** acceptable for it to be "primary," or does that need a freshness guard first?
3. Preferred reconciliation direction to draft into a build brief — (C)+(A), (D), or a blend?

*Phase 0 complete. No code, no scoring change. Both paths live as-is. Gate report returns here.*
