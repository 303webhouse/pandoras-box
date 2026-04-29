# Close-Handler Refactor — Titans Pre-Review (Pass 1)

**Date:** 2026-04-29
**Author:** Pivot (Sonnet, working as Olympus PIVOT proxy in Claude.ai)
**Status:** Draft for ATLAS / HELIOS / AEGIS Pass 1 review → ATHENA synthesis → Brief for CC
**Repo:** 303webhouse/pandoras-box, branch main

---

## How to use this document

This is a Pass 1 pre-review brief. The expected workflow is:

1. **ATLAS, HELIOS, AEGIS each review this independently.** Each agent answers the 'Specific review asks' in their section below, raises concerns, proposes alternatives.
2. **Pass 2:** each agent re-reviews after seeing the others' notes (incorporates feedback).
3. **ATHENA synthesizes** into a final design decision document.
4. Nick reviews ATHENA's synthesis, asks clarifying questions.
5. Pivot writes a CC implementation brief based on ATHENA's decisions.
6. **Final Titans pass** on the CC brief before it goes to Claude Code.

Do NOT skip Pass 1 — the goal is for each Titan to surface concerns from their domain BEFORE consensus pressure kicks in.

---

## 1. Background — what triggered this

### Tonight's incident (2026-04-28 → 04-29)

User attempted to close 1 of 2 open DINO call_debit_spread contracts. Hub UI was visibly lagging, so user double-clicked the 'accept' button. Both clicks reached the backend; both processed; result corrupted state.

**Hub state after the incident:**
- Single `unified_positions` row for DINO with `quantity: 1, status: CLOSED, exit_price: 1.92, realized_pnl: 74`
- The 'second' DINO contract — which user confirms is **still open at the broker** — had no representation in the hub at all
- Recovery: manual creation of a new OPEN row (`POS_DINO_20260429_062201`) with the surviving contract's details

**Severity:** P0. This is a financial system. State drift between hub and broker means trade decisions are made on wrong data. Tonight it cost the user 20 minutes of after-hours debugging; in market hours it could cost a real position.

### Latency observation

The double-click was not user error in isolation. It was a predictable response to a slow UI. Measured floor for the close handler:

- 6 sequential database round trips (each `async with pool.acquire()`)
- Network RTT to Railway public Postgres proxy: ~40-60ms per acquire
- Floor: ~250-400ms before query work
- Plus frontend behavior: full positions list refetch + MTM trigger after every action = additional 5-10s of 'loading' UI

When click-to-feedback exceeds ~500ms, humans double-click. That's a UX axiom, not user fault.

---

## 2. Problem statement

Three intertwined problems, each independently fixable:

### Problem A — Race condition (TOCTOU) in close handler

`backend/api/unified_positions.py` line 1399:
```python
row = await conn.fetchrow(
    "SELECT * FROM unified_positions WHERE position_id = $1 AND status = 'OPEN'",
    position_id
)
```

No row lock. No idempotency check. Two simultaneous requests both pass the `status = 'OPEN'` check before either commits, both run all 6 downstream operations independently. Classic time-of-check ≠ time-of-use race.

### Problem B — Slow click-to-feedback (UX consequence)

Close handler does 6 sequential DB ops, each grabbing a fresh pool connection:
1. SELECT position
2. INSERT trades record
3. UPDATE unified_positions
4. (conditional) Resolve signal outcome (1+ DB ops)
5. UPDATE accounts (cash adjustment)
6. INSERT closed_positions

Plus frontend likely refetches `/api/v2/positions` after success and triggers MTM. End-to-end: 5-10 seconds of 'loading' state on the close button.

### Problem C — No frontend guard against multi-click

Close button is not disabled on click. No debounce. No optimistic UI to give immediate feedback. User has no choice but to wait — or click again hoping the first click was lost.

These three compound: slow backend + no frontend guard + no backend idempotency = corruption.

---

## 3. Proposed scope (three components)

### Component 1 — Backend idempotency (P0, must ship first)

**Goal:** A duplicate close request within ~5 seconds returns 409 Conflict instead of corrupting state.

**Three implementation options:**

**1a. Redis lock keyed on `position_id`.** SET NX EX 5 at start of handler, DEL at end. Requires Upstash Redis already in stack (REDIS_URL env var). Survives across FastAPI workers.

