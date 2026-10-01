# CC-STATER lane — status

**Written:** 2026-10-01 00:45 MDT (06:45 UTC)
**Worked against:** `origin/main` = `b0ada46` (fix(health): a class judged on being alive must read a row that can be a failure)
**Worktree / branch:** Claude Code cloud session. `claude/stater-scope` (scope + mockup) → `claude/stater-phase0` (fixes, stacked on scope)
**Hub at read time:** UW governor `outcome_resolver` 81 at 06:33 UTC (no Stater tab open, about 12/h)

## Why this lane exists
SPINE chartered CC-STATER (R-IV.618) to own Stater Swap, the hub's crypto surface.
- **Frontend:** `frontend/stater.*`.
- **Crypto backend:** `api/crypto_market.py`, `api/btc_signals.py`, `bias_filters/crypto_*`,
  `config/crypto_*`, `jobs/crypto_*`, `strategies/crypto_setups.py`, `strategies/btc_market_structure.py`,
  `services/read_only/crypto_*`, `hub_mcp/tools/crypto_*` and `utils/crypto_sessions.py`.

It inherits S-6M's ownership of `stater.*`. It never touches Agora files, `backend/signals/`,
`main.py`, schema or migrations, or positions and cash. It holds no exchange credentials and places
no orders.

## What this session did
1. **Scope (R-IV.618)** on `claude/stater-scope`:
   - `docs/stater/STATER-SCOPE-2026-10-01.md`;
   - the Phase 1 mockup on sample data, `docs/stater/mockups/stater-phase1-sample.html` (the
     principal has a private artifact copy);
   - the relay to SPINE.
2. **Phase 0 (R-IV.619)** on `claude/stater-phase0`, all six items in SPINE's order:
   - [x] **P0.1** GETs read stored rows; no recompute, no writes, no events. Bars are cached.
   - [x] **P0.2** BTC/ETH/SOL bars come from Coinbase Exchange public, with OKX as fallback. Zero UW.
   - [x] **P0.3** `/crypto/market` cache, fallbacks and CVD state are per symbol, with the full pair.
     The shape is unchanged.
   - [x] **P0.4** Honest readings: the session key, the tape stale limit, N/A instead of 0, and the
     dial respects `degraded`.
   - [x] **P0.5** `GET /api/crypto/signals`, a crypto-only feed; Stater reads it.
   - [x] **P0.6** The reset route is declared before `/{signal_id}`.
   - **Tests:** 35 backend tests (each failure-expecting check carries a positive control) and 10
     browser checks on fixtures. The same browser checks fail 6 times on `main`'s page.
   - **Relay to BUILD:** `docs/handoffs/RELAY_CC-STATER_to_CC-BUILD_2026-10-01_phase0.md`.
3. **UW drain, measured from the governor:** 1 UW call per `GET /crypto/state/BTC` (3 GETs moved
   the counter +3). That is 2,880 a day from one open tab via that route alone. After the merge,
   these paths make zero calls (tests). Re-take the snapshot after deploy.

## In flight
- Phase 1 waits for the principal's approval of the mockup.
- Phase 0 waits for SPINE's ruling, then BUILD's review and merge.
- Next items, not started:
  - the geo-blocked strategy engine (`crypto_setups.py` → `fapi.binance.com` HTTP 451);
  - the cycle engine's double count (two-sided vendor FIRING).

## Findings for other lanes (relayed as text; owners insert)
- **BUILD:**
  - The README ownership row for CC-STATER.
  - `uw_governor` `outcome_resolver` quota can drop after Phase 0 merges.
  - The full backend suite rewrites the tracked `data/watchlist.json` (a test side effect, also on
    `main`).
- **ABACUS:** the R-IV.420(e) Stater pin is done here (`v2.css?v=39`). Nothing for ABACUS to do.

## What the next CC-STATER session should do first
Read SPINE's ruling on Phase 0 and the principal's on the mockup. If Phase 0 has merged, take the
governor snapshot (`GET /api/uw/health/by_caller`, `outcome_resolver`) with a Stater tab open, to
confirm the drain is gone. Then start the geo-blocked strategy engine item.
