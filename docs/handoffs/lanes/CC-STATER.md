# CC-STATER lane — status

**Written:** 2026-10-01 00:20 MDT (06:20 UTC)
**Worked against:** `origin/main` = `b0ada46` (fix(health): a class judged on being alive must read a row that can be a failure)
**Worktree / branch:** Claude Code cloud session; `claude/stater-scope` (scope + mockup) and `claude/stater-phase0` (fixes)
**Hub at read time:** UW governor `by_caller` total 489, `outcome_resolver` 75 (2026-10-01 05:59 UTC)

## Why this lane exists
SPINE chartered CC-STATER (R-IV.618) to own Stater Swap, the hub's crypto surface.
- **Frontend:** `frontend/stater.*`.
- **Crypto backend:** `api/crypto_market.py`, `api/btc_signals.py`, `bias_filters/crypto_*`,
  `config/crypto_*`, `jobs/crypto_*`, `strategies/crypto_setups.py`, `strategies/btc_market_structure.py`,
  `services/read_only/crypto_*`, `hub_mcp/tools/crypto_*` and `utils/crypto_sessions.py`.

It inherits the earlier S-6M (Stater mobile) lane's ownership of `stater.*`. It never touches Agora
files, `backend/signals/`, `backend/main.py`, schema or migrations, or anything about positions or
cash. It holds no exchange credentials and places no orders.

## What this session did
- Read Stater end to end with three read-only scans of `origin/main` and wrote the scope:
  `docs/stater/STATER-SCOPE-2026-10-01.md`.
- Built the Phase 1 mockup on generated sample data: `docs/stater/mockups/stater-phase1-sample.html`.
  It fetches nothing, and every panel is marked SAMPLE. The principal has a private artifact copy.
- Wrote the relay to SPINE: `docs/handoffs/RELAY_CC-STATER_to_SPINE_2026-10-01.md`.
- Started Phase 0 (R-IV.619) on `claude/stater-phase0`. That branch carries its own copy of this
  file with progress.

## In flight
- Phase 1 waits for the principal's approval of the mockup.
- Phase 0 is in progress on `claude/stater-phase0`.

## Findings for other lanes (relayed as text; owners insert)
- **BUILD:**
  - Add a CC-STATER row to the `docs/handoffs/lanes/README.md` ownership table.
  - Until Phase 0 merges, an open Stater tab spends UW calls and writes log rows on every 30 s poll.
- **ABACUS:** the R-IV.420(e) Stater pin/dot relay is now CC-STATER's, so there is nothing for
  ABACUS to do.

## What the next CC-STATER session should do first
Read SPINE's ruling on the mockup, if one has arrived. Then continue Phase 0 on
`claude/stater-phase0` from the first unchecked item in that branch's copy of this file.