**1b. Postgres advisory lock or `SELECT ... FOR UPDATE`.** Lock the row at fetch time. Forces serial execution within the transaction. No new infrastructure.

**1c. Idempotency-key header.** Frontend generates a UUID per close attempt, sends in `Idempotency-Key` header. Backend checks if seen recently (Redis or DB), short-circuits dupes. Industry standard (Stripe model). More robust but more frontend work.

### Component 2 — Frontend debounce + optimistic UI (P1)

**Goal:** Click feels instant. Second click physically cannot fire.

**Sub-features:**
- Disable button on first click (instant, no setState wait)
- Show 'Closing...' text immediately
- Optimistic update: remove the position from the visible list optimistically, restore on backend error
- Debounce on the click handler as belt-and-suspenders

### Component 3 — Backend latency reduction (P2)

**Goal:** End-to-end close latency target ≤ 500ms (from 5-10s today).

**Sub-changes:**
- Wrap all critical-path DB ops in a single transaction with one connection acquire (6 acquires → 1)
- Move analytics writes (`closed_positions` insert) to a background task
- Move signal resolution to a background task
- (Frontend, related): on close success, surgically remove that position from local state — do NOT refetch full list, do NOT trigger MTM

---

## 4. Specific review asks per Titan

### ATLAS (Backend Architect, Wall St finance background)

You own this section. Your domain.

1. **Lock mechanism choice — Redis vs PG row lock vs idempotency-key header.** Which gives the best safety/complexity tradeoff for a single-user, low-concurrency trading system? What's your read on the risk if Redis is unreachable mid-handler (graceful degrade or fail-closed)?

2. **Transaction scope.** If we wrap critical-path DB ops in a single transaction, what are the boundaries? Specifically: should the trades-table INSERT and the unified_positions UPDATE be in the same transaction (so they either both commit or both roll back)? Today they're separate — if the UPDATE fails, the trade record is orphaned.

3. **Background task safety.** What's the right pattern for `closed_positions` insert and signal resolution? `asyncio.ensure_future` (current pattern for proximity attribution), a Celery-style queue, or a periodic reconciliation job? Failure mode if a background task fails silently?

4. **Connection pool implications.** Currently each DB op grabs a connection. If we collapse to 1 connection per close, does that change pool sizing? Are there other endpoints similarly profligate that we should fix opportunistically (NO — out of scope, but flag any obvious ones)?

