# CC HOTFIX BRIEF — Catalyst Tab v0 (TODAY, market hours — Nick override recorded)

**Date:** 2026-06-12 (IPO morning) · **Deadline gate: DEPLOYED + VERIFIED by 09:30 MT or HOLD all of it until after close (14:00 MT).** No exceptions to the gate — it is the thing that makes "now" acceptable.

**Override record (Titans governance):** This build deploys during market hours, overriding
PROJECT_RULES deploy-window policy. Explicit, repeated, informed Nick directive 2026-06-12 AM.
Risk accepted by owner. Mitigations: additive-only changes, local boot test before push,
empirical post-deploy verification, instant rollback path, and the standalone PowerShell scanner
(`scripts/flow_scanner.py`) running as an INDEPENDENT fallback radar the entire time — today's
trading does NOT depend on this deploy succeeding.

**Relationship to the weekend brief:** This is a forward slice of
`2026-06-11-catalyst-module-v1.md` Task 6, using the SAME live primitives (`catalyst_events`,
`lightning_cards`, `hermes_flash` WS). The weekend build replaces the scanner→webhook feed with
the server-side poller. Nothing here is throwaway except ~30 lines in the scanner.

---

## Scope — three tasks, nothing else

### TASK A — Scanner posts its signals to the hub (NO deploy required)

A.1 — READ `backend/webhooks/hermes.py` lines ~91–230 first. Determine the exact payload shape
`hermes_webhook()` accepts and what `_store_catalyst_event()` (line ~510) persists.

A.2 — Add `post_to_hub(event: dict)` to `scripts/flow_scanner.py`, called from the two emit
points (cluster alerts + DP blocks). Payload carries: ticker, direction, premium, sweeps,
dominance, scenario, event_type ("flow_cluster" | "dp_block"), source="flow_scanner_v2".
Conform it to whatever shape A.1 reveals. Include `"secret"` from env `HERMES_WEBHOOK_SECRET`
(injected by `railway run` — NEVER print or log it). Config flag at top: `POST_TO_HUB = True`
so Nick can kill it with one edit.

A.3 — **Fallback if the Hermes handler shape-rejects non-velocity payloads (422):** add a
minimal `POST /api/catalyst/manual` to the backend protected by the EXISTING `require_api_key`
dependency (already in `backend/main.py`), writing via the existing `_store_catalyst_event()`.
Scanner sends `X-API-Key` from env `PIVOT_API_KEY`. This moves the backend change into Task B's
single deploy. Do NOT create any unauthenticated route (AEGIS hard veto).

A.4 — Side-effect check: if the Hermes path triggers the VPS scrape burst, confirm it fail-opens
(try/except, non-blocking). If it would block or error loudly, use the A.3 fallback route
instead. Do not modify the Hermes handler itself today.

A.5 — Verify BEFORE Task B: one test POST returns 200 and a row appears in `catalyst_events`
(query it read-only). Log the row id in the closure note.

### TASK B — "Catalyst" tab in the Insights section (frontend; the deploy)

B.1 — READ `frontend/app.js` tab machinery (`switchFeedTab` ~4521, tier badge MAP ~4199, WS
message switch ~1282) and the existing hermes-alerts read path (`get_hermes_alerts`,
hermes.py:409 — find its HTTP route; if none is mounted, add a read-only GET alongside A.3).

