# Build Brief — A3 (Outcome Self-Scoring) + A4 (Committee-Review Logging)

**Workstream:** Sub-brief 2 · A3 + A4
**Master brief:** `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md` §4
**Phase 0 findings:** `docs/phase0-a3a4-findings.md`
**Locked decisions:** FWD_RETURN horizons = **T+1 and T+5** · **parallel-grade** model · fresh **`committee_passes`** table · single CHECK migration for all three new values.

---

## HARD RULES (do not violate)

- **No migration is RUN against prod, and nothing is deployed, without Nick's explicit greenlight relayed through the review chat.** Build the files; don't apply them.
- **No deploys/migration-runs during market hours** (Railway restart drops the hub ~1–3 min). After-close / weekend only.
- **Shadow-first.** The new resolvers and the committee row are purely additive — they must not alter any live scoring, trade-idea output, or anything Nick sees or trades.
- **IS-NULL guard mandatory** on every `signals.outcome_source` write (matches all four existing writers). The pre/post `outcome_source` distribution snapshot must show **`ACTUAL_TRADE` (2) and `BAR_WALK` (1,852) unchanged.**
- **Build → STOP at each phase gate → report to the review chat → wait.** Don't run ahead between phases.

---

## STEP 0 — Reconciliation (before any code)

1. **Read master brief §4.** Confirm it intends A3's `OPTIONS_PNL` and `FWD_RETURN` as **parallel grades** — a signal can hold an options grade and a forward-return grade *alongside* an existing bar-walk grade — not as mutually-exclusive replacements for the single `outcome_source` label. The design below assumes parallel. **If §4 contradicts this, STOP and report before building.**
2. **Migration application mechanism:** are numbered migrations **auto-run on deploy**, or applied manually? If auto-on-deploy, the migration files must NOT be merged/deployed until greenlit — because *merge = run*. Report which it is.
3. **Forward-return anchor:** confirm `signals` carries an entry/reference price + a signal-creation timestamp usable to anchor the forward window. If the reference price isn't on `signals`, report where it lives.

---
## PHASE 1 — Migrations (write files; DO NOT run)

Follow the existing numbered-migration convention (confirm the latest number — 016 was last referenced). All three are **additive / non-destructive**.

