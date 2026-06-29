# L1a Auction+Flow Gate — Week-1 Shadow Review & Committee Handoff

**Date:** 2026-06-29 (1 week after shadow-live 2026-06-22) · **For:** Claude / Olympus committee (PYTHIA, PIVOT, DAEDALUS)
**Status:** SHADOW-LIVE, tag-only, diverts nothing · **Verdict: NOT enforce-ready — root cause identified (fixable)**
**Repro (read-only):** `python scripts/l1_shadow_measure.py` + the diagnostic SQL in §4.

---

## 1. TL;DR

In one week the gate tagged **563 signals**; only **53 were in-scope** (liquid-20), and of those the full-confirmation `pass` fired **exactly once**. The cause is **not** the flow logic and **not** (mainly) threshold tightness — it's that **the PYTHIA Market-Profile feed covers a ticker set that barely overlaps the L1a liquid-20 universe.** 13 of the 20 liquid names have no usable MP, so their auction half can never reach `fresh_accepted`. Fix the feed/universe alignment (or decouple the auction half) before enforce. Flow half is healthy. Edge is unmeasured (0 resolved passes).

## 2. Gate outcomes (since 2026-06-22, n=563)

| Gate | n | meaning |
|---|---|---|
| out_of_scope | 510 | non-liquid — gate correctly inert |
| asterisk | 29 | in-scope; flow confirms but auction NOT fresh_accepted (or flow weak) |
| fail | 23 | in-scope; flow contradicts the signal's direction |
| **pass** | **1** | in-scope; flow confirms **and** auction fresh_accepted |

In-scope = 53. Flow was `fresh` for all 53 (the Path-A/cached-quote restore is feeding it; the v1 `flow_bonus≠0` limitation did not bite this week).

## 3. Why `pass` is starved — the auction half

**Auction state × acceptance-heuristic (in-scope):**

| auction_state | accepted | n | reading |
|---|---|---|---|
| asterisk | false | 27 | heuristic rejected (mostly correct — see below) |
| asterisk | null | 12 | heuristic indeterminate (interp/direction mismatch) |
| **asterisk** | **true** | **5** | **heuristic ACCEPTED but MP was STALE → killed by freshness** |
| closed | null | 7 | signal fired outside RTH |
| **fresh_accepted** | true | 2 | the only auctions that *could* pass (→ 1 pass, 1 flow-too-weak) |

**`fresh_accepted` = 2/53 (3.8%) is the binding constraint.** Decomposing the 51 non-passes:
- **MP coverage gap (root cause):** only ~7/20 liquid names have a live MP feed. **11 liquid names have ZERO `pythia_events` this week — SPY, GOOGL, TSLA, SMH, IWM, TLT, ISRG, INTU, FXI, HYG, ZS** — and 2 are stale (MSFT last 174h ago, AMD 96h). For these 13 names the auction is *structurally* asterisk forever. (Meanwhile PYTHIA pushes MP for ~40 NON-liquid names — AMAT, PG, SLB, SNAP, MCD, BKNG, IONQ, … — the Pine feed's universe is misaligned with L1a's.)
- **Intra-signal staleness:** even when the heuristic accepts (7 cases), MP was fresh in only 2 → **5/7 accepted setups lost to freshness.**
- **RTH:** 7/53 fired outside regular hours (`closed`).
- **Regime:** the dominant auction interpretation this week was *"Price above VAH in thin extension – caution"* (23/53). The heuristic rejects chasing it — arguably **correct** behavior, not a bug.

## 4. MP feed coverage vs the L1a liquid-20 (the evidence)

`pythia_events` recency, liquid-20 only:

| Has FRESH MP (≤~4h) | Stale MP | **ZERO MP this week** |
|---|---|---|
| AAPL, AMZN, NVDA, QQQ, META, AVGO, XLK | MSFT (174h), AMD (96h) | **SPY, GOOGL, TSLA, SMH, IWM, TLT, ISRG, INTU, FXI, HYG, ZS** |

> SPY — the single most important name — has **no** MP feed; QQQ does. The 1 `pass` all week was AAPL LONG (a fresh-MP name).

Query: `SELECT ticker, COUNT(*), MAX(timestamp) FROM pythia_events WHERE timestamp >= '2026-06-22' GROUP BY ticker;` cross-referenced to `config/liquid_universe.LIQUID_UNIVERSE`.

## 5. Flow half — healthy, working as intended

| flow_aligned | n | avg dominance ratio | range |
|---|---|---|---|
| true (sign matches dir) | 23 | 0.280 | 0.021–0.794 |
| false (contradicts) | 30 | 0.274 | 0.036–0.903 |

Flow aligns ~43% of the time; when aligned the dominance ratio averages **0.28, well above the 0.15 threshold** — so the threshold is not the bottleneck. The 23 `fail`s are dominated by **contrarian SHORTs fighting bullish flow** (GOOGL/AMZN/NVDA/AAPL SHORT) — the gate flagging shorts against the tape, which is plausibly the gate doing its job. (`fail` resolved avg_pnl −0.26 is weak corroboration, small N.)

## 6. Edge check — INCONCLUSIVE

`pass` has **0 resolved outcomes** → the gate's actual edge is unmeasured. Resolved buckets (small-N, noisy): asterisk avg_pnl −1.06, fail −0.26, out_of_scope −0.58. No usable signal yet.

## 7. Decision options (for the committee)

- **A — Align the MP feed universe (highest leverage).** Extend the PYTHIA Pine feed to push MP for all 20 L1a-liquid names (esp. SPY/QQQ/GOOGL/TSLA), and/or trim the ~40 non-liquid names it currently pushes. Makes L1a work as designed (full auction confirmation). Requires Pine/webhook work + a re-bake week.
- **B — Decouple the auction half (ship sooner).** Redefine the gate so *absent* MP → flow-primary decision (`pass` on flow-confirm alone; auction recorded as a non-blocking asterisk), reserving full `pass` semantics for names that do have MP. Ships L1a as a flow-gate now, auction as a bonus where available.
- **C — Narrow the enforce universe** to the ~7 MP-covered liquid names initially; expand as feed coverage grows.
- **D — Revisit MP freshness threshold** (the 5/7 accepted-but-stale cases) and the RTH handling (7 closed).

**CC recommendation:** A is the "correct" fix but gated on Pine-feed work; **B is the pragmatic path** to get L1a delivering value now without waiting on feed coverage, with A as the follow-on. Either way, **do not enforce on the current 1-week data** — `pass` is too rare and its edge is unmeasured.

## 8. Standing enforce gates (unchanged)
sb3 ADX-regime promote (regime-conditioning still `deferred_sb3_null`) + full Olympus committee pass + Nick's greenlight. This review addresses none of those — it surfaces a prerequisite feed-coverage problem that must be resolved (A/B/C) first.
