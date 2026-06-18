# Brief — Retire the legacy `open_positions` table

**Date:** 2026-06-17 · **Bucket:** cleanup / migration · **Scope:** `open_positions` only (siblings `positions` / `options_positions` noted but out of scope)

## Decision context
Nick (2026-06-17): `open_positions` is deprecated as a source of truth. Canonical open-position state is `unified_positions`, accessed via the Pandora MCP (`hub_get_positions` → hub API → `unified_positions`). This brief scopes the work to physically remove the table cleanly. The table has been **write-silent since 2026-03-09** (last `last_updated`), and is **not read by the live UI or MCP**.

## Headline: the job is much smaller than "8 files"
The original deprecation note listed 8 backend files referencing `open_positions`. On audit, **7 of those are false positives** — a same-named local variable, a dict key, a function/endpoint *name*, or a docstring. **The reads are already migrated to `unified_positions`.** Only **two real touchpoints** remain:

1. **Write endpoints in `backend/api/portfolio.py`** (sync/create/close) — still `INSERT/UPDATE open_positions`.
2. **Startup DDL in `backend/database/postgres_client.py:800`** — `CREATE TABLE IF NOT EXISTS open_positions` (+ ALTERs/indexes, lines 828–841). This **re-creates the table on every boot**, so it must be removed or any DROP is undone on next deploy.

## File-by-file disposition

| File / line | Reference | Real table? | Action |
|---|---|---|---|
| `api/portfolio.py:165` `GET /positions` | `SELECT FROM unified_positions` + `_v2_to_legacy_dict` | **No — already migrated** | none |
| `api/portfolio.py:201` `POST /positions/sync` | SELECT/UPDATE/INSERT `open_positions` (208,213,254,272,295) | **Yes (write)** | reroute or delete (see open question) |
| `api/portfolio.py:361` `POST /positions` (create) | SELECT 374, INSERT 392 | **Yes (write)** | reroute or delete |
| `api/portfolio.py:424` `POST /positions/close` | SELECT 444, UPDATE 506 | **Yes (write)** | reroute or delete |
| `database/postgres_client.py:800` | `CREATE TABLE IF NOT EXISTS open_positions` + ALTER/INDEX | **Yes (DDL)** | **delete** (else DROP is resurrected on deploy) |
| `database/postgres_client.py:1526` `get_open_positions()` | `SELECT FROM unified_positions` | **No — already migrated** | optional rename only |
| `api/positions.py:746` | calls `get_open_positions()` (→ unified) | No | none |
| `discord_bridge/bot.py:1853` | `GET /api/portfolio/positions` (→ unified) | No | none |
| `discord_bridge/bot.py` (2723–3205) | `"open_positions"` import-payload **dict keys** | No | none |
| `analytics/api.py:1487` | local var `open_positions` reading `FROM trades` | No | none |
| `analytics/portfolio_monitor.py:52` | `_load_open_positions()` reads `trades`/`positions` | No (different table) | none |
| `analytics/robinhood_parser.py:675,693` | `"open_positions"` dict key | No | none |

## Open question — RESOLVED 2026-06-17 (VPS audit)
**Q: Does anything still write the legacy table via `POST /api/portfolio/positions/sync|close`?**
**A: No live, successful writer exists. The endpoints are safe to retire.**

Callers found on the VPS, all dead or unused:
- `scripts/yfinance_price_updater.py` (reads `/portfolio/positions` → unified ✓; POSTs prices to `/portfolio/positions/sync` → legacy table). **Dead since 2026-02-25** — openclaw `jobs.json` shows `yfinance-price-updater enabled=False, lastRun=2026-02-25`; prices cache `data/yfinance_prices.json` frozen at 2026-02-25; no `/var/log/yfinance_prices.log`. (A system-crontab line for it exists but produces no log/cache output → effectively dormant.)
- `scripts/ibkr_poller.py`, `scripts/ibkr_quotes.py` — **commented out** in crontab ("DISABLED until ibeam is authenticated") and `enabled=False` in jobs.json since 2026-02-25.
- Manual Pivot RH-screenshot flow (`PORTFOLIO.md`, `RH_SCREENSHOT_RULES.md`) posts to these endpoints — **Nick confirmed he does not use it**; he never enters positions via Discord/Pivot.

**Hub pricing is unaffected by this cleanup.** `unified_positions` is priced by a separate live (Railway/v2) path — `price_updated_at` is fresh as of 2026-06-17 20:47 UTC (20/30 open rows priced). The dead VPS yfinance job wrote the *legacy* table, which the hub never reads, so it was redundant even when alive.

**Implication for the cleanup:** reroute-vs-delete is now a free choice. Simplest safe path: **delete** the 3 legacy write endpoints, **remove** the dormant yfinance crontab line + its legacy `/positions/sync` POST (the script's price refresh is already superseded by the v2 MTM), and **remove** the startup DDL. Keep the `_v2_to_legacy_dict` read mapper (still used by `GET /positions`).

⚠️ Latent bug noted in passing: if anyone re-enables `yfinance_price_updater.py`, it currently pushes prices into the dead `open_positions` table (a no-op for the hub). If VPS-side pricing is ever wanted again, repoint it at `/v2/positions/mark-to-market`. Currently redundant with the live Railway MTM — leave off.

## Recommended approach (lowest risk)
Keep the public API contract, swap the table underneath — so Pivot needs no change even if still wired to it:

1. **Reroute the 3 write endpoints** in `portfolio.py` (`sync_positions`, `create_position`, `close_position`) to operate on `unified_positions` — ideally by **delegating to the existing v2 handlers** (`unified_positions.py` create/close) rather than rewriting the legacy schema logic. Note the schema translation: legacy `position_type/spread_type/is_active` → v2 `structure/status`; the `_v2_to_legacy_dict` mapper (portfolio.py:90) already encodes the inverse and is a reference.
2. **Remove** the `CREATE TABLE IF NOT EXISTS open_positions` block + ALTER/INDEX (`postgres_client.py:800–841`).
3. **(Optional)** rename `get_open_positions()` → `get_open_unified_positions()` and drop the misleading endpoint comments, to kill the naming debt.
4. **Backup + drop:** `pg_dump` the (stale) `open_positions` table to an archive, then `DROP TABLE open_positions;` as a migration. Verify no FK references first.
5. Update tests that assert the legacy endpoints (`tests/test_auth.py:140–145`, `tests/test_positions.py`, `tests/test_frontend_routes.py`) and the Pivot docs (`RH_SCREENSHOT_RULES.md`) to the v2 contract.

## Risks / notes
- **Resurrection trap:** skipping step 2 means the DROP silently comes back on the next Railway deploy. This is the #1 gotcha.
- **Pivot breakage:** skipping the open-question verification risks silently breaking screenshot sync if Pivot still posts to the legacy endpoints. Reroute-don't-delete (step 1) de-risks this entirely.
- **Siblings:** `positions` and `options_positions` are the same class of dead/dying tables (see `api/options_positions.py:476` `sync-from-db`, `postgres_client.py` options fns, `portfolio_monitor.py` `positions` fallback). Out of scope here but should ride the same cleanup wave — file follow-ups.
- **Safety rule:** DROP is a destructive prod action — do it behind a reviewed migration with the dump in hand, never ad hoc.

## Definition of done
Legacy write endpoints write `unified_positions` (or are removed), startup no longer recreates the table, the table is dumped + dropped via migration, tests + Pivot docs updated, and `git grep open_positions` returns only `unified_positions`-backed names or comments.