1. **Extend `outcome_source_valid` CHECK** on `signals` to additionally allow: `OPTIONS_PNL`, `FWD_RETURN`, `COMMITTEE_REVIEW`. (Only permits new values; touches no existing rows. This is the blocker Phase 0 found — deferred in migration 016.)
2. **Create `signal_forward_returns`** (A3's forward-return grades). Required fields — match house naming/types:
   - `signal_id` (FK → signals)
   - `horizon_days` (int: 1 or 5)
   - `reference_price` (numeric — signal's entry/anchor price)
   - `horizon_close_price` (numeric — UW bar close at the horizon)
   - `fwd_return_pct` (numeric — **direction-adjusted**, see Phase 2)
   - `computed_at` (timestamptz)
   - unique `(signal_id, horizon_days)`
3. **Create `committee_passes`** (A4's durable structured row). Required fields:
   - `id` (pk)
   - `ticker`
   - `pass_ts` (timestamptz)
   - `spot` (numeric)
   - `agent_reads` (JSONB — per-agent reads: TORO / URSA / PYTHIA / PYTHAGORAS / THALES / DAEDALUS)
   - `pivot_synthesis` (text or JSONB)
   - `conviction`
   - `entry` / `stop` / `target` / `invalidation`
   - `signal_id` (nullable FK → signals; set only when the pass maps to a specific signal)
   - `created_at` (timestamptz)

Report final DDL for all three at **Gate 1**.

→ **GATE 1 — migration files written + Step 0 answers. STOP. Nick greenlights the migration run.**

---
## PHASE 2 — A3 resolvers (after migrations greenlit + run; shadow)

Two new resolvers. Both write `signals.outcome_source` **only** under `WHERE outcome_source IS NULL`. Add an `A3_SHADOW_MODE`-style flag (mirror B2's `B2_SHADOW_MODE`) so the first pass can dry-run/log before writing, if that fits the existing pattern.

**2a. `OPTIONS_PNL` resolver**
- Read `signal_options_expressions WHERE b2_status = 'EXITED'`, join `signals.signal_id = signal_options_expressions.signal_id`.
- Pull `options_pnl, exit_trigger, max_profit, max_loss` — the grade **lives in this table; do not duplicate it.**
- Set `signals.outcome_source = 'OPTIONS_PNL'` (IS-NULL guard). The label is a pointer; the numbers stay in `signal_options_expressions`.

**2b. `FWD_RETURN` resolver (T+1 and T+5)**
- Fires at a **fixed calendar horizon**, NOT at target/stop touch — distinct from the bar-walk resolver (`jobs/outcome_resolver.py`). Keep separate; do not modify the bar-walk path.
- For each eligible signal, compute return at **T+1 and T+5 trading days** (skip weekends/holidays) using **UW bars (primary; yfinance fallback only — no Polygon/FMP)**:
  - `reference_price` = signal's entry/anchor price
  - `horizon_close` = UW daily close on the Nth trading day after entry
  - **Direction-adjusted:**
    - LONG: `fwd_return_pct = (horizon_close − reference_price) / reference_price`
    - SHORT: `fwd_return_pct = (reference_price − horizon_close) / reference_price`  *(negated)*
    - → a correct call is **positive regardless of direction.**
- **Guard:** if the horizon bar doesn't exist yet (signal too recent), **skip and retry later** — forward-accumulating, like B2. Never fabricate a close.
- Write one row per `(signal_id, horizon_days)` into `signal_forward_returns`. Set `signals.outcome_source = 'FWD_RETURN'` (IS-NULL guard) — secondary label; the table rows are the truth.

**Verification at Gate 2 (report numbers):**
- Pre/post `SELECT outcome_source, COUNT(*) … GROUP BY 1` — `ACTUAL_TRADE` and `BAR_WALK` unchanged.
- Spot-check one LONG and one SHORT signal — confirm `fwd_return_pct` sign is direction-correct.
- Spot-check one `OPTIONS_PNL` label against its exited expression row.

→ **GATE 2 — A3 built + shadow-run + verification numbers. STOP. Report to review chat.**

---
## PHASE 3 — A4 committee logging (after A3 cleared)

- **Extend the existing handler** at `POST /api/committee/results` (the VPS bridge already calls it; it currently writes `signals.committee_data` JSONB). Add a server-side write of a structured row to `committee_passes`. **Preserve the existing `committee_data` JSONB write — add alongside, do not replace.**
- For the in-place handler edit: read the exact current code, construct the diff, and **report the proposed diff at Gate 3 before it touches anything that deploys.**
- Set `signals.outcome_source = 'COMMITTEE_REVIEW'` **only** when the pass maps to a specific `signal_id`, under the IS-NULL guard. The `committee_passes` row is **always** written regardless of signal linkage — that row is the source of truth.
- **Orphan cleanup:** `committee_recommendations` exists in code but its table was never created (silently failing). Confirm nothing live depends on it; then either remove the dead path or leave it inert — report which, and confirm `committee_passes` supersedes it.
- **AEGIS (light, bounded):** this extends an already auth-gated surface — no new endpoint, no new auth boundary. Confirm: input validated before the structured write, no secrets/tokens in any new log line, write stays inside the existing auth boundary. Report.
- **Olympus impact: NONE** (passive capture — committee skills don't call the API directly; the VPS bridge is the intermediary). No committee regression pass required. **If any part of the build would require a skill-side call, STOP** — that changes the impact assessment.

**Verification at Gate 3 (report):**
- Trigger/await one committee pass → confirm a `committee_passes` row is written **and** `signals.committee_data` JSONB is still written (existing behavior intact).
- Confirm `outcome_source` distribution still shows `ACTUAL_TRADE` / `BAR_WALK` unchanged.

→ **GATE 3 — A4 built + verified + AEGIS note + orphan disposition. STOP. Report to review chat.**

---

## Sequencing summary

Step 0 → **Gate 1** (migration files written) → [Nick greenlights migration run] → Phase 2 A3 (shadow) → **Gate 2** → Phase 3 A4 → **Gate 3**. No prod-affecting enablement beyond shadow without a further explicit greenlight.
