# AEGIS Pre-Production Override Log

Running record of every pre-production override invoked per `skills/_shared/TITANS_RULES.md § Veto Rights`.

**Purpose:** When Nick invokes the pre-production override on an AEGIS data-API credential flag, the flag is recorded here — the override is acknowledgment, not dismissal. Every entry feeds into the comprehensive security review backlog.

**Override eligibility:** Data-API credentials only (UW API key, alternative data sources). Broker/trading API credentials (Robinhood, IBKR, Fidelity, Breakout Prop) are NOT eligible regardless of phase.

**Override expiry triggers:**
1. Any broker trading API is connected to the hub.
2. Nick formally schedules the comprehensive security review.

When either trigger fires, all overrides expire and the recorded flags become active review items.

---

## Override entries

### 2026-07-24 — AEGIS Coordinated Pass (W1-4) — **CLOSED**
- **Flag:** Hardcoded plaintext Postgres credential in `scripts/reconcile_rh.py` `DB_URL` constant. First raised 2026-07-16 (SOXS/XLF reconciliation micro-brief) while the file was untracked; the file was later committed to `origin/main` via `66fb98c` (2026-07-19), putting the live credential on origin. Quarantined-by-discipline 2026-07-23 (Fable Option 2 — AEGIS/W1-4 owns the file + commit + rotation).
- **File:line:** `scripts/reconcile_rh.py:16` (the `DB_URL = "postgres://…"` constant), committed in `66fb98c`.
- **Class:** Infrastructure DB credential (not a data-API deferral — this is a *resolved* finding, recorded here as the security-relevant-action audit trail).
- **Resolution (this pass):**
  1. Neutralized in HEAD (`ff1c94c`) — hardcoded DSN removed; resolved at connect time from `DATABASE_URL` env / `.mcp.json` (credential-with-`@` count 1 → 0, verified).
  2. Postgres password rotated by Nick (Runbook A) — `ALTER USER` + all live consumers updated (backend `DB_PASSWORD` literal, local `.mcp.json`).
  3. Kill-proof verified — old committed string → **REJECTED (auth-failed)**; new credential → **ACCEPTED** (values never displayed).
  4. History rewrite ruled OUT (private repo + rotation renders the committed string worthless; filter-repo risk > value).
- **Status:** **CLOSED 2026-07-24** — the committed string on origin is now worthless; no residual review item.
- **Nick acknowledgment:** AEGIS Coordinated Pass session 2026-07-24 (Runbook A completed; Fable G0 PASS + veto-lift grade).

<!-- Entry format:
### YYYY-MM-DD — [build name / brief ID]
- **Flag:** [original AEGIS finding]
- **File:line:** [where the flag fires]
- **Override conditions at invocation:** [broker connected? security review scheduled?]
- **Nick written acknowledgment:** [link to chat transcript or commit comment]
- **Resolution plan:** [what gets fixed in the comprehensive security review]
-->
