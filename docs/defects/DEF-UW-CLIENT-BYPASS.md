# DEF-UW-CLIENT-BYPASS · P1

**Registered 2026-09-11 by R-IV.369(c).** **Status: OPEN.**
**Every UW call goes through `_uw_request` or it does not go.**

---

## THE RULE

`_uw_request` is the single chokepoint: token bucket, per-caller counter, governor
precheck, circuit breaker, 429 → typed sentinel. **A call that does not pass through it
is uncounted, untagged, ungoverned, and invisible to every instrument built on top.**

**The governor cannot block a call that never reaches the chokepoint.** That is not a
tuning problem; it is outside the mechanism entirely.

## THE INSTANCE THAT MATTERS — a second UW client on another host

**`gen_vps_writer.py` deploys a complete, independent UW client tree to the VPS:**

```
/opt/openclaw/workspace/scripts/uw_forward_logger/
    config.py            own throttle, own key read from /etc/openclaw/openclaw.env
    fetchers/base.py     "Shared base: auth header, retry logic, 429 backoff"
    fetchers/darkpool.py         /api/darkpool/{ticker}
    fetchers/flow_alerts.py      /api/stock/{ticker}/flow-alerts
    fetchers/greek_exposure.py   /api/stock/{ticker}/greek-exposure
    fetchers/net_prem_ticks.py   /api/stock/{ticker}/net-prem-ticks
    fetchers/spot_exposures.py   /api/stock/{ticker}/spot-exposures
```

**Its own auth, its own retry, its own 429 backoff, the SAME API KEY, a different
host.** Five endpoints per ticker, over a YAML watchlist.

### Its pacing is the whole quota

```
config.py   THROTTLE_SLEEP_BETWEEN_CALLS_S = 1.0
            THROTTLE_MAX_BURST             = 10
            THROTTLE_BURST_PAUSE_S         = 15.0

  -> 10 calls per 25 s cycle  =  1,440 calls/hour  =  34,560/day continuous
  -> 86% of the entire 40,000/day account limit, from one collector
```

**Measured unattributed spend on 2026-09-11 was 23,417 — 16.3 hours at exactly that
pacing.** Consistent, and consistent is not proven: **the VPS is unreachable from this
workstation (ports 22/443/80 all time out), so this is an identification from the
deploy script, not an observation of a running process.**

### AND IT POLLS THE ENDPOINT THAT FAILED

**`fetchers/greek_exposure.py` calls `/api/stock/{ticker}/greek-exposure`** — the exact
endpoint whose emptiness produced the gex outage and the proposed `DEF-UW-GEX-DEAD`.

**The hub's own `greek_exposure` caller spent 49 requests today, 0.3%.** The composite
lost its GEX factor because **a sibling collector on another host exhausted the shared
account on the same endpoint.** Self-inflicted, across a host boundary nobody was
looking across.

## FULL INSTANCE LIST

**Search scope: entire worktree, `*.py` / `*.js` / `*.sh` / `*.json`.**

**Own base URL AND own key — genuine independent clients (12):**

`gen_vps_writer.py` · `scripts/flow_scanner.py` · `scripts/flow_scanner_v1_backup.py` ·
`scripts/vps_deploy/patch_premarket_uw.py` · `scripts/earnings_gap_backtest.py` ·
`scripts/gap_convexity_options_validation.py` · `scripts/pead_backtest.py` ·
`scripts/phase0_events_verify.py` · `scripts/phase0_options_probe.py` ·
`scripts/phase0_probe.py` · `scripts/sprint0_uw_validation.py` ·
`scripts/stage2_options_backtest.py`

**Triage, because they are not equally dangerous:**

| kind | files | risk |
|---|---|---|
| **deployed daemons** | `gen_vps_writer.py` (the forward logger), `scripts/flow_scanner.py` (`while True`, 1 s) | **the quota** |
| **VPS patches** | `patch_premarket_uw.py` — adds direct UW pulls to `premarket_briefing.py` | recurring, unmeasured |
| **one-off analysis** | the backtests and probes | low, but each is a live key outside the chokepoint |

### NOT AN INSTANCE — checked and cleared

**`backend/api/unified_positions.py`** imports `UW_API_KEY` **only to test presence**
(`if not UW_API_KEY: return _greeks_unknown("no_api_key")`) and then calls
`get_ticker_greeks_summary` / `get_spread_value`, which DO route through `_uw_request`.

**It was the most alarming hit in the grep — the only one inside the deployed app — and
it is a false positive.** Recorded because a defect list that includes a cleared file
teaches the next reader to distrust the whole list. **Third grep this week whose scariest
hit did not survive a read.**

## FIX SHAPE — not chosen here

**A shared client, or a shared budget.** The VPS cannot import `backend.integrations`,
so the chokepoint cannot simply be reused — which is presumably why this happened. The
options are a hub-side proxy endpoint the VPS calls, or a **shared Redis counter both
clients decrement**, so the governor governs the account rather than one process.

**Whatever is chosen, the invariant is the same: the account has one budget, so it needs
one accountant.**
