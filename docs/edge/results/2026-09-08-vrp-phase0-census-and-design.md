# VRP STUDY — PHASE 0 DATA CENSUS + PROPOSED DESIGN (R-IV.328)

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD, OLYMPUS-TRITON, EDGE
**Vintage (in-DB UTC): `2026-09-09 02:30:57.997130+00`** · read-only
**NO NUMBERS COMPUTED.** This is a census and a proposal. Nothing below is a result, and the
design requires spine's ratification before any figure is produced.

---

# PART 1 — DATA CENSUS

## (a) VIX — NOT stored as a series, but RECOVERABLE from jsonb

**No VIX bar series exists.** `stable_daily_bars` holds no `VIX` or `^VIX`, and **zero columns
named `vix` exist in any table in the schema.** Only the tracking ETFs are present:

| ticker | bars | range |
|---|---|---|
| VXX | 1,299 | 2021-07-06 → 2026-09-04 |
| UVXY | 1,299 | 2021-07-06 → 2026-09-04 |

**But the raw level is captured inside `factor_readings.metadata`:**

| factor | distinct days | range | rows with `vix` | rows with `vix3m` | rows with `iv_rank` |
|---|---|---|---|---|---|
| `iv_regime` | **414** | 2025-04-24 → 2026-09-09 | 19,229 | 0 | 18,967 |
| `vix_term` | **198** | 2026-02-20 → 2026-09-09 | 18,321 | **18,321** | 0 |

Sample payloads, verbatim:
```
iv_regime : {"vix": 15.72, "iv_rank": 11.1, "rank_source": "52w_yfinance",
             "vix_52w_max": 33.82, "vix_52w_min": 13.47}
vix_term  : {"vix": 15.720000267, "vix3m": 18.3899993896, "ratio": 0.8548124409340682,
             "level_mod": 0.0, "term_score": 0.2}
```

**So the study has VIX over 414 trading days and the VIX/VIX3M term structure over 198.**
These are **intraday readings (~100/day), not daily closes** — a daily series requires picking
one reading per day by a stated rule, and that rule is a design decision, not a given.

## (b) SPY / QQQ daily bars — complete and aligned, but stale

| ticker | bars | distinct dates | range |
|---|---|---|---|
| SPY | 1,299 | 1,299 | 2021-07-06 → **2026-09-04** |
| QQQ | 1,299 | 1,299 | 2021-07-06 → **2026-09-04** |

- **Zero duplicate dates** (bars = distinct dates on both).
- **Zero gaps longer than 4 calendar days** — no missing week, no holiday hole beyond a long weekend.
- **Zero SPY dates missing a QQQ bar** — the two series are perfectly aligned for pairing.

**Staleness flag:** bars end **2026-09-04** while VIX readings run to **2026-09-09** — the bar
writer is ~3 trading days behind. Source is `backend/stable_engine/bars_yf.py` (**yfinance**),
the same dependency under active investigation elsewhere. **Not diagnosed here.**

## (c) OPTION CHAIN HISTORY — NONE, AND NONE FETCHABLE

**No stored chain history.** Schema sweep for `option|contract|chain|greek|iv_|expiry` returns
exactly two tables, neither of which is a chain archive:

- `options_positions` — the book's own positions
- `signal_options_expressions` — expressions attached to signals

**No historical option endpoint exists in the client.** Every option-side function takes a
ticker (and sometimes an expiry) and **no date**:

```
get_options_snapshot(...)      get_flow_recent(ticker)        get_flow_per_expiry(ticker)
get_greek_exposure(ticker)     get_iv_rank(ticker)            get_max_pain(ticker)
get_single_option_value(...)   get_ticker_greeks_summary(...)
```

**Consequence, and it is the governing fact of this Phase 0: the hub cannot price a historical
option spread.** There is no record of what any 30–45 DTE SPY or QQQ spread cost on any past
day, and none can be fetched. The same shape as tide and dark pool — live fetch, no sink, no
backfill through the client.

## (d) IMPLIED-vs-REALIZED PROXY — YES, COMPUTABLE, ON A BOUNDED WINDOW

Both legs exist:
- **Implied:** VIX from `factor_readings.metadata`, 414 days; term structure 198 days.
- **Realized:** computable from SPY/QQQ closes, 1,299 bars, complete and gap-free.

