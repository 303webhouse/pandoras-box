# Micro-Brief — DEF-KILLSWITCH-FAILOPEN + A-4 · v1.1

**Author:** SHELL · v1.0 2026-07-29 (spine-graded PASS), v1.1 same day (consolidates spine rulings R1–R4 post-Step-0), **v1.2 same day** (spine amendments A1–A3, amended and released under spine PRE-AUTHORIZATION — no further grade before build)
**Priority:** P1 MANDATORY pre-freeze · **Ships:** ALONE · **Governed by:** `docs/HONEST_SEAM_STANDARD.md`
**HARD FENCE (spine):** deploys **Friday 2026-07-31** or it does not deploy — no weekend slide. If Option-1 sizing balloons Thursday: STOP, report, fallback is spine's call.
**Executor:** CC-SHELL · spine grades the push before deploy GO. This file commits with the fix.

## Defect — two layers

**Layer 1 (frontend):** the KILL-SWITCH cell collapses fetch failure and `null` into "CLEAR / normal," no health treatment. (Phase 0 ACK; re-locate by content, lines have drifted.)
**Layer 2 (backend — Step-0 finding, SHELL-verified on origin):** `backend/services/read_only/board.py` serves **in-memory process state**; `kill_switch: null` exists only in its exception handler; every normal path coerces the module default into `"active": false` with `degraded: false` and `data_age_seconds ≈ 3e-05` — a maximum-confidence all-clear manufactured from an assumption. Redis absence is meanwhile the *healthy* resting state: one write site (`circuit_breaker.py` `_persist_circuit_breaker_state`), five event-driven callers, resting path never writes.

## Scope (R1 — fence amended, not breached; the stop-and-surface clause fired as designed)

**IN:** `get_kill_switch()` / board.py gains **provenance + real age** — how the state is known (event-confirmed this boot / restored-at-boot / default-since-boot with no persisted record) and the age of the last state-affecting event or boot. The fabricated `data_age` and `degraded: false` **die — report truth or report nothing.** `v2.js` five-state renderer + minimal CSS. TTL armed-path change per R4 below, own commit.
**OUT:** CB subsystem logic, all write paths, `apply_circuit_breaker()`, TTL refresh/write-logic (post-vacation), everything else. Nothing bundled.

## Five states (R2)

| Truth | Renders |
|---|---|
| Fetch OK · confirmed `false` (event-confirmed this boot) | **CLEAR** / normal — provenance + age beneath |
| Fetch OK · `false` restored-at-boot from persisted state | **CLEAR** — with its age shown plainly |
| Fetch OK · `true` | **ARMED** — red, prominent, unmissable |
| Fetch OK · default-since-boot, no persisted record | **NO TRIP ON RECORD** — calm, affirmative, provenance + age beneath. NOT "NO DATA": that implies breakage and trains the operator to ignore a healthy safety surface |
| Fetch failed / non-200 / timeout | **UNKNOWN** — source unreachable. Never CLEAR |

All five legible at 390×844 and desktop. Cell gains standard health/age treatment (Ruling 6 family).

## Authority rule (A1 — binding)

**In-memory state stays authoritative for `active`.** The enforcement consumers (`composite.py:843+`, `bias_scheduler.py:1036`) read memory — the display must mirror the enforcer, never Redis. **Redis presence = provenance only.** A display served from Redis could render ARMED while bias scoring runs unconstrained — a board asserting protection the system isn't applying, worse than the defect being fixed. **Divergence is disclosed, as a PROVENANCE VALUE, not a sixth visual state:** Redis holding an armed record while memory reads default → amber provenance line, wording "persisted armed record present, not loaded." Sizing must stay inside Thursday.

## Staleness (spine condition, binding)

Acceptance covers a **backgrounded-then-resumed PWA**: background the app, ≥2h elapses (real or simulated), resume → the cell either refetches on visibility or visibly shows its age. A two-hour-old CLEAR rendered as fresh is fail-open wearing a valid 200 → FAIL.

## A-4a — inert presence-check leg (A2)

Write then delete `bias:circuit_breaker` against **real Redis**; confirm the new backend reports persisted-record provenance from the live presence check. Synthetic fixtures never exercise the presence check — which is Option 1's whole value. Zero blast radius: nothing reads the key at runtime (Step-0). Governed by drill gate (i): pre-state captured as **existence**, restore to **ABSENT**. **HARD GATE: tight window, NEVER overlapping a deploy** — a process restart while that key is present restores armed state into memory and mutates live bias. Note: A-4a deliberately manufactures the A1 divergence condition — the amber "persisted armed record present, not loaded" disclosure MUST render during the window; capture it as evidence.

## A-4b — fire drill (R3: ratified, POST-deploy)

**Pre-deploy positive control: SYNTHETIC fixtures** for all five states in the new payload shape (a pre-deploy live capture would fixture the old shape — wrong artifact).
**Post-deploy drill — Friday evening or Saturday, market-closed window, ONE real production write total:** arm via the real path (`apply_circuit_breaker()` — CC-SHELL proposes the minimal invocation mechanism for spine grade before any write) → **ARMED renders on Nick's device** → Discord alert arrives (**Nick is told it's a drill BEFORE it fires**) → reset exercised → post-reset state renders truthfully → the real armed payload is captured as the permanent regression fixture.
**Drill gates, all binding:** (i) **restore-to-ABSENT** — pre-state captured as *existence*, not value; if the key was absent, the end state is a **deleted key**, never `false` (false renders CLEAR, absent renders NO TRIP ON RECORD — opposite meanings, identical byte-diff); (ii) **reversibility confirmed per consumer BEFORE the write** — including crypto lanes, which never close; (iii) any bias rows the drill writes are **timestamped/tagged as drill artifacts** so R1–R6 audit work cannot later misread them as signal; (iv) every step reported.

