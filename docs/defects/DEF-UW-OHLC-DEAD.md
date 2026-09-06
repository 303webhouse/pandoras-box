# DEF-UW-OHLC-DEAD · P2 (outage) · **P1 (the label facet)**

**Registered** 2026-09-05 by R-IV.275(d). **Found** by CC-BUILD 2026-09-05 during the
position-0 outage diagnosis — **it was not what either alarm was about.** **Status:** OPEN.

> ## CORRECTION — 2026-09-06, on CC-QUERY's finding
>
> **Two claims in the original filing were WRONG and are corrected below in place.**
>
> **1. The blast-radius table was wrong.** It listed six `get_ohlc` callers as inheriting the
> yfinance fallback. **They do not.** `get_ohlc` (`uw_api.py:223-279`) contains **zero** yfinance
> references; the fallback lives in `get_bars` (`uw_api.py:623-678`), a **different function**, which
> contains nine. A `get_ohlc` caller gets `None`, not a silent yfinance bar. **The corrected
> two-way split is below.**
>
> **2. The label mechanism was wrong.** The original said the field claims `uw_computed` *"while
> yfinance computed it."* For `backend/services/read_only/chart_indicators.py` that cannot happen — it calls `get_ohlc`, gets
> `None`, and returns the unavailable shell. **The real mechanism is worse, and is
> corrected below.**
>
> **The severities do not move.** The outage is still P2, the label still P1. **What
> changes is the mechanism, and a defect whose mechanism is wrong is a defect that will be
> fixed in the wrong place.**

**Two severities on purpose.** The outage is P2: the fallback works, so no consumer is
returning wrong bars today. **The label is P1**, because the hub tells its readers the bars
came from a server that served none of them.

---

## The outage

UW `/api/stock/{ticker}/ohlc/1d` returns nothing. Every daily-bar fetch falls through to
yfinance at `backend/integrations/uw_api.py:663`.

**Measured twice, on different processes:**

```
2026-09-05, 500-line log buffer
  40 x "UW /ohlc/1d unavailable or empty for <T> — falling back to yfinance"
  15 tickers: COPX GLD HYG IWM QQQ RSP SMH SPY TLT XLE XLF XLK XLP XLU XLY
  40 of 40 fetches fell back.  ZERO served by UW.

2026-09-05 20:41 ET, FRESH BOOT after deploy 2655b8cb — confirmed still dead
  SPY QQQ IWM TLT XLE SMH XLF HYG GLD, same line, same fallback
```

**Nothing alarmed, and that is the defect's shape rather than an oversight.** The fallback
succeeds, so every consumer gets bars, so no error surfaces anywhere. **A fallback that
works silently makes the primary's death invisible** — the same structure as the grader
running on deploys instead of on schedule, and as the six compute-then-discard findings.

## The label facet — P1

`indicators_source` is a **hardcoded string literal**, at
`backend/services/read_only/chart_indicators.py:44` and `:210`:

```
"indicators_source": "uw_computed", "as_of": as_of,
```

It is not derived from anything. **CORRECTED MECHANISM:** `backend/services/read_only/chart_indicators.py`:117 calls `get_ohlc`, which
has **no fallback** — so when UW is dead it returns `None` and the module returns its
*unavailable shell* at `backend/services/read_only/chart_indicators.py`:37. **That shell hardcodes the same string:**

```
"ticker": tkr, "timeframe": timeframe, "spot": None, "bar_count": 0,
"indicators_source": "uw_computed", "as_of": None,
```

**So the field asserts a UW computation on a payload with `bar_count: 0`.** Not *"yfinance
computed it"* — **nothing computed it, and the field still names UW.** The function is
even docstringed *"Honest unavailable shell — never fake-fresh"*, and it is honest about
staleness while asserting a false provenance in the same dictionary. `backend/hub_mcp/tools/chart_indicators.py:23` repeats the claim in
the tool description the committee reads.

**A hardcoded provenance string is a NULL PROVENANCE.** It cannot report anything else, so
it can never be observed to be wrong — the null-verifier law applied to a label rather than
a check. It was true when written and became false without changing.

**P1 because it is an assertion about evidence.** A reader deciding how much to trust a
number asks where it came from; this field answers with a constant.

## Blast radius — TWO PATHS, and only one of them falls back

**This is the corrected table. The original conflated the two functions.**