B.2 — ADD a new tab "Catalyst" to the Insights section in `frontend/index.html` + `app.js`.
ADDITIVE ONLY — do not remove or modify the existing four tabs today (that's weekend scope).

B.3 — Tab behavior, deliberately basic:
- On open: fetch recent catalyst events (last 50, newest first) from the read path.
- Live: on `hermes_flash` / catalyst WS messages, prepend a card (batch DOM writes).
- Card = one decisive line, mirroring the scanner's terminal format: `▲/▼ TICKER DIRECTION
  $PREMIUM (sweeps · dominance% one-sided) → scenario`, plus a timestamp.
- **Large text — minimum 18px card body (Nick's eyes are the reason this tab exists).**
- Staleness: show "last event HH:MM:SS"; empty state reads "ARMED — no qualifying clusters yet"
  (silence must look healthy, not broken).
- Cap 25 visible cards. No other features. Resist improvement.

### TASK C — Deploy + verify + rollback (the gate)

C.1 — LOCAL BOOT TEST IS MANDATORY BEFORE PUSH: run the backend locally (uvicorn) — app must
boot clean and `/health` (or equivalent) must respond. A crash-looping Railway deploy is the
one unacceptable failure mode; this test eliminates it.

C.2 — Commit (`git commit -F C:\temp\commitmsg.txt`), push to main → Railway auto-deploys.
Push IMMEDIATELY when ready — earlier in the quiet pre-cross window is strictly safer.

C.3 — Verify empirically (deploy status is NOT verification, per PROJECT_RULES): wait 70–170s,
then (1) hub liveness (bias composite endpoint or /health), (2) dashboard loads, (3) Catalyst
tab renders, (4) one scanner test POST appears as a card. All four or it didn't ship.

C.4 — Rollback path: `git revert HEAD && git push` (second restart, bounded). PowerShell
scanner is unaffected either way.

C.5 — **09:30 MT gate:** if C.3 is not fully green by 09:30 MT, revert anything pushed and HOLD
the remainder until after close. Nick trades off the PowerShell window; nothing is lost.

---

### TASK D — Targeted-setup trigger card + sound (frontend only; rides Task B)

**Design constraint (do not violate):** This is a CLIENT-SIDE FILTER on the catalyst event
stream Task A/B already deliver. NO new backend, NO new endpoint, NO new poll, NO new WS channel.
Every catalyst event already arrives in the browser (Task B.3); Task D inspects each one as it
lands and escalates the ones that match the targeted setup. If Task B is not working, Task D does
nothing — it is purely additive on top of B's rails. Build D ONLY after B.3 renders live cards.

D.1 — **Match criteria.** A catalyst event is a "TARGETED HIT" when ALL hold (read from the event
fields the scanner already sends — ticker, direction, premium, dominance, scenario, event_type):
   - `event_type == "flow_cluster"` AND `dominance >= 0.80` (stricter than the tab's 0.70 floor —
     a targeted hit is a HIGH-conviction one-sided cluster, not just any cluster), OR
   - `event_type == "dp_block"` (every SPCX dark-pool block is a targeted hit — institutional
     print on the new listing is always setup-grade).
   - Plus the scenario tag is one of the live trade scenarios (NOT "context print"): i.e. the
     event's `scenario` contains "Scenario A", "Scenario B", or "forced-selling".
   Put the whole predicate in ONE function `isTargetedHit(event)` so Nick can edit the thresholds
   in one place. Default DOMINANCE_HIT = 0.80 as a named const at top of the module.

D.2 — **Visual escalation** when `isTargetedHit` is true (in addition to the normal card render):
   - Render the card in a distinct "HIT" style — heavier border, accent background, a ★ TARGET
     badge. Must be unmistakable at a glance (Nick's eyes — large, high-contrast).
   - PIN it to a "🎯 Targeted Hits" strip at the TOP of the Catalyst tab, above the rolling feed,
     newest first, cap 5. Normal (non-hit) cards continue flowing in the feed below, unchanged.
   - Include the decisive line + scenario so the card says what to DO, not just what fired.

D.3 — **Sound.** On a targeted hit, play a short alert tone.
   - Generate it with the Web Audio API (oscillator beep, ~150ms, two quick tones) — DO NOT add
     an audio file dependency or external asset. Self-contained in JS.
   - **Browser autoplay guard:** audio context must be unlocked by a user gesture first. Add a
     one-time "🔔 Enable sound" button on the Catalyst tab; clicking it resumes/creates the
     AudioContext. Until clicked, hits still pin + flash visually (sound is enhancement, never the
     only signal). Show whether sound is armed/muted.
   - Debounce: max one beep per 3 seconds even if multiple hits land together (no alarm storms).

D.4 — **Self-test before deploy (extends C.1):** with the backend local, POST a synthetic event
that satisfies `isTargetedHit` (e.g. flow_cluster, dominance 0.85, scenario "Scenario A leg") and
confirm: card pins to the Hits strip, renders in HIT style, and (after clicking Enable sound) the
beep fires. Also POST a non-hit (dominance 0.72, "context print") and confirm it does NOT pin or
beep — it just flows in the feed. Log both in the closure note.

D.5 — **Severability:** Task D is the lowest priority of A/B/D. If the 09:30 gate is approaching
and D isn't done, ship A+B (the tab) and revert/defer D — a working live tab without the trigger
card is a complete, useful deliverable. Do not let D jeopardize the gate.

---

### TASK E — Catalyst↔Signal Confluence Flag (Nick directive 2026-06-12; explicit scope add — supersedes the no-scope-growth gate for this task only; ships as v=162)

**Architecture decision (Fable + Olympus-reviewed): EXTEND existing machinery, build nothing
parallel.** Discovery anchors CC must read first:
- Event-driven confirmation hook ALREADY runs at `backend/signals/pipeline.py:1144-1147`
  (lightning-card match → `add_lightning_confirmation` → WS). Task E adds a SECOND check in the
  same location, same pattern, pointed at `catalyst_events`.
- Batch confluence engine ALREADY runs (`main.py:220` → `confluence/engine.py`, 15-min RTH
  cadence). **DO NOT modify it today** — it is the weekend home for the richer version
  (reverse-direction confluence, auction context).

E.1 — In `signals/pipeline.py`, immediately adjacent to the existing lightning hook (~1144),
after the signal row persists: query `catalyst_events` for same `trigger_ticker`, `event_type IN
('flow_cluster','dp_block')`, `created_at` within `CONFLUENCE_WINDOW_MIN` (module const, default
15), AND direction agreement (signal `direction` vs event payload direction; `dp_block` is
direction-agnostic → matches either, flagged `direction_match: "dp_agnostic"`).

E.2 — On hit, dedupe via Redis SETNX `catalyst:confluence:{signal_id}`, then write via the
existing `_store_catalyst_event(event_type='confluence_flag', trigger_ticker=...,
sector_velocity={signal_id, strategy, signal_direction, catalyst_event_id, catalyst_event_type,
catalyst_direction, direction_match, delta_seconds, window_min, headline:"CONFLUENCE — context,
not entry timing"})` and broadcast a `catalyst_event` WS message exactly as `/catalyst/manual`
does. The card then renders in the Catalyst tab automatically.

E.3 — **FAIL-OPEN MANDATE (the one hard safety rule):** the entire check is wrapped try/except;
any error logs a warning and continues. Confluence must NEVER break, block, or delay signal
emission — it rides inside the live pipeline.

E.4 — Task D interplay: add `event_type === 'confluence_flag'` to `isTargetedHit()` → pins to
the 🎯 strip + beeps. Card copy MUST include the strategy name and the phrase "context, not
entry timing."

E.5 — Committee visibility v0: confluence rows surface through the existing hermes-alerts read
path, distinguishable by `event_type='confluence_flag'`; the clean labeled MCP surface lands
with weekend Task 7. **URSA requirement:** payload carries `strategy` so backtests can separate
independent-source confluence (price-based scanners, e.g. Holy Grail) from shared-source echo
(flow-derived scanners confirming flow clusters — same UW well, not independent).

E.6 — Touches NOTHING else: no scoring logic, no `signals` schema change, no
`confluence/engine.py` change, no auth change. Writes ONLY via `_store_catalyst_event`.

E.7 — Verify: local boot test; synthetic test = insert a catalyst event **labeled TEST** for a
ticker, then emit/simulate a signal on the same ticker inside the window → exactly ONE
⚡ TEST confluence card appears (SETNX dedupe holds on re-run); a signal with no recent catalyst
event produces nothing. (Lesson from this morning stands: every synthetic event is visibly
labeled TEST in its headline.)

E.8 — **Deploy gate:** build + boot-test now. PUSH only in calm air — NOT while the SPCX cross
is imminent or printing, and NOT while Nick has an open position; if no calm window appears,
push after close (it was still built today). Severable from A/B/D — their deployment status is
unaffected by E.

E.9 — **Calibration note (goes in the closure doc):** `confluence_flag` is CONTEXT-ONLY until
n≥50 flagged events are backtested against the non-confluence baseline (hit rate + lead/lag
`delta_seconds` distribution). No agent, card, or sizing logic treats it as conviction input
before that gate. Primary v0 purpose is data capture on a record-volatility day.

---

## Hard gates / do-NOT list
- NO changes to: job scheduler, scoring, webhook auth behavior, `WEBHOOK_HERMES_ENFORCE`
  (stays observe today), existing Insights tabs, any schema (tables already exist).
- NO unauthenticated endpoints. NO secrets echoed, logged, or committed.
- NO scope growth: if a "small improvement" suggests itself, it goes in the weekend brief.
- Scanner keeps running in PowerShell throughout — do not stop it, do not make the tab its
  only output.

## Done definition
1. Scanner clusters + DP blocks visible as cards in the new Catalyst tab, live via WS.
2. All four C.3 verifications logged with timestamps in a short closure note
   (`docs/strategy-reviews/catalyst-tab-v0-closure-2026-06-12.md`), including deploy SHA.
3. Existing tabs and hub behavior unchanged. Rollback never needed — or executed cleanly.
