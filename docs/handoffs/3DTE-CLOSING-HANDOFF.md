# 3DTE — CLOSING HANDOFF

**Lane:** 3DTE (fka STRIKE) · 1–3 DTE setup design & evaluation
**Chartered:** 2026-08-05 (verbal) / 2026-08-17 (filed, `docs/strike/2026-08-17-strike-lane-charter.md`)
**Closed:** 2026-09-03 · **Authority:** R-IV.230 (consolidation; lane function moves to spine)
**Author:** 3DTE · **Ledger with spine at close:** ZERO
**Governing artifacts:** `docs/strike/` (charter, SPEC-01..04, queries, results) · `docs/defects/` · `docs/codex-briefs/`

---

## §0 — HOW TO READ THIS

Every claim below is either (a) addressed to an artifact or relay, or (b) explicitly
marked as not-attestable. Nothing is asserted from recall. §3 is a GAP DECLARATION,
not a section with content — read it before assuming this handoff is complete.

---

## §1 — PYTHIA v2.5 DEPLOYMENT (complete; principal-side; highest-value open item)

### 1.1 Root cause — proven, not inferred

**Evidence:** TradingView runtime error, principal-supplied screenshot 2026-09-02,
observed on an NBIS 15m chart:

```
Runtime error: RE10045
In `array.get()` function. Index 50 is out of bounds, array size is 50.
at #main():153
```

**Source:** PYTHIA Market Profile v2.4 Pine script, principal-supplied 2026-09-02,
volume-distribution block. The two clamps are mirrored — each index is clamped at
one end only:

```pine
loBinIdx = math.max(0, math.floor((low - sessionLow) / binSize))            // floor 0, NO ceiling
hiBinIdx = math.min(numBins - 1, math.floor((high - sessionLow) / binSize)) // ceiling 49, NO floor
```

**Failure path:** `binSize = range_ / numBins` (50). When a bar's `low` equals
`sessionHigh` — a zero-range bar setting a new session high, or float rounding at
the top edge — `floor((low - sessionLow) / binSize)` evaluates to exactly **50**.
`hiBinIdx` clamps to 49; `loBinIdx` does not clamp and stays 50.
`array.get(volBins, 50)` on a 50-element array → RE10045, alert HALTS.

**Secondary defect, same block, silent:** with `loBinIdx=50 > hiBinIdx=49`, Pine
**counts down** when `from > to`, so `for i = 50 to 49` executes at 50 and then 49
rather than not running (confirmed by the error firing at index 50). Additionally
`binsHit = 49 - 50 + 1 = 0`, so `volPerBin` falls through to the full bar volume and
dumps it into a single bin — **profile corruption with no error**, on any bar that
reaches this state without crashing first.

### 1.2 Why this explains the observed collapse

- **Not symbol-specific — bar-specific.** Every ticker crashes once its history
  contains one qualifying bar. This supersedes the earlier SPY-scoped naming.
- **Runs-then-dies-on-restart.** The error fired on **historical bar 4573**.
  TradingView replays history on alert recalculation; the alert dies when the replay
  reaches the bad bar, not from live data. Restarting buys days, then recurs.
- **A clean chart does not imply a clean alert** — chart and server-side alert
  calculate over different bar windows. Principal observed exactly this (QQQ chart
  clean while the QQQ alert was halted).
- **Predicts the death-wave shape.** Per CC-QUERY's addressed census
  (`C:\temp\cc-query-handoff\PYTHIA-COLLAPSE-VERIFICATION.md`,
  sha256 `468044f2…`): 212 distinct tickers, 206 dead, 167 deaths (81%) in
  07-27→08-05, peaking 39/day on 07-27 and 07-28. A platform-side recalculation
  sweep kills en masse. **TESTABLE PREDICTION, unverified:** the wave corresponds to
  a TradingView recalc event, not to market data.

### 1.3 The patch — PYTHIA v2.5

Replace the body of the `if range_ > 0` block inside `// === VOLUME DISTRIBUTION
INTO BINS ===` with:

```pine
    if range_ > 0
        binSize := range_ / numBins
        // v2.5 FIX (RE10045): clamp BOTH indices at BOTH ends.
        // v2.4 clamped loBinIdx only at 0 and hiBinIdx only at numBins-1.
        // A bar whose low sits at the session high (zero-range bar making a
        // new high, or float rounding at the top edge) yields
        // floor((low - sessionLow)/binSize) == numBins -> array.get(50) on a
        // 50-element array. Pine also counts DOWN when from > to, so the loop
        // ran i=50 then i=49 instead of not running at all, and binsHit==0
        // pushed the whole bar's volume into one bin.
        rawLo = math.floor((low  - sessionLow) / binSize)
        rawHi = math.floor((high - sessionLow) / binSize)
        loBinIdx = math.max(0, math.min(numBins - 1, rawLo))
        hiBinIdx = math.max(0, math.min(numBins - 1, rawHi))
        if hiBinIdx >= loBinIdx
            binsHit = hiBinIdx - loBinIdx + 1
            effectiveVol = volume > 0 ? volume : 1.0
            volPerBin = effectiveVol / binsHit
            for i = loBinIdx to hiBinIdx
                curVol = array.get(volBins, i)
                array.set(volBins, i, curVol + volPerBin)
            cumSessionVol += effectiveVol
```

Also change the indicator title so alert provenance is traceable:
`indicator("Pythia Market Profile v2.5", ...)`.

### 1.4 Deployment steps (principal-side; Pine Editor)

1. Pine Editor → open PYTHIA v2.4 → **Save As** a copy first (rollback path).
2. Paste the §1.3 block over the existing `if range_ > 0` body — everything from
   `binSize :=` down to `cumSessionVol += effectiveVol`. **Indentation is
   load-bearing in Pine.** Verify `cumSessionVol += effectiveVol` sits INSIDE the
   new `if hiBinIdx >= loBinIdx`.
3. Save. The chart recompiles.
4. **Verify on an NBIS 15m chart** — this is the known repro (bar 4573). A clean
   NBIS is the proof. A clean SPY/QQQ chart is NOT proof (§1.2).
5. **Recreate alerts on v2.5** — do not restart v2.4 alerts. Existing alerts stay
   bound to the v2.4 script and will keep dying. One dedicated alert per symbol,
   **never bound to a watchlist** (R-IV.109(e): prey-list coverage is an arbitrary
   computed slice and is disqualified as an upstream).
6. Watch one full session before adding further tickers.

### 1.5 Rollback

Revert to the saved v2.4 copy and recreate alerts against it. Rollback restores the
crash; it is a compile-failure escape hatch only.

### 1.6 Scope of what this fixes

Not four alerts. Per CC-QUERY's census, 206 of 212 tickers are dead and the active
universe fell 203 → 82 → 25 → 12 → 12 → 9 across weeks 07-27 → 08-31. This patch is
the cure for that collapse. It also restores `hub_get_market_profile`, which is
PYTHIA-fed (§5.2) and sits in the standing Olympus pre-review sequence.

---

## §2 — ATLAS REVIEW REQUEST (HELD) — full content + release conditions

### 2.1 Status

**HELD, unsent.** Spec is filed and unchanged at
`docs/strike/specs/STRIKE-SPEC-01-ib-break-feed-conversion.md` (blob `5f5a19e7`).
**The 09-08 ship date (R-IV.115(e)) is not reachable** — a revised date was requested
of spine and had not been issued at close.

### 2.2 Two release conditions (both must hold before sending)

1. **v2.5 deployed and surviving one full session** on the dedicated tickers.
   Rationale: the converter is buildable, but its upstream is not currently reliable
   on any ticker.
2. **Rates re-derived on a stable universe.** Every rate figure in §2.3 was measured
   08-24/25/26, when the active universe was 12 tickers (from 203). 3DTE read ticker
   death as market conditions — ledger entry L10, §5.1. **Do not send §2.3's numbers
   to Titans without re-derivation**; they are addressed here so the error is visible,
   not so it is reused.

### 2.3 The request, as authored (numbers pending re-derivation per 2.2)

