# RH MCP Rebuild — Handoff to the Titans

**Date:** 2026-05-27
**Trigger:** Robinhood released an MCP server for AI agents on 2026-05-27.
The position/portfolio tracking layer is being redesigned around it,
superseding the manual-CSV-sync flow shipped 2026-05-26.

This is a short orientation doc, not a brief. Its purpose is to make sure
the Titans don't re-discover what was already learned in the last 24 hours
of CSV-sync work, and to flag the known gaps the MCP integration will
inherit responsibility for.

---

## Current state of `unified_positions` (after 2026-05-26 sync)

Account `ROBINHOOD`, status `OPEN`: **12 rows**, all reconciled against
broker reality as of 2026-05-26 evening (sync_run_id
`aaad7835-7f8e-4083-8871-1d396cf88e16`, see `position_sync_audit` for the
full INSERT/UPDATE trail).

| ticker | structure          | qty | entry  | long / short | expiry  |
|--------|--------------------|-----|--------|--------------|---------|
| IBIT   | put_debit_spread   |   3 | 0.2267 | 42 / 39      | 5/29/26 |
| CF     | call_debit_spread  |   1 | 1.9800 | 140 / 150    | 6/18/26 |
| COUR   | long_put           |   3 | 0.1000 | NULL / NULL  | 6/18/26 |
| HYG    | put_debit_spread   |   4 | 0.6300 | 76 / 74      | 6/18/26 |
| IGV    | put_debit_spread   |   3 | 0.7967 | 77 / 72      | 6/18/26 |
| TSLA   | put_debit_spread   |   6 | 0.2417 | 240 / 230    | 6/18/26 |
| WEAT   | long_call          |   8 | 0.1800 | NULL / NULL  | 6/18/26 |
| XLY    | put_debit_spread   |   4 | 0.8500 | 100 / 90     | 6/18/26 |
| IBIT   | put_debit_spread   |   2 | 0.7100 | 40 / 36      | 7/17/26 |
| UVXY   | call_debit_spread  |   3 | 0.6000 | 40 / 45      | 7/17/26 |
| XLE    | call_debit_spread  |   2 | 0.5900 | 65 / 70      | 7/17/26 |
| XLF    | put_debit_spread   |   5 | 0.3060 | 48 / 45      | 7/17/26 |

The MCP integration starts from this state. Anything written by the MCP
should produce the same set when reconciled against broker — use
`scripts/sync_rh_csv.py` (dry-run) as the regression check.

---

## What the CSV sync script does (so the MCP can replace it cleanly)

`scripts/sync_rh_csv.py` is a chronological walker:

1. Parse RH activity CSVs (one or many; date ranges must not overlap).
2. Match BTO/STO pairs into vertical spreads; collapse `MULTI_LEG_HINTS`
   tickers (currently just HYG) into a compressed 2-leg structure with the
   middle leg preserved in `legs` JSONB.
3. Walk OEXP expirations and BTC/STC closes to reduce open quantities.
4. Filter out positions whose expiry is past `today` (the existing
   `_sweep_expired_positions` in `backend/api/unified_positions.py` handles
   them).
5. Diff against `unified_positions` rows (`account='ROBINHOOD'`, `status='OPEN'`).
6. Emit INSERT / UPDATE / CLOSE actions inside a single transaction with
   per-operation audit logging.

The MCP integration removes steps 1–4 (live broker state replaces the
parser). Steps 5–6 (diff + audit-logged apply) likely stay — they're the
"write to canonical DB" contract.

---

## Schema contracts the MCP design should honor

These were validated end-to-end by the CSV sync and are baked into
downstream readers (`hub_get_positions`, `/v2/positions/summary`, committee
context, the cash-balance reconciliation, the price-updater):

- `position_id` is `POS_<TICKER>_<YYYYMMDD>_<6HEX>` (unique). The CSV sync
  derives the hex from a sha256 of the position key to avoid collisions for
  multiple positions opened the same day for the same ticker (e.g., two
  IBIT spreads both opened 5/22). The original API convention was a
  wall-clock timestamp; the hash variant is back-compatible.
- `account` is uppercased: `ROBINHOOD`, `FIDELITY_ROTH`, etc.
- `structure` uses `*_debit_spread` / `*_credit_spread` / `long_call` /
  `long_put` (canonical). Aliases like `bull_call_spread` / `bear_put_spread`
  exist in older rows and **are normalized on read** in the sync script via
  `STRUCTURE_ALIASES`. If the MCP writes new rows, it should pick the
  canonical form.
- `entry_price` is **always positive**. Credit vs debit semantics are derived
  from `structure`, not from sign (per Brief 05b — `ABS()` enforced).