**The binding constraint is VIX, not bars.** The overlap is **414 trading days (~17 months)**
for a level study and **198 (~9.5 months)** for anything using term structure — against 1,299
days of price history that cannot be used without an implied leg.

---

# PART 2 — PROPOSED DESIGN, FOR RATIFICATION

## The honest framing, stated first

**The question spine posed cannot be answered as a backtest with the data the hub holds.**
"What would a defined-risk short-premium program have returned, net of friction" requires
historical option prices. There are none, and none are obtainable retrospectively.

**What can be answered is the conditioning question underneath it:** *was implied volatility
richer than subsequent realized volatility, by how much, and in which realized-vol regimes* —
which is the premium a short-premium program harvests, before structure and before friction.

I propose registering that, **named as a proxy study rather than a strategy result**, with the
backtest deferred to the sinks build. A study that reports strategy returns from a VRP proxy
would be reporting a number its data cannot support.

## PS-01 — PROPOSED PRE-REGISTRATION

**MODE:** EXPLORE (descriptive). Findings eligible only as future pre-registrations.

**HYPOTHESIS.** Over the observed window, VIX exceeds subsequent SPY realized volatility, and
the excess varies systematically with the realized-volatility regime at observation time.

**POPULATION.** Trading days on which both a VIX reading and a complete forward SPY bar window
exist. **Expected n ≈ 414 minus the forward horizon**, to be stated exactly at execution and
gated.

**DAILY VIX RULE (must be fixed before any computation).** The **last `iv_regime` reading
whose timestamp falls at or before 20:00 UTC** on each trading day. Stated so the intraday
series becomes a daily one by a rule, not by whichever aggregate is convenient.

**PRIMARY ENDPOINT.** `VRP = VIX(t) − RV(t, t+21)`, where `RV` is annualized close-to-close
realized volatility over the next 21 trading days, in the same units as VIX. **21 trading days
is the fixed horizon**, chosen as the midpoint of the 30–45 DTE window the program describes.

**SECONDARY ENDPOINTS.** (i) the same at 15 and 30 trading days, reported as sensitivities,
never as the headline; (ii) VRP conditioned on term structure (`vix/vix3m`) on the 198-day
sub-window, labeled as a shorter population.

**CONDITIONING.** Realized-vol **terciles measured on the trailing 21 days at observation
time** — S7's cut, applied backward-looking so it is knowable at decision time. **Terciles are
cut on the whole population once, not within any subgroup.**

**GATES.** n ≥ 100 per cell or **NOT COMPUTABLE**. Wilson intervals on any rate; bootstrap or
stated-SE on any mean. **Effective n is days, and overlapping 21-day forward windows make
adjacent observations dependent** — so intervals must be computed on non-overlapping blocks or
explicitly labeled as overstating confidence. This is the error the third market read exposed
in the Triton work and it applies with full force here.

**FRICTION.** **Not modeled, and the study says so on its face.** No option quote exists at any
past instant. A VRP figure is a gross premium, not a return. **Any statement of the form
"this would have returned X net of Y" is out of scope for PS-01 by construction.**

**FALSIFIERS, stated before the data is read.**
1. If mean VRP at 21d is ≤ 0 across the pooled window, the premise fails outright.
2. If VRP's sign differs across realized-vol terciles, "it pays" is regime-specific and the
   pooled figure is not the finding.
3. If removing the single largest VRP month flips the pooled sign, the result is one episode —
   **the ex-one-period test is registered in advance**, because the Triton work found exactly
   that and only found it by looking.
4. If the 15d and 30d sensitivities disagree in sign with the 21d headline, the horizon choice
   is doing the work and no horizon is reportable.

**WHAT WOULD UPGRADE THIS TO THE QUESTION ACTUALLY ASKED.** A stored option chain — strike,
expiry, bid, ask, IV at capture — for SPY and QQQ, 30–45 DTE, daily. That is a **forward
collection** item for the sinks build. Once it accrues, PS-02 can price actual defined-risk
structures at actual quotes and answer the net-of-friction question. **Until then the honest
deliverable is the premium, not the program.**

## What I have NOT done

No figure has been computed. No VIX value has been extracted, no realized vol calculated, no
tercile cut. The census above reports **what exists**; every number in it is a row count, a
date range, or a field name.
