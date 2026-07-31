# A-4b fire-drill report — DEF-KILLSWITCH-FAILOPEN

**Executed:** CC-SHELL, 2026-07-31, market-closed (overnight, US cash session shut)
**Mechanism:** `POST /webhook/circuit_breaker/test/spy_down_2pct`, machine header, server-side
**Graded:** spine PASS, with the `spy_down_2pct` override (Discord fires only at 2pct+)
**Result: PASS.** ARMED proved capable of firing, rendering, and alerting; reset proved
one-shot; artifacts fully enumerated.

## Timeline

| # | step | UTC | MDT |
|---|---|---|---|
| 1 | pre-state + watermarks | 07:01:26 | 01:01:26 AM |
| 1 | **ARM** | 07:01:39 | 01:01:39 AM |
| 1 | ARMED captured (390×844 + 1480) | 07:01:55 | — |
| 1 | **RESET** | 07:02:15 | 01:02:15 AM |
| 2 | **ARM** (window held open for operator) | 07:27:17 | 01:27:17 AM |
| 2 | operator confirmed ARMED visually | ~07:28:3x | ~01:28 AM |
| 2 | **RESET** | 07:28:43 | 01:28:43 AM |

Run 1 armed window: **36 seconds**. Run 2: **86 seconds**.

## Why there were two runs

Run 1's window was closed after 36 s, optimising for safety. That was too fast for the
operator to reach the board, and the "where to look" instruction had not been given — so
the on-device ARMED screenshot, a mandatory acceptance item, was not captured. Run 2 was
authorised by Nick directly and held **open until he confirmed**, rather than closed on a
timer. **This is a second production write, beyond the "one real production write total"
budget** — recorded here explicitly. It was spent to satisfy the on-device evidence the
brief itself requires.

Lesson for any future drill: the operator instruction ("sixth cell of the top band,
labelled KILL-SWITCH, turns red and pulses") must precede the arm, and the window should be
closed on operator confirmation, never on a timer.

## Evidence

**ARMED state applied** — `active: true`, `trigger: spy_down_2pct`, `bias_cap: LEAN_TORO`,
`bias_floor: LEAN_URSA`, `scoring_modifier: 0.75`.

**ARMED rendered** — vermilion `rgb(255,92,51)`, cell pulsing, `spy_down_2pct · fired 16s
ago`, verified headlessly at 390×844 and 1480, and confirmed on-device by Nick ("I see it
and the box around it is flashing vermillion").

**Discord alert delivered** — confirmed by Nick. This closes the last unproven leg of the
operator-notification path; Discord is the only push channel during the 08-04 → 08-15
phone-only window.

**Post-reset** — CLEAR, teal, not pulsing, `confirmed this session · 22s`. Health stayed
`healthy` (redis ok, postgres connected) across both runs.

## Gates

**(i) Pre-state → end state.** Captured at drill time as *existence*: **PRESENT**
(`present-clear`, Thursday's genuine `spy_recovery` record, ~6.5 h of TTL remaining).
End state **PRESENT** (`present-clear`). Matches. Deletion never arose, consistent with the
spine ruling that a real trip makes the record TRUE.

**(ii) Reversibility, crypto lanes.** Nothing to reverse — no crypto module imports
`get_circuit_breaker_state`/`apply_circuit_breaker`; the crypto "circuit breakers"
(`strc_monitor`, UW budget) are unrelated subsystems; `crypto_cycle_engine` runs its own
composite on its own tables; no crypto module reads `factor_readings` or
`bias_composite_history`. Confirmed before the first write.

**(iii) Artifact rows — complete enumeration.**

| run | table | rows written | ids |
|---|---|---|---|
| 1 | `bias_composite_history` | 1 | **27774** |
| 1 | `factor_readings` | 0 | — |
| 2 | `bias_composite_history` | 1 | **27777** |
| 2 | `factor_readings` | 0 | — |

**The complete drill footprint is two rows: `bias_composite_history` id 27774 and id
27777.** Nothing else was written.

Far below the ~25-row estimate, for a sound reason: with the market closed the forced
`score_all_factors()` returned `None` for every factor, and `None` is never persisted — the
"return None, never 0.0" honest-seam rule doing exactly its job. Both surviving rows are
**unconstrained** (`composite_score` byte-identical to the pre-drill row, `TORO_MINOR`,
`override: null`), because each came from the *reset's* unconstrained recompute. **No
CB-clamped row was ever persisted.**

At-risk readers, for the record: `api/weekly_audit.py`, `analytics/`, `api/bias.py`,
`signals/pipeline.py`. If R1–R6 audit work touches this window, exclude ids 27774 and 27777.

**(iv)** Every step above.

## Finding — register (P3, post-vacation)

**`bias_composite_history.created_at` is systematically ~6 hours ahead of real write time.**
Row 27774 records `created_at = 2026-07-31T13:02:16.984Z` for a write that provably occurred
at `07:02:1x Z`. Checked and excluded: the column default is `now()`, the database's own
`now()` returns correct UTC, `TIMEZONE` is `Etc/UTC`, and the table carries no triggers. The
source of the skew is unexplained.

This matters directly to the purpose of gate (iii): audit work keyed on `created_at` would
mis-window by six hours, which is precisely how a drill artifact gets misread as signal, or
a genuine signal gets attributed to a drill. Enumerating by **id** rather than timestamp is
therefore the reliable method, and is what this report does.

## Confirmed as a side effect

`POST /circuit_breaker/reset` is a **one-shot clear**, not a handshake — proven in code
(`reset_circuit_breaker()` rewrites the whole state dict including `pending_reset: False`)
and empirically (both runs returned `pending_reset: false`). The `accept_reset`/
`reject_reset` handshake belongs to the *automatic decay* path, gated behind
`max_minutes: 1440` for this trigger and unreachable inside a short drill. The operator's
board was never at risk of staying red.