- `cost_basis = abs(entry_price) * quantity * 100` for options; `* 1` for
  stock.
- **Naked single-leg long options** (`long_call`, `long_put`) write
  `long_strike = NULL` and `short_strike = NULL` to match the existing
  convention. The actual strike lives in `legs` JSONB (CSV sync starts
  populating this on new INSERTs; COUR + WEAT existing rows still have NULL
  legs). The price-updater limitation that motivated NULL strikes is
  documented in PROJECT_RULES.md "unified_positions Schema Limitation".
- **Multi-leg structures** (currently HYG's 3-leg broken-wing put ratio)
  use the 2-leg approximation in `long_strike` / `short_strike` and put the
  full leg set in `legs` JSONB. The MCP can lift this if it wants — three
  separate rows linked by a group ID was the alternative — but the existing
  HYG row is the canonical example to preserve / migrate.

---

## Known gaps inherited by the MCP integration

1. **Hub P&L overstates spread losses.** `hub_get_positions` (or a
   downstream calc reading from it) reports losses on debit spreads that
   exceed mathematically-possible max loss. Observed on XLY 6/18 100/90 ×4
   (max loss bounded by $340 total debit, hub reports larger). One plausible
   cause — DB had wrong qty (× 2) — was just fixed by the sync. Re-verify
   after MCP integration. If the bug persists, root cause is in the calc
   layer (likely summing per-leg M2M loss without netting the short leg's
   credit) — not in DB state. Memory: `[[hub-pnl-max-loss-bug]]`.

2. **VPS committee context still reads `docs/open-positions.md`.**
   `scripts/vps_deploy/patch_tier3_tier4.py` (line ~540) and
   `scripts/vps_deploy/patch_context_and_pythia.py` (lines 24, 35, 49) inject
   the markdown file content into TORO / URSA / PYTHIA / PIVOT prompts via
   `sync_trading_docs.sh`. The file has a deprecation header pointing at
   `hub_get_positions`, but until the VPS scripts switch over, the committee
   sees stale narrative (currently dated 2026-04-15). The MCP integration
   should bundle the VPS-side switch — committee should read live state, not
   a markdown snapshot.

3. **Naked single-leg strike backfill.** Existing COUR / WEAT rows have
   `long_strike = NULL` and no `legs` JSONB. The price-updater therefore
   can't price them (PROJECT_RULES.md "Naked single-leg option pricing gap").
   The CSV sync writes new naked-long rows with strike-bearing `legs` JSONB,
   but the existing two rows weren't backfilled. The MCP integration is the
   natural place to either backfill, or fix the price-updater to consult
   `legs` JSONB as a fallback.

4. **Multi-strike close handler is naive.** The CSV walker warns and skips
   close transactions where one STC strike pairs against multiple BTC strikes
   (e.g., closing two verticals on the same day that share a long leg). Only
   seen in already-expired data (IBIT 4/17) so the expiry filter masks it,
   but a strict implementation should allocate STC qty proportionally to BTC
   strikes. The MCP avoids this entirely by reading live state instead of
   replaying transactions.

5. **Cash-balance + closed-positions reconciliation are explicitly out of
   scope** for the CSV sync. `account_balances.cash` and `closed_positions`
   were left untouched. The MCP integration is the right time to wire these
   in, since live broker state has authoritative cash and lot-level realized
   P&L.

---

## Useful artifacts for the rebuild

- **Schema:** `migrations/010_unified_positions.sql` + later ALTERs in
  `backend/database/postgres_client.py` (the truth, since the API was
  patched after the migration).
- **API writer:** `backend/api/unified_positions.py` — `create_position`,
  `update_position`, `close_position`, the cash-delta logic, the
  weighted-avg-on-add path. The MCP writer should produce the same DB shape
  these endpoints do.
- **Reader:** `backend/hub_mcp/tools/positions.py` — the `hub_get_positions`
  MCP tool that the committee uses. Probably needs to keep the same response
  envelope so committee skills don't break.
- **Sync script (this brief):** `scripts/sync_rh_csv.py` — keep it as a
  manual fallback / regression check for the MCP integration.
- **Audit table:** `position_sync_audit` (migration 015) — generic enough to
  log MCP-driven writes too if the design wants a unified audit trail.
- **Backups:** `backups/unified_positions_pre_sync_*.json` (gitignored) —
  pre-sync snapshot if rollback ever needed.

---

## What this doc is not

Not a design. The Titans own the architecture decisions (which MCP tools to
expose, how to handle the polling cadence, how to model multi-broker, how
to bridge from the manual CSV path to the live MCP without a flag day, how
the committee skills' read patterns adapt). This is just the state of play
in `unified_positions` and the gaps the next team should be aware of.