```
TITANS REVIEW REQUEST — STRIKE-SPEC-01 (IB-Break Feed Conversion)
Lane: 3DTE · Authority: R-IV.109 (scope ruling) + R-IV.115(e) (dates)
Spec: docs/strike/specs/STRIKE-SPEC-01-ib-break-feed-conversion.md

Run ATLAS lead + AEGIS touch. MOCKUP GATE n/a (no UI). Pass 1 solo →
Pass 2 integrated → ATHENA overview → Nick approval.

WHAT IT BUILDS: a converter turning PYTHIA IB-break webhook events into
SHADOW signal rows in the existing pipeline. Long on ib_break_up, short
on ib_break_down; entry = price_at_event; stop = IB midpoint (opposite
extreme recorded as a metadata variant); t1/t2 = ±0.5 / ±1.0 × IB
height. Emits the existing signals schema, non-live status, source
'STRIKE_IB_BREAK'. Dedup: first per ticker per direction per session.

ALREADY ANSWERED (spec's open questions 1–2 are closed):
· Event store = pythia_events (NOT webhook_events). Carries `timestamp`
  and `alert_type`, not created_at/event_type.
· Path proven healthy end-to-end at census time: 341/342 webhook
  deliveries; every trading day populated 08-20→08-26.
· Ticker scope RULED (R-IV.109(a)): QQQ (primary validation) · IWM ·
  SMH, SPY excluded. **SUPERSEDED BY EVENTS — see 2.4.**
· DEDICATED-ALERT REQUIREMENT (R-IV.109(e)): the converter may only
  depend on tickers holding a dedicated per-symbol TradingView alert.

BINDING DESIGN CONDITION (R-IV.109(c)): per-ticker expected-event
watermarks ship WITH the converter, day one. Extended by R-IV.127(d):
watermarks distinguish INTERMITTENT sources (band + outage cadence)
from CONTINUOUS (silence = alarm). Gate form adopted verbatim from
CC-QUERY: resolve max(timestamp) WHERE ticker = $1 AT CALL TIME;
refuse or loudly label any read whose last event precedes the session
under analysis; NEVER a hardcoded survivor list — that is tripwire
decay at feed scale. Measured spread proving a fixed threshold fails:
AMZN 0h57m → AMD 4h26m, all genuinely alive.
Cautionary precedent, in-house: OBS-01's own sentinel was named in its
header and never implemented; liveness silently rested on row-presence
for all 8 observation days (R-IV.127(a)).

MEASURED RATE — DO NOT USE UNTIL RE-DERIVED (see 2.2 condition 2):
raw IB events collapse ~3.5:1 under dedup; at ruled scope ~1 qualifying
signal/day; n≥50 gate ≈ 10 weeks; each additional dedicated-alert
ticker adds ~0.5–1/day.

QUESTIONS FOR THE PASS:
1. ATLAS — pythia_events read pattern: poll, trigger, or job? What
   guarantees exactly-once conversion under webhook replay (idempotency
   key candidate: ticker + session date + alert_type)?
2. ATLAS — signals table: correct non-live status value for shadow
   emission, and does any live consumer read that status today?
3. ATLAS — watermark implementation: sidecar table vs existing health
   surface? Must survive process restart (per-process counters were
   proven to reset on deploy).
4. AEGIS — pythia_events payload trust: the converter derives entry,
   stop, and targets from webhook-supplied numbers. What validation
   before those become signal rows (range sanity, IB height > 0, ticker
   allowlist)?
5. ATHENA — sequencing: ship at low signal rate, or gate on the
   principal adding dedicated alerts for ~8 tickers? Index and sector
   ETFs share the structural-IB premise; single names would need
   re-derivation.
6. ATLAS — promotion-gate liveness: SPEC-01's n≥50 gate must count
   GRADED rows with grading currency verified, never emitted rows.
   Precedent: DEF-TRITON-GRADER-DARK — grader dark since 08-17 while
   its poller stayed healthy; 843 rows accumulated ungraded and nothing
   alarmed. What surfaces grading currency for STRIKE_IB_BREAK shadow
   rows, and does the gate check it?

SCOPE FENCE: no new Pine, no webhook endpoint changes, no UI, no live
scoring, no auto-trading, no changes to PYTHIA ingestion. Defects found
are ticketed, not fixed in-scope.
```

### 2.4 Scope superseded by the collapse