5. **State drift detection.** Beyond preventing the bug, should we add a periodic reconciliation job that reads broker state (Robinhood doesn't have a public API but the user could paste a snapshot) and flags hub/broker divergence? Out of scope for this brief but flag if you think it's a real gap.

### HELIOS (Frontend UI/UX, high-stress environment specialist)

This is exactly your wheelhouse — trade-execution UX where humans are clicking under stress.

1. **Debounce timing.** 500ms is conventional. For a financial action where a misclick has real cost, should it be longer? 1s? Should we add a confirm step instead?

2. **Optimistic UI rollback.** Position is shown removed from list optimistically. Backend fails. How do we communicate the rollback without making the user lose trust? Toast notification? Position reappears with a warning state? Where does the user expect to see the failure message?

3. **Loading state communication.** Current state: button stuck in 'loading' with no progress indicator. Better patterns for a multi-second operation: progress bar, step-by-step status ('Submitting close...' → 'Recording fill...' → 'Updating ledger...')? Or is that over-engineered for an operation that should be ≤500ms after Component 3?

4. **Two-step confirm vs one-click.** Pro-confirm: prevents misclicks entirely. Con-confirm: adds a step in time-sensitive trading. Where does HELIOS land on Robinhood-style swipe-to-confirm vs current one-click-execute? Note user has expressed frustration with both UX patterns in past contexts.

5. **Error vocabulary.** When idempotency rejects a duplicate (409 Conflict), what does the user see? 'Already submitted' vs 'Duplicate click detected' vs silent (just don't fire the second action)? Affects user trust and learning.

6. **Mobile vs desktop.** User trades from desktop primarily but checks positions on mobile. Does the debounce/optimistic UI design need to differ by viewport?

### AEGIS (Cybersecurity / Data Privacy)

This is mostly a UX/architecture refactor, but flagging for your review:

1. **Redis lock key design.** If we go with Redis locks, the key is something like `close_lock:{position_id}`. Position IDs are UUID-ish (`POS_DINO_20260423_182330`) — non-secret but identifiable. Are there logging/observability concerns? Should we hash the key?

2. **Idempotency-key header (Option 1c).** If frontend generates UUID v4 per attempt, that's safe. If it generates from request body hash, that's replayable. Which pattern do you require?

3. **Audit trail preservation.** Today, every close attempt that gets to step 2 creates a `trades` row. Under the new design, a duplicate-rejected click creates NO row. Is that the right audit posture, or do we want a `rejected_close_attempts` table for forensics? (Performance cost: another DB op on the unhappy path.)

4. **Race-condition disclosure.** Do we owe the user a notification when idempotency catches a duplicate? 'We protected you from a double-close' — security-positive UX. Or is that overshare?

5. **Background task failure mode.** If `closed_positions` insert is moved to background and silently fails, our analytics tables drift from `unified_positions`. Is that acceptable degradation? Should we alert?

### ATHENA (PM, final synthesis — answer these AFTER the others have spoken)

1. **Sequencing.** Do we ship Component 1 (idempotency) tomorrow standalone, then 2 and 3 over the next week? Or is the integrated design tight enough to ship together? The user is actively trading; risk of deferred fixes is more incidents.

2. **Scope creep risk.** ATLAS may want to refactor the connection pool, HELIOS may want a new design system component, AEGIS may want an audit table. What stays in scope, what goes to follow-up briefs?

3. **Verification protocol.** How do we prove idempotency works in prod without recreating the original bug? Synthetic load test? Manual concurrent curl pair? Staging environment? (No staging exists today — flag if needed.)

4. **Rollback plan.** If Component 1 ships and breaks something subtler, what's the kill switch? Feature flag on the lock check?

5. **Communication.** Does the user need new vocabulary for the idempotency-rejected case ('queued' vs 'already in flight' vs 'blocked')? UX writing pass needed?

---

## 5. Constraints (non-negotiable)

- **Repo and stack stay the same:** FastAPI / Postgres (Railway) / Upstash Redis / vanilla JS frontend
- **No staging environment.** All testing happens against prod or local mock. Must support a safe rollout strategy.
- **Single-user system in practice.** But the bug class (double-submit) doesn't require multiple users — concurrent requests from one user are enough.
- **Trading-hours sensitivity.** Cannot ship anything that risks a deploy-time blip during 9:30 AM–4:00 PM ET.
- **No breaking schema changes** to `unified_positions` — that table is referenced from too many other places. New tables / new columns OK, dropped/renamed columns not OK.

## 6. Out of scope (defer to separate briefs)

- Other endpoints with the same TOCTOU pattern (`update_position`, `create_position`, etc.) — we'll audit and fix in a follow-up
- General API-wide rate limiting
- Frontend bundle size reduction (530KB app.js — known, separate workstream)
- MTM speed improvements (related but distinct: MTM is a background job, close handler is user-facing)
- Reconciliation against broker state — flagged for future, not this sprint

## 7. Verification (proposed — ATHENA to refine)

For Component 1 specifically:

```bash
# Two simultaneous close requests on a 2-contract position
curl -X POST .../close -H 'X-API-Key: ...' -d '{"quantity":1,"exit_price":1.92}' &
curl -X POST .../close -H 'X-API-Key: ...' -d '{"quantity":1,"exit_price":1.92}' &
wait
```

Expected post-fix: one returns 200, one returns 409. Position record reflects exactly one close.
Expected pre-fix (today): both return 200, position state corrupted (the bug we hit tonight).

For Components 2 and 3: timing measurement — close-button click to UI-final-state should be ≤ 500ms p50, ≤ 1s p99.

---

## 8. Open questions for ATHENA's synthesis

These don't fit cleanly under any one Titan:

1. Is there value in exposing a 'draft close' intent (record intent, queue for execution) vs the current 'fire-and-commit' pattern? Bigger architectural question — flagged but probably out of scope.

2. Should we add a generalized middleware for idempotency that other mutation endpoints can opt into, vs hardcoding in the close handler? Closer to scope; ATLAS to weigh in.

3. Cost: Upstash Redis already in use, no incremental cost for SET NX EX. Postgres advisory lock — also free. Idempotency-key header pattern — small. None of this should hit the budget.

---

*Draft complete. Awaiting Pass 1 reviews from ATLAS, HELIOS, AEGIS.*