**Path A — `get_ohlc`: NO FALLBACK. These callers get `None` when UW is dead.**

| caller tag | site |
|---|---|
| `ohlc_bars` | `backend/indicators/bars.py:29` |
| `ohlc_bars` | `backend/integrations/uw_api.py:537` |
| `ohlc_quote` | `backend/integrations/uw_api.py:354` |
| `ohlc_sector` | `backend/jobs/sector_constituent_refresh.py:190` |
| `triton_flow_shadow` | `backend/jobs/triton_shadow_common.py:56` — **the grader** |
| `chart_indicators` | `backend/services/read_only/chart_indicators.py:117` |

**Path B — `get_bars`: HAS the yfinance fallback.** `qqq_sma_watch.py:176` (the R-IV.193
instrument), `correlation_monitor`, `trip_wire_monitor`, `market_data`,
`sectors`, `composite`, `universe_cache`, `a3_fwd_return_resolver`,
`wrr_buy_model`.

**The 40 measured fallbacks are Path B traffic only.** *"Every daily-bar fetch falls
through to yfinance"* was too broad: **Path A fetches do not fall through, they fail.**

**The R-IV.193 SMA watch is on Path B**, so the original conclusion about it still holds —
correct today because the fallback holds, not because the primary does. **That was traced
and remains traced.**

**The grader is on Path A**, which is CC-QUERY's proof (a): it cannot grade without live UW
bars, so **every row it wrote dates UW liveness.**

**The R-IV.193 QQQ 200-SMA watch is on this path**, traced rather than assumed:
`_fetch_closes` → `uw_api.get_bars` (`:623`) → the fallback log at `:663`. **It is correct
today because the fallback holds, not because the primary does.** If yfinance follows UW,
the watch goes `ERROR` rather than wrong — which is the right failure, but it is one
dependency deep and nobody is counting it.

## An open question this lane cannot answer from here

**Does a failed `/ohlc/1d` call still meter against the UW quota?** If it does, the hub is
**paying for zero bars**, ~40 requests per cycle, and the budget watchdog's
`NEXT_TIER_SHED_CANDIDATES = ["ohlc_bars", "technical_indicator", "ohlc_sector"]`
(`uw_budget_watchdog.py:47`) is a shed list whose first and third entries may already be
returning nothing. **Stated as a question. Metering is a property of UW's side and is not
observable from this codebase.**

**ANSWERED as a METHOD by R-IV.279(d), below** — not from code, from the wire. The question stands; what changed is that it is now measurable, and the measurement is scheduled into the AEGIS sizing pass.

## THE INVERSION — provenance exists where it was least needed

`get_bars` **already tags its provider.** `_tag_provider(bars, PROVIDER_UW)`, a `provider` field valued
`"uw"` or `"yfinance"`, *"per DEF-BARS-NO-PROVENANCE"* (`uw_api.py:638`), with
cached series carrying the provider they were fetched under.

**So the provenance work was done on the path that HAS a real choice of provider, and was
not done on the path that has none — which is the path that asserts one anyway.**

**That inverts the phantom's reconciliation.** `DEF-BARS-NO-PROVENANCE` was stubbed as *"closed in code at
`773e7a8`, artifact never filed."* **It is closed for Path B and open for Path A**, and the
Path A half is the P1 — because a hardcoded literal on a path with no alternative can
never be right by accident, only by coincidence of the original author being correct on
the day.

## ONSET — bounded by CC-QUERY, and it is NOT the grader's cause

```
grader writes date UW liveness (Path A, no fallback):
  08-17  962 rows | 08-26  9 | 08-27  1,862 | 09-02  573   -> UW ALIVE
  09-05  measured DEAD (this lane, twice, incl. a fresh boot)

ONSET: after 2026-09-02 20:41:55Z, at or before 2026-09-05.
```

**UW served on 08-17, 08-27 and 09-02 — all AFTER the grader died on 07-31.** So **one
mechanism does not explain both**, and this defect is a separate, later failure.
**Merging them would leave the grader's loop defect unfixed behind a repaired vendor
path** — a fix that makes the symptom disappear while the cause remains.

**Burn data cannot date it, and that is this defect's own shape.** `ohlc_bars` held
1,689–2,018 calls/day through 09-04. **Calls keep being made and consumers keep getting
bars, so a silent fallback leaves no volume signature.** The only instrument that dated the
onset was **a consumer with no fallback** — which is the argument for Path A's
existence, not against it.

