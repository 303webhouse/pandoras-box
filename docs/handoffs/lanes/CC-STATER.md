# CC-STATER lane — status

**Written:** 2026-10-01 10:45 MDT (16:45 UTC)
**Worked against:** `origin/main` = `a338cce` (fix(positions): an option expired at the close now ends that evening…)
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`, on `claude/stater-*` branches
only (R-IV.628). It inherited the lane from the Claude Code cloud session, which ran out of credits.
**Hub at read time:** prod runs `a338cce`, which includes BUILD's caller tags, since 15:31 UTC.

## Why this lane exists
SPINE chartered CC-STATER (R-IV.618) to own Stater Swap, the hub's crypto surface.
- **Frontend:** `frontend/stater.*`.
- **Crypto backend:** `api/crypto_market.py`, `api/btc_signals.py`, `bias_filters/crypto_*`,
  `config/crypto_*`, `jobs/crypto_*`, `strategies/crypto_setups.py`, `strategies/btc_market_structure.py`,
  `services/read_only/crypto_*`, `hub_mcp/tools/crypto_*` and `utils/crypto_sessions.py`.

It inherits S-6M's ownership of `stater.*`. It never touches Agora files, `backend/signals/`,
`main.py`, schema or migrations, or positions and cash. It holds no exchange credentials and places
no orders.

**On the principal's PC (R-IV.628(b)):**
- Never check out, commit to or push `main`; BUILD merges.
- The database login is read-only.
- No Railway CLI, no deploys, no environment-variable changes.

## Branches
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-p0-market` | New. Cut from `main` `a338cce`. `df7ce28` (P0.3 cherry-pick) + `5b45daa` (fallback TTLs). | **Yes, merge first.** |
| `claude/stater-phase0` | All six Phase 0 items, plus `7c3295e` (the same TTL commit) and `0ecdb0d` (main merged in, caller-tag conflict resolved). 42 tests. | **Yes, after p0-market.** It still waits on SPINE's Phase 0 ruling. |
| `claude/stater-scope` | Scope doc + Phase 1 mockup (docs only). Contained in phase0. | It merges along with phase0. |
| `s6-stater-build` | Older S-6 cockpit work, from another session. Not touched. | Not this lane's to merge. |

## What was done for R-IV.623 (executed under R-IV.628)
1. **Done: the per-symbol fallback store with TTLs** (`5b45daa`): 120 s for prices, CVD and order
   flow, 900 s for funding. Past the limit the value is null and `errors` says "no fresh value". The shape is unchanged.
   Also done: the vendor-format audit (in the commit message and the relay) and 7 tests with positive
   controls. Shipped alone on `p0-market` and cherry-picked onto phase0.
   - **Open:** I did not have BUILD's repro text, so the repro test is reconstructed from R-IV.623.
     BUILD should compare it with theirs.
2. **Done: the relay** `docs/handoffs/RELAY_CC-STATER_to_CC-ABACUS_CC-BUILD_2026-10-01_market-ttl.md`.
   - The shape is unchanged. The bot and Stater handle null.
   - **Agora does not crash, but its client-side last-good copy keeps showing an expired price.** That is ABACUS's decision.
3. **Partly done: the measurement.** The caller tag is on `main` and deployed.
   - **Before (passive, no Stater tab open):** since the 15:31 UTC deploy, about 68 min, the counts are
     `crypto_bars_tape_health` 15 (about 13/h), `crypto_bars_regime` 3, `crypto_bars_state_api` 0, and
     `crypto_bars_outcome_resolver` 0. The old `outcome_resolver` row holds 213, all from before the rename.
   - **Still needed:** a reading with a Stater tab open. Either the principal opens Stater for 5
     minutes, or SPINE grants a budget of about 3 UW calls for 3 `GET /crypto/state/BTC`. BUILD's own
     before-figure is on record in `51732bd`: 4 calls per 30 s with a tab open.
   - **After:** the same reading once phase0 is deployed. Expected: `crypto_bars_state_api` at 0 with a tab open.

## Findings for other lanes (relayed as text; the owners insert)
- **ABACUS:** `app.js` `cryptoMarketLastGood` has no time limit, so it masks the server's nulls. A null CVD direction shows as `NEUTRAL`.
- **BUILD:**
  - `test_frontend_routes.py` hangs when run after the crypto tests in one process. This happens on `main` too.
  - The `polygon-health` route test fails on `main`.
  - Still open from before: the README ownership row and the `data/watchlist.json` test side effect.
- **SPINE (this lane, needs a ruling):** `btc_market_structure._fetch_cvd` reads `cvd_analysis`,
  which `/crypto/market` has never returned. So that strategy's CVD gate has always scored 0.
  Fixing it changes signal scoring, so it waits for a ruling.
- **Matrix:** HYPE is now listed on Binance spot (verified from the US, not yet from Railway).

## What the next CC-STATER session should do first
1. Check whether BUILD merged `p0-market`, then phase0.
2. Take the Stater-tab-open measurement (before, or after if phase0 has deployed) from
   `GET /api/uw/health/by_caller`.
3. Then the queued items: the geo-blocked strategy engine (`crypto_setups.py` → `fapi.binance.com`
   451), the cycle engine's double count, and the `cvd_analysis` gate if SPINE rules on it.