R-IV.109(a) ruled QQQ (primary) · IWM · SMH, SPY excluded. As of 2026-09-03:

| Ticker | State | Address |
|---|---|---|
| QQQ | DEAD 09-01T14:30:52Z | CC-QUERY census; 3DTE hub read 09-02 matched to the second |
| SMH | DEAD 09-01T15:30:55Z | same |
| IWM | ALIVE | CC-QUERY survivor six |
| SPY | ALIVE (resumed) | 3DTE hub read 09-03 ~19:3xZ — session_date 09-03, ib_break_up @770.20, age 4.5h |

**Ruled scope is 1 of 3 alive; SPY is available but unruled.** Spine must re-rule
scope post-v2.5 rather than inherit R-IV.109(a) as written.

### 2.5 Held, not sent: four ticker adds

DIA · XLK · XLF · XLE, one dedicated alert each, recommended on the premise that
index and sector ETFs sustain continuous two-sided auctions with meaningful initial
balances; liquid single names frequently do not (gap-and-go opens digest overnight
news rather than forming balance), and mixing them blends two mechanisms in one
shadow population. **HELD** — adding symbols to a crashing script produces more
silent halts. Release with §2.2 condition 1.

---

## §3 — GAP DECLARATION: DEF-SIGNAL-STATUS-DISCARDED / R-IV.178(a)

**3DTE cannot produce this section.** Stated in CC-QUERY's phrasing law — this is
what a lane can attest, not a claim about the record:

> **No relay numbered R-IV.178 is present in this lane's inputs, and this lane holds
> no artifact naming DEF-SIGNAL-STATUS-DISCARDED.** The relay sequence received by
> 3DTE runs R-IV.1 · 7 · 9 · 17 · 23 · 29 · 31 · 36 · 42 · 53 · 54 · 57 · 59 · 60 ·
> 61 · 63 · 66 · 69 · 72 · 75 · 76 · 79 · 80 · 81 · 82 · 94 · 95 · 97 · 98 · 99 ·
> 109 · 115 · 127 · 130 · 229 · 230. R-IV.178 is not among them.

Reconstructing a widening investigation from inference would be exactly the failure
class this board spent three weeks naming (STATUS FROM RECALL; recall-may-propose /
only-the-artifact-may-assert). **This lane declines to author it.**

**ADJACENT MATERIAL 3DTE DOES HOLD, addressed — offered as input if spine re-issues
the item:**

1. **Status churn observed under suppression.** OBS-01 day-2 read (CC-QUERY,
   2026-08-25 23:19Z): 08-24 rows read ACTIVE/NULL on day 1 and
   EXPIRED/DISMISSED on day 2 (e.g. AAPL 14:33:23). Creation counts immutable;
   status mutates overnight. **Auto-dismiss-after-24h is a candidate, not an
   attribution.** Consequence ruled: any status-derived reading is
   vintage-dependent — state the read time or don't cite it.
2. **Status is invisible to the OBS tripwire by design** — counts are creation-side
   and version-invariant; status mutation sits outside the instrument's measurement.
   Filed in the OBS-01 terminal packet debt section.
3. **Feed surfacing depends on status.** STRIKE-Q2 CR-3 (`trade_ideas.py:50-61`):
   surfacing requires `status='ACTIVE'` AND not expired AND <24h old AND
   `user_action IS NULL` AND category not in (INTRADAY_SETUP, FOOTPRINT) AND
   matching feed_tier AND no `would_suppress` tag.
4. **Only three statuses appeared across three weeks of census** (STRIKE-Q1,
   `docs/strike/queries/results/2026-08-17-STRIKE-Q1-RESULTS.md`, commit `518b381`):
   no `filled`, no `executed` — the feed and the trading record have never been
   connected.
5. **Committee bridge is a status dead-end.** STRIKE-Q2 Q2.5: 171 signals
   `committee_requested_at` set, ZERO `committee_completed_at`, every day of the
   window. Filed as DEF-COMMITTEE-BRIDGE-DEAD (P1),
   `docs/defects/DEF-COMMITTEE-BRIDGE-DEAD.md`.