## The yfinance tension, recorded on this face per the ruling

**Declared fallback. De-facto primary. On two surfaces, in two different ways:**

- `backend/jobs/stable_jobs.py`'s module docstring opens **"yfinance-only (zero UW calls)"**
  — yfinance as *declared primary*. (That same sentence is wrong a second way: the module
  hosts the tide warmer, which is a UW call every five RTH minutes.)
- **Path B** is nominally UW-primary with yfinance fallback, and **100% of measured Path B
  fetches are served by the fallback** — yfinance as *de-facto primary*. **Scoped to Path
  B**: Path A has no fallback and simply fails, which is why it could date the onset.

**A dependency that is load-bearing everywhere and documented as a fallback is a single
point of failure nobody is counting.** It is why a yfinance outage was a plausible
hypothesis for two unrelated alarms on 2026-09-05, and why that hypothesis had to be
falsified by measurement rather than dismissed.

**yfinance is itself partly degraded:** it fails on `^ADVN`, `^DECLN`, `^ADV`, `^DEC`
(HTTP 404, "Quote not found"), with **zero** rate-limit signatures and all 15 equity
tickers succeeding. The breadth symbols are gone; the equities are not.

## Fixes in scope (R-IV.275(d))

1. **`indicators_source` reports the ACTUAL server.** The value is derived from which path
   answered, never a literal. **If it cannot be derived, it says `unknown` — not
   `uw_computed`.**
2. **Fallback rate counted and alarmed.** `>X%` fallback = `degraded`. The threshold is a
   decision, not an implementation detail: state it, and state the expected satisfaction
   rate per §1.1 so the alarm is known to be reachable. **Today's rate is 100%, so any
   threshold below 100 fires immediately — which is the correct first observation.**
3. **Read-only investigation of why `/ohlc/1d` fails** — quota, deprecation, or auth. No
   writes. The three are distinguishable by response code and by whether other UW endpoints
   still answer (they do: `/info`, earnings and flow all returned on the same boot, so a
   blanket auth failure is already ruled out).

## SCOPE CONFIRMED — R-IV.279(d)

1. **`indicators_source` is derived from which server actually answered, PER CALL.** Not per module,
   not per boot, not a default with an override — the value is produced by the code path
   that returned the bars. **A per-boot value would be right until the first fallback and
   silently wrong after it**, which is the defect restated one level up.
2. **Fallback events are counted and alarmed.** Today's rate is 100%, so the first
   measurement is the alarm.

### The metering question, answered EMPIRICALLY — and the wire is currently discarded

Spine's method: **read UW's rate-limit headers before and after one cycle** during the
AEGIS sizing pass. *Unobservable from code, observable from the wire.*

**One thing the build must know first: this client does not read those headers.**
`_uw_request` (`backend/integrations/uw_api.py:147`) carries a 120 req/min **token bucket** and handles a **429** by returning the
`UWUnavailable(RATE_LIMITED)` sentinel — but **no response header is captured anywhere in the module.** Grep for
`x-ratelimit` returns nothing.

**So "observable from the wire" is exactly right, and it is not observable from this client
as written.** The measurement needs either a temporary header capture in `_uw_request` (`backend/integrations/uw_api.py:147`), or an
out-of-band request that bypasses the client entirely. **The second is preferable for a
one-off**: it changes no production code path to answer a question about production, and
it cannot itself perturb the counter it is measuring.

**Why the answer matters beyond tidiness.** If a dead `/ohlc/1d` still meters, the hub is
spending quota at roughly 40 requests per cycle for zero bars, and the budget watchdog's
`NEXT_TIER_SHED_CANDIDATES` list is queued to shed callers that are already returning nothing — shedding
would then reduce the metered spend while changing no data at all, which is the one case
where a shed is pure profit and nobody has noticed it is available.

## Reconciliation — one stub, two names

**This is the live instance of `DEF-BARS-NO-PROVENANCE`**, the phantom stubbed at
R-IV.263(c) from citing context only. That stub recorded a name with no measurement behind
it; this file is the measurement. **The stub is not superseded — it is resolved into this
one**, and it now carries a pointer here so a reader arriving by either name lands on the
evidence.