## TTL (R4 — DEF-KILLSWITCH-TTL-RESTART, direction FIXED: armed state fails CLOSED)

**PRECONDITION (A3 — blocks this commit only):** before removing the armed-path expiry, verify the manual reset endpoint is reachable by Nick **from his phone**. Fail-closed plus an unreachable reset strands him with a permanently-armed breaker for nine days. Not phone-reachable → **STOP this commit, report** — that becomes the more urgent half and spine rules separately. Then:
**This cycle, own commit:** TTL value change/removal on the **armed path only** — an armed breaker must not expire into silence. **Post-vacation:** anything touching refresh or write logic (Discord-alert mitigation documented in the registration).

## Acceptance

1. Synthetic positive control, all five states, 390×844 + 1480 — screenshots of ARMED, UNKNOWN, and NO TRIP ON RECORD mandatory.
2. Live post-deploy read + plain-language explanation of which state production landed in (expected: NO TRIP ON RECORD if the key remains absent).
3. Backgrounded-PWA staleness leg passes.
4. Desktop regression: layout untouched, only truthful states changed.
5. Own cycle, explicit refspec, four-step verify; spine grades push before deploy GO. Freeze law absolute.
6. Drill report evidencing all four gates, ARMED-on-device screenshot included.
7. A-4a report: write→delete with pre-state captured as existence, provenance rendered from the real presence check, A1 divergence disclosure captured, window timing evidenced as non-overlapping any deploy.
8. A3 evidence: manual reset confirmed reachable from Nick's phone (method + screenshot), or the STOP invoked and reported.

## Operator note (Nick, on the record)

After Friday's deploy the resting cell likely reads **NO TRIP ON RECORD** — calm and correct, not breakage. You witness the drill live on your phone; the Discord alert that follows is the drill, and you'll be told before it fires.

---

## Execution record — CC-SHELL (2026-07-29)

**A3 PRECONDITION: STOP INVOKED. The manual reset is NOT phone-reachable, so the TTL
armed-path commit was not made.** Four independent confirmations:

- `POST /webhook/circuit_breaker/reset` is `Depends(require_api_key)`; production returns
  **401** without a key.
- No reset control exists in `frontend/` — zero references to the route.
- `_send_discord_notification()` posts a plain embed through a webhook ("direct HTTP, no
  bot"): no `components`, no `custom_id`. Discord webhooks cannot carry buttons that route
  back, so the CB alert is notification-only.
- No committee/VPS script exposes a CB reset.

The only reset path is an authenticated POST carrying `PIVOT_API_KEY`, which is not an
operator action from a phone. Per A3 this is now the more urgent half: making the armed
path fail closed while the reset is unreachable would strand a permanently-armed breaker
through the freeze. Spine rules separately.

**Shipped in this commit (Layer 1 + Layer 2 rendering truth):**

- `board.py` — `get_kill_switch()` gains a `provenance` block: `source`
  (`event-confirmed` / `restored-at-boot` / `default-since-boot`), truthful `as_of` and
  `age_seconds` anchored to the last state-affecting event or boot, `persisted_record`
  from a live Redis presence check, and the A1 `divergence` disclosure.
- `circuit_breaker.py` — observability-only provenance ledger. No behaviour change, no
  write-path logic change; marked at the single existing persist choke point so all five
  event callers are covered by one line.
- `v2.js` / `v2.css` — five-state renderer, single detail line, amber honest-seam token.

**Reading recorded against R1's "the fabricated `data_age` and `degraded: false` die":**
they were made **truthful** rather than deleted. `map_stable_status()` keys the MCP
staleness contract on `as_of` + `data_age_seconds`; deleting them would force
`hub_get_board_state` to report `unavailable` permanently. "Report truth or report
nothing" — truth was reportable, so it is reported. `degraded` stays `false` for the
resting state because it is not a fault; honesty is carried by provenance. A genuine read
failure still takes the exception path with `as_of: null` and `degraded: true`.

**Departures from the letter of the brief, both forced by measurement:**

1. **One detail line, not "provenance + age beneath" as a second line.** The regime band
   is a fixed-height grid sized by its tallest cell. A fourth line grew every cell from
   87px to 98px and made the band overflow — which would have clipped the provenance away,
   defeating its purpose. Measured against `origin/main`: band height is now identical at
   87px with zero overflow in all seven states.
2. **`pending_reset` renders in the ARMED family** (`ARMED · PENDING`, vermilion, pulsing)
   rather than as the pre-existing calm teal `PENDING`. `pending_reset` still means
   `active: true` and the breaker is still enforcing caps and floors until an operator
   accepts, so R2's "`true` → ARMED, unmissable" governs.

**Evidence:** 16/16 synthetic positive-control assertions pass at 390×844 and 1480, across
all five states plus `ARMED · PENDING` and the A1 divergence disclosure, driven by HTTP 500
and by network abort for UNKNOWN. Staleness leg passes both scenarios: polling pauses while
hidden, a refetch fires on resume, and a resume against a broken source falls to UNKNOWN
rather than retaining the stale CLEAR. Desktop regression measured against `origin/main`,
band geometry unchanged, no horizontal scroll at either width.