If R-IV.178(a) concerns status values being discarded at any pipeline stage, items
3–5 are the addressed material this lane can contribute. **Spine should re-issue the
item to whichever lane inherits it.**

---

## §4 — OPEN EXPECTATIONS AT CLOSE

| # | Item | Owner | State / address |
|---|---|---|---|
| 1 | **Deploy PYTHIA v2.5** | Principal | §1. Highest-value open item; gates 206 tickers, Olympus MP inputs, and SPEC-01 |
| 2 | Re-rule SPEC-01 ticker scope post-fix | Spine | §2.4 — R-IV.109(a) superseded by events |
| 3 | Re-derive SPEC-01 rates on a stable universe | Inheriting lane | §2.2 cond. 2 |
| 4 | Send ATLAS request | Inheriting lane | §2.3, after conditions 1+2 |
| 5 | Revised SPEC-01 ship date | Spine | 09-08 unreachable; requested, not issued at close |
| 6 | Four ticker adds (DIA/XLK/XLF/XLE) | Principal | §2.5, held |
| 7 | **Rotate webhook secrets** | Principal / AEGIS | DEF-PYTHIA-WEBHOOK-SECRET-EXPOSED: secret hardcoded in Pine payload; a second secret in cleartext in the TradingView alert-log CSV. Both transmitted in chat; one persists as an uploaded file. Rotate both (Pine + hub config); adopt a redaction convention for future Pine/log sharing |
| 8 | R-IV.178(a) re-issue | Spine | §3 |
| 9 | OBS-01 terminal packet | Filed 09-01 | Series 36·63·66·58·53·41·59·50·52; EMITTER-CHARACTERIZATION ONLY; OBS-01 RETIRED |
| 10 | SPEC-02/03/04 | Filed, unscheduled | `docs/strike/specs/` — Strong Close Continuation · Compression Flag · PDH/PDL Engine |
| 11 | Roth QQQM tranches | Principal | R-IV.115(c): T1 712 / T2 697 / T3 681 QQQ-equiv, GTC after Warsh 08-28 (gate passed), backstops 09-08 · 09-25 · 10-09. Manual placement; flagged as a date, not advice |
| 12 | URSA duration dissent | Spine (Battlefield Brief) | R-IV.115(g): 9 of 21 RH legs expire before the Oct/Nov catalyst cluster. Flagged LIVE |

---

## §5 — LEDGER ENTRIES WITH ADDRESSES

### 5.1 3DTE falsified / withdrawn findings

Board-wide ledger: `docs/conventions/falsified-findings-ledger.md` (ruled R-IV.130).
Entries L4 and L5 are already filed instrument-scoped in the OBS-01 terminal packet.

| ID | Finding | Class | Address (asserted → corrected) |
|---|---|---|---|
| L1 | "8–12 qualifying signals/day" for SPEC-01 | Unscoped extrapolation (raw, undeduped, unscoped) | 3DTE relay preceding R-IV.109 → corrected in 3DTE's pre-ATLAS rate relay (measured 5·5·5 fleet, 1/day at scope) |
| L2 | RH at-risk > balance is "structurally impossible" | Mechanism-from-symptom | 3DTE relay in R-IV.80 traffic → refuted R-IV.98(a) by CC-POSITIONS (balance is not position-aware; 21 rows, 0 credit structures) |
| L3 | PYTHIA outage caused by watchlist rotation / compute-cap eviction | Mechanism-from-symptom | 3DTE relay preceding R-IV.109 → refuted by the alert panel (two alerts hard-STOPPED on Pine calculation errors) |
| L4 | HG_1H "monotonic decline, not noise" (66→58→53→41) | Inference from absence / pattern-in-short-series | 3DTE day-4 findings relay → falsified at d5 (41→59; max_score 83 = window high). Filed in OBS-01 packet |
| L5 | "crypto arm dark since ~08-23" | Status from recall | OBS-01 v2.1 registered header, sha256 `714b1bfe192806b4`, filed `14fb9ff` → false from 08-28; corrected R-IV.127(c) |
| L6 | 08-31 crypto figure fixed in a header while still moving | Premature settling | Same header → PARTIAL edit R-IV.136(c); vindicated at d7 (settled 24 of 44 vs the 11 of 31 carried) |
| L7 | 08-20 cited as the observation-day floor | Adjacent citation (pre-window row) | 3DTE certification proposal → struck R-IV.127(a); exception moved to d4 (08-27, HG_1H = 41) |
| L8 | "d1–d6 LIVE and consumed on the ruled warrant" | Overclaim on a superseded header | 3DTE day-6 findings relay → withdrawn; EDGE ITEM 4 adopted R-IV.127(a) as LIVENESS-INDETERMINATE-BUT-NON-ZERO |
| L9 | `ib_break_up` + `va_migration: lower` as the crash trigger | Hypothesis from coincidence | 3DTE relay 09-02 → withdrawn in the v2.5 diagnosis relay (actual cause RE10045, §1.1) |
| L10 | Fleet-wide IB rate decline read as market conditions | Adjacent citation (real measurement, wrong universe) | ATLAS request "MEASURED RATE" section, §2.3 → corrected in the collapse-consumption relay: universe was 12 tickers, from 203 |
| L11 | OBS-0 named in v2.1's header, never implemented | Null verifier by omission | v2.1 header vs executable text → ruled R-IV.127(a)/(b); packet debt section |

