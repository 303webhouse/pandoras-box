# Registration nemesis-long-v1: NEMESIS | Washout Reversal, LONG (R-IV.855(d))

Status: **REGISTERED**. Sections 1–10 are immutable once hashed; any change is nemesis-long-v2.
Filed: 2026-10-10, written after a measured 05:26:09 UTC (Fri 2026-10-09 23:26 MDT), **before any forward data exists**. The first forward session is Mon 2026-10-12.
Mode: CONFIRM, a forward test in SHADOW. **Grader: CC-QUERY.** LAB does not grade it.
Hash: sha256 of this file as committed (`git show <commit>:<path> | sha256sum`), relayed with the
commit to SPINE and QUERY.

## 1 · Definition text (the March spec read literally, one variant)
Source: `docs/approved-strategies/wrr-buy-model.md`, approved 2026-03-16 (Olympus) and 2026-03-17
(Titans). Mechanical forms as declared in Task 5 §1
(`C:\temp\cc-query-handoff\lab\nemesis-replay\00-DECLARATIONS.md`, sha256 `270ba5e0…`).

A LONG fires at the close of session t when ALL hold, on fully adjusted daily bars:
1. 3+ consecutive down closes, OR today's low < the lowest low of the prior 20 sessions (`:24`);
2. Wilder RSI(3) ≤ 15 (`:25`);
3. a reversal candle: bullish engulfing (prior bar down; close > open, open ≤ prior close,
   close ≥ prior open), OR a hammer (lower wick ≥ 2× body, upper wick ≤ body), OR a doji
   (body ≤ 10% of range, lower wick > 2× body) (`:26`);
4. volume ≥ 1.5× the mean of the prior 20 sessions (`:27`);
5. within 1 ATR(14, Wilder) of key support: the prior 20-session low, the 20-session VWAP, or
   the nearest round number (step $1 / $5 / $10 / $50 by price band) (`:28`);
6. **ROC(10) < −3%** (`:29`).

**Why this variant is the literal one.** The spec writes ROC(10) as "deeply negative" and gives no
number. Of the three variants Task 5 replayed:
- **b (−3%) is the only number the approving process itself wrote for this spec:** brief 5B's
  scanner, `roc < -3.0` (`docs/codex-briefs/brief-5b-nemesis-countertrend-lane.md:429`), the
  implementation brief Titans approved on 2026-03-17.
- **c (−8%)** comes from a different strategy built later (PHOENIX, commit 9f40b4a).
- **a (−5%)** was LAB's midpoint, with no documentary basis.

The best replay performer was c; it is not chosen. The registration uses brief 5B's strict `<`.
On the Task 5 snapshot, the registered rule and variant b give the identical 1,640 fires.

**The bias condition (`:23`) is recorded, not a gate.** The spec's 0–100 scale has no defined
mapping to the live −1..+1 composite (`backend/signals/pipeline.py:725-740`). `log_signal`
stores the bias snapshot on every row.

## 2 · Code commit
- **Commit:** `e5e92b170bace5cb9dde14349616d62839477ffa` (branch `claude/lab-register-t5`).
- **Frozen blobs:**
  - `backend/strategies/registered_shadow.py` `97de7f6f3a964c938ea5af2fad5444a58d570bb0`
    (the rule: `nemesis_long`; the live job emits `WRR_LONG` / `nemesis_spec`);
  - `scripts/lab/forward_registered.py` `3491299de8912df8f770cc6652fa5300562d76ee` (the grader);
  - `scripts/lab/replay_t5.py` `a8b8197fb23c87e2fab66218d181d597a41cc657` (returns, β,
    statistics);
  - `scripts/lab/market_state.py` `904fd76ee552e1dfdc252705d9de6a99795bb080`.
- If BUILD merges by squash or rebase, these blobs are the identity of the code.

## 3 · Universe
The 196 names frozen in `registered_shadow.UNIVERSE`: the census proxy list, minus SPY (the
benchmark) and BK / MMC / SQ (no bars). It is survivorship-biased by construction (today's names).
The grader reports the sector-ETF subset beside it.

## 4 · Entry price
The next session's **open** after the signal session (split-adjusted, dividend-unadjusted). The
live job evaluates at 07:00 ET on the prior session's final bar, so the signal is known before
that open.

## 5 · Horizons
- **Primary h = 1**: the close of the entry session.
- Secondary: h = 2, 3, 5, 10, reported.
- **Why h = 1 and not the spec's "2–3 days" (`:42`).** NEMESIS is BEFORE THE TURN, whose ceiling
  is **B3 or TAIL** (R-IV.823(c)3). B3 is a one-session trade. That is the CIRCE horizon finding
  (R-IV.830(g)), applied here.
  - The spec's own 2–3 day hold therefore lies outside the ceiling. h = 3 is reported, but it
    cannot be the surfacing figure.
  - Declared plainly: Task 5's h = 1 figure for this variant was near zero (date-mean +0.01%,
    t 0.15). The horizon is chosen by the ceiling, not by the replay.

## 6 · Primary metric
The **date-mean market-adjusted return at h = 1**: r_adj = r − (0.67β + 0.33)·r_SPY over the same
entry → exit window, with β from the 60 sessions ending the session before the signal. It is
averaged by signal date first; the **date-clustered t** goes with it.
- Reported beside it: the pooled mean, the raw mean, the median and the hit rate; split by
  STACK-FIRST state (trend / transition / range); costs of 0.10 and 0.25% round trip, as
  sensitivity only.

## 7 · Controls
- **(A)** the same tickers on every session in the window, LONG.
- **(C)** same date: every universe name on each fire date. The fire-minus-control difference is
  averaged over fire dates.

## 8 · Decision rule (applied by QUERY at the read)
| condition at the read | decision |
|---|---|
| n < 30 fires OR < 20 distinct dates | INSUFFICIENT if the hard stop has passed; else not read |
| minimums met, date-mean r_adj(h=1) ≤ 0 | **FAIL** |
| minimums met, date-mean > 0, t ≥ 2.0, AND control-(C) difference > 0 | **PASS** |
| minimums met, anything else | **HOLD**: no surfacing; any extension is a new registration |

- PASS is necessary, not sufficient, for SURFACE. SURFACE also needs stage 2 (ETF-only, R-IV.855(e)),
  a TA note, and the principal's yes, inside B3 / TAIL.
- **A range-only result is a CONDITIONAL edge** (R-IV.830(g)).

## 9 · Minimum n and minimum distinct dates
- **Minimums:** n ≥ 30 fires AND ≥ 20 distinct signal dates.
- **Expected satisfaction, declared** (verification-laws §1.1): the replay rate was 1,640 fires on
  821 dates over 19.7 years, about 83 fires and 42 dates a year on this universe. Both minimums
  are expected by about 2027-04. Reachable, as shown by the replay's own rate.

## 10 · Stop date
- **When:** the forward window closes on the **last session of the first calendar month** at
  which a count-only run (`forward_registered.py --count-only`: fires and dates, no returns)
  shows both minimums met. QUERY runs it monthly.
- **Hard stop: 2027-10-08.** If the minimums are unmet then, the decision is INSUFFICIENT.
- **The read:** `forward_registered.py <out> --until <stop session>`, run no earlier than 15
  sessions after the stop session, so the h = 10 exits exist.

## Lifetime tries counter
3: the three Task 5 variants (a / b / c). Variant b, registered here as version v1, is not a new
variant.
