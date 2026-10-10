# Registration phoenix-washout-v1: PHOENIX | Uptrend Dip-Buy, washout variant, LONG (R-IV.855(d))

Status: **REGISTERED**. Sections 1–10 are immutable once hashed; any change is phoenix-washout-v2.
Filed: 2026-10-10, written after a measured 05:26:09 UTC (Fri 2026-10-09 23:26 MDT), **before any
forward data exists**. The first forward session is Mon 2026-10-12.
Mode: CONFIRM, a forward test in SHADOW. **Grader: CC-QUERY.** LAB does not grade it.
Hash: sha256 of this file as committed, relayed with the commit to SPINE and QUERY.

**This is a NEW variant, not PHOENIX as coded.** PHOENIX as coded (`NEMESIS_LONG`) stays SHADOW,
unchanged (R-IV.855(c)). This variant drops PHOENIX's candle and volume tests. In Task 5 it was
control (B); the guardrail says that replay can't prove it, so it is tested forward here.

## 1 · Definition text
A LONG fires at the close of session t when ALL hold, on fully adjusted daily bars, by PHOENIX's
own arithmetic (`backend/strategies/wrr_buy_model.py`):
1. close > the 200-session simple mean of closes (`:128-131`), with ≥ 205 of the ticker's own bars;
2. RSI(3) ≤ 10, PHOENIX's plain-mean RSI (`_compute_rsi`, `:42-55`);
3. ROC(10) ≤ −8% (`:138-143`).

No candle test, no volume test.

## 2 · Code commit
- **Commit:** `e5e92b170bace5cb9dde14349616d62839477ffa` (branch `claude/lab-register-t5`).
- **Frozen blobs:**
  - `backend/strategies/registered_shadow.py` `97de7f6f3a964c938ea5af2fad5444a58d570bb0`
    (`phoenix_washout`; emits `PHOENIX_WASHOUT` / `phoenix_washout`);
  - `backend/strategies/wrr_buy_model.py` `2d83451cd6dc1f6e6bc422f40c1848ff5e94d161` (the
    thresholds it reads);
  - `scripts/lab/forward_registered.py` `3491299de8912df8f770cc6652fa5300562d76ee`;
  - `scripts/lab/replay_t5.py` `a8b8197fb23c87e2fab66218d181d597a41cc657`;
  - `scripts/lab/market_state.py` `904fd76ee552e1dfdc252705d9de6a99795bb080`.
- **Parity on the Task 5 snapshot:** 4,742 fires against control (B)'s 4,743. The one difference
  is a Task 5 artefact (its 205-bar guard counted pre-IPO calendar rows for one UBER session).

## 3 · Universe
The 196 names frozen in `registered_shadow.UNIVERSE`, survivorship-biased; sector-ETF subset
reported.

## 4 · Entry price
The next session's open (split-adjusted, dividend-unadjusted). It is known before that open: the
07:00 ET job uses the prior session's final bar.

## 5 · Horizons
- **Primary h = 3.** Secondary: h = 1, 2, 5, 10.
- **Why h = 3.** The cell is WITH-TREND LONG, which has no provenance ceiling: C5 and F5 do not
  reach it (R-IV.838(c)). The WRR family's stated hold is 2–3 days (`wrr-buy-model.md:42`), and
  PHOENIX as coded has no hold of its own, so the family's upper bound is used.
- Declared plainly: in Task 5 every headline horizon of this variant was positive, so h = 3 is
  not the one cherry-picked from a mixed set.

## 6 · Primary metric
The **date-mean market-adjusted return at h = 3** (r_adj as in the skill §3.3), with the
date-clustered t.
- Reported beside it: the pooled and raw means, the median, the hit rate, the STACK-FIRST split,
  and 0.10 / 0.25% cost sensitivity.

## 7 · Controls
- **(A)** the same tickers on every session above their 200-day.
- **(C)** same date: every universe name above its 200-day on each fire date. Difference averaged
  over fire dates.

## 8 · Decision rule (QUERY, at the read)
| condition at the read | decision |
|---|---|
| n < 30 OR < 20 distinct dates | INSUFFICIENT if the hard stop has passed; else not read |
| minimums met, date-mean r_adj(h=3) ≤ 0 | **FAIL** |
| minimums met, date-mean > 0, t ≥ 2.0, AND control-(C) difference > 0 | **PASS** |
| minimums met, anything else | **HOLD** (any extension is a new registration) |

PASS is necessary, not sufficient, for SURFACE: stage 2 ETF-only, a TA note and the principal's
yes are all also required.

## 9 · Minimum n and minimum distinct dates
- **Minimums:** n ≥ 30 AND ≥ 20 distinct dates.
- **Expected satisfaction, declared:** the replay rate was 4,742 fires on 1,686 dates over 19.7
  years, about 240 fires and 85 dates a year. Both minimums are expected within about three
  months (by about 2027-01). Reachable.

## 10 · Stop date
- **When:** the last session of the first calendar month at which `forward_registered.py
  --count-only` shows both minimums met. QUERY runs it monthly; it is outcome-free.
- **Hard stop: 2027-10-08.**
- **The read:** run no earlier than 15 sessions after the stop session.

## Lifetime tries counter (PHOENIX family)
2: V-CODE (Task 5), plus this washout variant.