### 5.2 3DTE attestations that held

- **`hub_get_market_profile` is PYTHIA-fed** — consumer-side corroboration of a code
  path CC-QUERY explicitly did not verify: 3DTE hub reads returned QQQ
  `as_of 09-01T14:30:52Z` and SMH `09-01T15:30:55Z`, matching `pythia_events`
  last-event timestamps to the second.
- **OBS-2's youngest-bucket partiality design** — the one piece of 3DTE instrument
  authorship that held all week; 08-28 healed 18→19 overnight exactly as intended.
- **"97 tickers tall"** — NOT corroborable from this lane's inputs or disk.
  CC-QUERY's addressed figures (212 / 206 / 167 / 203) are the measurable ones.

### 5.3 Instrument defects found by the instrument (OBS-01, 8 days)

OBS-0 gap (L11) · tripwire decay (coverage 3→1→0; CC-QUERY) · ARTEMIS fitted-band
failure (1 of 8 days in band, 6× spread) · PULLBACK_ENTRY CTA arm above band
independent of crypto · L5 cap silently truncating oldest rows (CC-QUERY) ·
premature settling (L6) · adjacent citation in the certification (L7).

### 5.4 Laws this lane contributed or had minted against it

Render-scope (CC-QUERY, from a 3DTE render) · caveat-capture (from 3DTE's own
self-sighting, then violated by 3DTE in the same block) · clearance-citation (from
3DTE citing its own request as a grant) · same-block corollary (spine, from a
3DTE-adjacent inconsistency) · dedicated-alert requirement (R-IV.109(e)) ·
OBS-0-required-for-successor-instruments (R-IV.127(b)) · intermittent-vs-continuous
watermarks (R-IV.127(d)) · guard-anchored-to-its-own-window (EDGE, from tripwire
decay).

---

## §6 — STATE AT CLOSE

- **Ledger with spine: ZERO.**
- **OBS-01: RETIRED** at its terminal read, on schedule, destination unchanged.
- **D2 satisfied in full:** RETIRE declared as destination, CONTINUE ran to terminus
  09-01 with zero new build, packet labeled EMITTER-CHARACTERIZATION ONLY.
- **HOLY_GRAIL_1H:** retired on measurement (PR-105, blob `beac87d7` —
  KILL-CONFIRMED both directions, all four criterial cells negative at every friction
  level including zero). The observation window proved the *emitter* healthy and
  entirely suppressed; it bears on nothing about edge.
- **SPEC-01:** DRAFT-FILED, ATLAS request held on two conditions (§2.2).
- **SPEC-02/03/04:** filed, unscheduled.
- **What opened this lane:** whether the hub saw the 2026-08-03/04 melt-up. Answered:
  it saw it in five surfaces and said nothing, because a hard-coded suppress set in
  `l0_routing.py` buried its highest-volume strategy without regard to score.

---

*Authored by 3DTE, 2026-09-03. Handoff complete. §3 is a declared gap, not an
omission — read it before treating this document as whole.*
