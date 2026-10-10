# Carry measure: definition (R-IV.823(i), Task 6)

**Dated:** 2026-10-10, written after a measured 07:56:05 UTC (Sat 2026-10-10 01:56 MDT).
**Status:** DEFINITION ONLY, for **display**. Unregistered. Not a signal, not a filter, and not an
input to any strategy or to the bias composite.
**Forward test:** to be registered under the strategy-lab protocol (skill §2) **after Triton's read
7 (Fri 2026-11-06)**, not before. Until then it is never applied to Triton rows (the rule of
R-IV.677(c), followed here).
**Exploration slots:** this uses one. **The third slot stays empty** (R-IV.823(i)).

## Why these two pairs
AUDJPY and MXNJPY are yen-funded carry trades: long a high-yielding currency, short the
low-yielding yen. When carry positions are unwound, both fall together and fast, because the
funding leg is bought back at once. One pair is a G10 commodity currency, the other an
emerging-market currency, so a joint move is less likely to be one country's news.

## Inputs
- **Daily closes** of `AUDJPY=X` and `MXNJPY=X` from yfinance (the Stable Engine's source; the strip
  captures them from 2026-10-10, `backend/stable_engine/strip.py`).
  - The intraday points kept in `stable_intraday_points` are for display.
  - The measure itself uses **daily closes**.
- **Session calendar:** FX trades almost 24/5. A "session" here is a US equity trading day
  (`stable_engine/market_calendar.py`), and the close is the last yfinance daily close on or
  before that day. A missing pair-close leaves the day's measure **UNAVAILABLE**: it is never
  carried forward.

## The measure
For each session t:
1. **Basket return:** R_t = ½ · [ln(AUDJPY_t / AUDJPY_{t−1}) + ln(MXNJPY_t / MXNJPY_{t−1})].
2. **Five-session carry move:** C5_t = R_{t−4} + … + R_t.
3. **Scale:** σ_t = sample standard deviation of R over the 60 sessions ending **t−1** (at least 50
   valid). Fewer than 50 → UNAVAILABLE.
4. **z:** z_t = C5_t / (σ_t · √5).
5. **State:**

| state | rule |
|---|---|
| **UNWIND** | z_t ≤ −2.0 |
| **STRESS** | −2.0 < z_t ≤ −1.0 |
| **CALM** | z_t > −1.0 |
| UNAVAILABLE | any input missing, as above |

## Display (when the principal approves one)
z_t and the state beside DXY and USDJPY, with both pairs' levels and day changes. Today those are
served under `fx_capture` by `/api/stable/fx`. Not wired to any screen until approved.

## What the forward test will ask (to be fixed at registration, after read 7)
- **Candidate hypothesis:** in UNWIND (and STRESS), the next 1–5 sessions of SPY and QQQ show a
  lower market return and a higher realised volatility than in CALM.
- **At registration, not now:** the primary metric, horizon, decision rule, minimum n (in UNWIND
  *episodes*, not days, because unwinds cluster) and stop date. They are decided before any forward
  data, under skill §2.
- **No historical replay is run before registration.** Any replay would be exploration and would
  count on a tries counter.

## Change log
- 2026-10-10: v0, the definition (R-IV.823(i)).
