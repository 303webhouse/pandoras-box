# DEF-UW-CLIENT-BYPASS · P1

**Registered 2026-09-11 by R-IV.369(c).** **Status: OPEN.**
**Every UW call goes through `_uw_request` or it does not go.**

---

## RETRACTED — THE HOST NEVER RAN (R-IV.438(a)(b), 2026-09-17)

**The principal confirms the Hetzner box has been unpaid and inactive for months.
`uw_forward_logger` and `flow_scanner` were NEVER RUNNING.** Everything below that attributes
spend to them is **WITHDRAWN**, and is kept rather than deleted so the reasoning stays legible:

- **"a second UW client on another host" is HYPOTHETICAL, not live.** The deploy tree exists in
  this repo; the processes never did.
- **The 86%-of-account pacing arithmetic is void.** It describes what the script WOULD have
  spent, not what anything spent.
- **The GEX paragraph is void** as an explanation of the outage: no sibling collector was
  polling that endpoint.
- **The rule at the top STANDS.** "Every UW call goes through `_uw_request` or it does not go"
  is a property of the mechanism, not a claim about a host, and an ungoverned call remains
  invisible wherever it is made.

**The DEF's own caveat was correct and was not enough.** It said the identification came "from
the deploy script, not an observation of a running process" — and the number was still carried
forward into rulings as though the process existed. A caveat beside a figure does not stop the
figure travelling.

### What replaces it — one hypothesis, and it is now measured

**The leaked vendor key (security register S12): the credential was in a tracked file of a
PUBLIC repo.** With the box gone there is no other host that could hold either key.

**Measured 2026-09-17 after the principal rotated (values never handled, status codes only):**

| key | fingerprint | HTTP |
|---|---|---|
| the old key, still in the desktop MCP config | `67a10879` | **401** — revoked, the rotation is effective |
| the new key, in Railway | `3f5e0660` | **429** — authenticates; the account was already near its cap from today's pre-rotation traffic |

**A 429 on the new key is not a second consumer; it is today's spend, counted against the
account before the rotation.** Tomorrow's meter is the decisive read (R-IV.437(c),
R-IV.438(c)): a gap that survives a key change is a consumer holding the NEW key; a gap that
vanishes was the leaked one.

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

---

## ~~CONFIRMED BY OUTCOME — 2026-09-13 05:02 ET~~ — WITHDRAWN, SEE BELOW

**The convergence check named in the transfer plan has run, and it converged exactly.**

```
                   account   hub      other
2026-09-11 (Fri)    40,000   16,583   23,417   59%   <- limit hit 09:46 ET
2026-09-13 (Sun)       586      585        0    0%   <- 9 h into the quota day
```

**586 = 585 + the one probe call that read the header.** There is nothing else on the key.

**This was the verification, not a re-statement of the identification.** The claim was made
from a deploy script — `gen_vps_writer.py`, its pacing arithmetic, and a 23,417-request
gap. **It could have been wrong in two ways: the logger might not have been running, or it
might not have been the whole gap.** Both are now excluded: the gap closed to zero when the
logger stopped, so it was running and it was all of it.

**AND THERE IS NO THIRD CONSUMER.** Friday's overnight read showed 1,031 "other" requests
in five hours and I flagged it as needing explanation before Monday. **It is explained: the
logger was still running then.** The stop came later.

### What this unlocks — and the figure that is NOT yet measured

**Hub-only demand can now be measured against the 40,000 cap for the first time.** But not
from the numbers above:

| day | hub | why it is not the answer |
|---|---|---|
| Sun 09-13 | 585 (9 h) | market closed; near-idle |
| Sat 09-12 | 2,725 | market closed |
| **Fri 09-11** | **16,583** | **TRUNCATED — the account 429'd from 09:46 ET, so callers spent the session failing, backing off, or serving cache** |

**Friday's 16,583 counts ATTEMPTS, not satisfied demand, and a session spent throttled is
not a session's worth of work.** It is neither a floor nor a ceiling: retries inflate it,
give-ups deflate it, and which dominates is unmeasured.

**MONDAY 2026-09-14 IS THE FIRST CLEAN FULL-SESSION MEASUREMENT**, and it is the number the
plan decision needs. **Nothing before it should be quoted as hub demand.**

### The recommendation firms up

**Still: no plan purchase.** One collector was 59% of a 40,000-request account. With it
stopped, a full trading session has to exceed ~40,000 on its own before more quota is the
answer — **and Friday's throttled 16,583 is the only hub figure in existence, which makes
"we need more quota" an assertion nobody can currently support.**

**The governor should still move to enforce.** Not because the pressure remains — it does
not — but because **nothing prevents the next uncounted client.** The bypass is the defect;
the quota exhaustion was its symptom.

---

## WITHDRAWN 2026-09-14 — THE CONFIRMATION WAS TAKEN ON A SUNDAY

**The Sunday convergence read cannot distinguish "stopped" from "idle because it is the
weekend", and I filed it as a confirmation. That was wrong.**

```
                        account     hub     other
2026-09-11 Fri           40,000   16,583   23,417   59%
2026-09-13 Sun (9 h)        586      585        0    0%   <- read as CONFIRMATION
2026-09-14 Mon (17.9 h)  17,859   11,718    6,140   34%   <- the consumer is BACK
```

**A weekday-only consumer reads zero on a Sunday.** So does a stopped one. **The
measurement I called a verification could not separate the two hypotheses it was meant to
decide between** — which is this register's own null-verifier law, committed by the lane
that has been filing instances of it all week.

**And I had the discriminator in hand and did not apply it.** Four hours before that read I
filed the nightly's weekend false-red discrimination — *a gap spanning a weekend proves
nothing about a weekday-gated process* — and then took a weekend reading as proof about a
process whose schedule I had never established.

### What is actually true now

| | Friday | Monday |
|---|---|---|
| other-consumer rate | **1,697/h** (to exhaustion at 09:46 ET) | **344/h** |
| as % of the logger's full pacing (1,440/h) | 118% | **24%** |

**The second consumer is still running, at about a fifth of Friday's rate.**

**Three readings fit and this file chooses none of them:** the logger was partially
stopped; the logger is stopped and a *different* VPS process (`premarket_briefing`,
`flow_scanner`) is the residual; or the logger is throttling itself differently. **The VPS
is still unreachable from this workstation, so the distinguishing read remains the one
that has been blocked since Friday.**

### Today is not an exhaustion day, which is why this is P1 and not P0

```
projected at the 20:00 ET reset, at current rates
  account   23,985 / 40,000        hub   15,738        other   8,246
```

**No exhaustion expected, and 0 rate-limited responses in the sampled window.** The
pressure is off; **the defect is not.** A consumer nobody can see is a consumer nobody can
size, and the plan decision still has no trustworthy denominator.

### The rule this costs

> **A CONVERGENCE CHECK MUST RUN WHEN BOTH SIDES ARE ACTIVE.**
> Two counters agreeing while one of them has nothing to count is not agreement. **Before
> reading a gap as closed, establish that the process which produced it was scheduled to
> run during the window.**

**Kin to conventions #15 and to `DEF-NIGHTLY-FLATLINE`'s weekend artifact — the same
mistake in three subsystems this week, twice caught and once committed.**
