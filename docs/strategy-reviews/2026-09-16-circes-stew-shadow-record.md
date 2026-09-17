# CIRCE'S STEW | Fade the Breakout — shadow record

**Internal id:** `circes_stew`. **Lineage (only):** Turtle Soup — Williams; Raschke's
close-back-inside refinement (Olympus review 2026-04-22 §2.1).
**State:** SHADOW since d990abb (deployed 2026-09-17 05:50 UTC). Not tradeable, not scored,
not sized. **Rulings:** R-IV.421, R-IV.422, R-IV.429(b), R-IV.430(a)(b).
**Code:** `backend/scanners/circes_stew.py` (trigger, pure), `backend/jobs/circes_stew_job.py`
(daily pass). **Tests:** `backend/tests/test_circes_stew.py`.

> **CIRCE'S STEW · SHADOW — unbacktested, no expectancy measured, do not size.**

---

## THE TRIGGER (as built, R-IV.421(c))

B2 daily, N = 20. A 20-bar high (low) is breached on bar B; the **first** close back inside
that level lands 1–4 bars later, counting B. Evaluated on the session's last bar only, so a
failure fires once, on the day it confirms. A breakout already outside before the window is
not a failure inside it. Where two breach bars qualify, the earliest names the level. Stop at
the failed extension; target a fixed 2R. Runs 16:30 ET on trading days.

## RATIFIED — R-IV.430

**(a) VA GATING ON THE FIRE CLOSE.** The close that fires the signal is located against the
PRIOR session's developing VA, as it stood before the signal's session (never cumulative).
`outside` and `edge` pass; `mid` and unknown do not.
**Reasoning, on the face:** the breach extreme is outside the prior VA by construction — on a
same-bar failure the breach bar's high exceeds a 20-bar high the prior session never reached —
so gating on the extreme would filter nothing. The extreme's location is still recorded on
every row (`va.extreme_location`).

**Edge band = the outer 25% of the VA width on each side — PROVISIONAL** until the first 30
fires show its distribution. Recorded on every row either way (`va.edge_fraction`, `va.zone`,
`va.vah`, `va.val`), so a changed band can be re-evaluated against the rows already
collected. Changing it bumps `GATE_VERSION`.

**(b) REGIME VOCABULARY FOR THE PROMOTION GATE.** The promotion gate requires positive
expectancy in both sector regimes (R-IV.421(f)). The stored label is
`sector_rotation_state`, from the one classifier in `services/read_only/sectors.py`:

| promotion-gate regime | stored label |
|---|---|
| **concentrated** | `CONCENTRATED_LEADERSHIP` |
| **rotating** | `BROAD_ROTATION` |
| *own stratum* | `ACTIVE_DISTRIBUTION` |
| *own stratum* | `REGIME_AGNOSTIC` |

`ACTIVE_DISTRIBUTION` and `REGIME_AGNOSTIC` are **reported separately and never folded into
either** gate regime. **A promotion claim states which labels its expectancy came from.** *BUILD's reading, not
ruled:* a row with no label (NULL — the rotation cache was unreadable at fire time) is
reported as its own stratum as well, never assigned one.

## PROMOTION GATES (R-IV.421(f), unchanged)

Sharpe > 0.8 · PF > 1.4 · ≥ 100 trades · VA-edge ≥ 60% of winners · positive expectancy in
BOTH `CONCENTRATED_LEADERSHIP` and `BROAD_ROTATION`. Shadow visibility is not promotion.

## OPEN PARAMETERS AND KNOWN GAPS

- **Firehose response:** more than 10 passing fires in a day surfaces none and latches the
  feed stopped until the gate is tightened and `GATE_VERSION` bumped. (Built; not separately
  ratified.)
- **Universe:** tickers with a PYTHIA event in the last ~10 calendar days — location is part
  of the trigger, so a name with no VA can never pass it.
- **Flow:** there is no per-bar dark-pool or put-sweep store; the payload carries the latest
  stored `flow_events` snapshot on the fire date and says so.
- **Raschke's "prior extreme ≥ 4 sessions old"** is not in the spec and is not implemented.
- **IV rank** comes from the universe cache (2h TTL); often NULL, recorded as NULL.
- **Price basis:** yfinance daily, split+dividend adjusted, fetched at run time — on every
  payload (`price_basis`), per R-IV.428(a)(1).

## WHERE THE ROWS ARE

`signals` with `strategy = 'circes_stew'`: `source = 'circes_stew'` (surfaced) or
`'circes_stew_unsurfaced'` (gate-rejected or stopped), `status = 'SHADOW'`, payload at
`triggering_factors -> 'circes_stew'`, join columns `va_location` and
`sector_rotation_state`. The River reads `/api/trade-ideas?status=SHADOW&source=circes_stew`.
