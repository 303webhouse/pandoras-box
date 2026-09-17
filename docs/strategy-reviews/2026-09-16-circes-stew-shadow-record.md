# CIRCE'S STEW | Fade the Breakout — shadow record

**Internal id:** `circes_stew`. **Lineage (only):** Turtle Soup — Williams; Raschke's
close-back-inside refinement (Olympus review 2026-04-22 §2.1).
**State:** SHADOW since d990abb (deployed 2026-09-17 05:50 UTC). Not tradeable, not scored,
not sized. **Rulings:** R-IV.421, R-IV.422, R-IV.429(b), R-IV.430(a)(b), R-IV.432(a)-(e)(h).
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
either** gate regime. **A promotion claim states which labels its expectancy came from.**
A row with no label (NULL — the rotation cache was unreadable at fire time) is
`UNLABELLED`, its own stratum, never assigned one (R-IV.432(d)).

## RATIFIED — R-IV.432 (the grading)

- **Walk hold: 10 sessions is the primary; 5 and 20 are reported beside it.** Nobody has measured
  the hold, so the curve is reported rather than one number defended.
- **"VA-edge >= 60% of winners" means `edge` + `outside`** -- both are the extension case the
  review meant; `mid` was the reject. The edge / outside split is reported beside it.
- **Exclusions:** a row whose window holds a calendar factor its series does not carry, or an
  adjustment seam, is counted, kept out of the aggregates, and reported on its own line.
- **A second vendor** checks every row whose window spans a calendar event (the HON case: the
  primary vendor inflates pre-ex prices on its own factor, and same-vendor verification cannot
  see it). Disagreement holds the row -- flagged, never graded.

## PROMOTION GATES (R-IV.421(f), unchanged)

Sharpe > 0.8 · PF > 1.4 · >= 100 trades · VA-edge (edge + outside) >= 60% of winners ·
positive expectancy in BOTH `CONCENTRATED_LEADERSHIP` and `BROAD_ROTATION`. Evaluated on the
primary hold. Shadow visibility is not promotion.

## THE NULL CASE — the number the filters must beat (R-IV.432(h))

**CIRCE'S STEW, UNFILTERED: SPY daily only, no location gate, no regime, walk grades on the
module's own rules.** Bars 2020-01-02 -> 2026-09-16 (yfinance, split-adjusted, dividends
excluded, fetched 2026-09-17 13:22 UTC), code at the backtest module v1 plus R-IV.432.

| hold | trades | win rate | avg win | avg loss | **expectancy** | PF | max DD | Sharpe |
|---|---|---|---|---|---|---|---|---|
| 5 | 226 | 36.3% | +1.83R | -1.42R | **-0.24R** | 0.73 | -65.3R | -0.63 |
| **10 (primary)** | 226 | 31.9% | +2.13R | -1.43R | **-0.30R** | 0.69 | -77.0R | -0.77 |
| 20 | 225 | 32.0% | +2.19R | -1.46R | **-0.29R** | 0.71 | -72.9R | -0.74 |

**Caveats, on the face:**
- **One symbol.** SPY is an index; the live shadow runs on single names.
- **No gates.** The location gate and the regime cannot be applied historically -- there is no
  historical prior-session VA, and the rotation regime is not stored. This is the trigger
  alone.
- **Average losses beyond -1R** are gap exits at the open, which the walk books at the price
  actually available.
- **Not a verdict on the gated strategy.** It is the baseline the gated version has to beat.

## OPEN PARAMETERS AND KNOWN GAPS

- **Firehose response:** more than 10 passing fires in a day surfaces none and latches the
  feed stopped until the gate is tightened and `GATE_VERSION` bumped. (Built; not separately
  ratified.)
- **Edge band 25%** is provisional until the first 30 fires show its distribution
  (R-IV.430(a)).
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
