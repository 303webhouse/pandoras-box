# CC-STATER lane â€” status

**Written:** 2026-10-01 11:51 MDT (17:51 UTC); first written 10:45 MDT for R-IV.628, updated for R-IV.637
**Worked against:** `origin/main` = `a338cce` (fix(positions): an option expired at the close now ends that eveningâ€¦)
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
3. **Before: done. After: waits for BUILD's deploy of phase0.** The caller tag is on `main` and deployed.
   - **Before, passive (no Stater tab open):** since the 15:31 UTC deploy, about 68 min, the counts are
     `crypto_bars_tape_health` 15 (about 13/h), `crypto_bars_regime` 3, `crypto_bars_state_api` 0, and
     `crypto_bars_outcome_resolver` 0. The old `outcome_resolver` row holds 213, all from before the rename.
   - **Before, the probe (R-IV.637(b), budget 5 UW calls, prod `478997e`, 17:46â€“17:49 UTC):** one request
     to each endpoint a Stater tab polls on `main`, sent with no session and no key, the way a tab sends them.
     **Spent: 1 UW call**, `crypto_bars_state_api` +1, from `GET /crypto/state/BTC`. Every other crypto tag stayed flat.

     | Endpoint | HTTP | UW by caller tag | Writes |
     |---|---|---|---|
     | `/crypto/regime`, `/crypto/clock` | 200 | 0 | none |
     | `/analytics/risk-budget`, `/trade-ideas?limit=50` | 401 | 0 | none |
     | `/crypto/market` Ã— 6 coins | 200, **about 8.1 s each** | 0 | none |
     | `/crypto/cycle-extremes` | 200 | 0 | **6 rows in `crypto_cycle_log`** (see below) |
     | `/crypto/state/BTC` | 200 | **1** (`crypto_bars_state_api`) | none |
     | `/crypto/tape-health` | **401** | 0 | none, because it was refused |

     - **The rows written:** one per coin, at `computed_at` (from the response)
       BTC `17:48:55.346745`, ETH `17:48:55.860674`, SOL `17:48:56.233770`, HYPE `17:48:56.614450`,
       ZEC `17:48:56.988100`, FARTCOIN `17:48:57.357746` (UTC, 2026-10-01).
       - **Probably 6 more, unconfirmed:** an earlier pass of the probe script timed out client-side at
         30 s. Its 49 s run time fits two 8-second `/market` calls followed by `cycle-extremes`. So a second
         set of 6 rows was probably written around 17:47:50â€“17:48:25 UTC.
       - **Row ids not read:** BUILD's read-only login (R-IV.627) does not exist yet. The Postgres
         tool on this PC logs in as `postgres` (the superuser), so under R-IV.628(b)2 it was not used.
         The rows can be found by `(symbol, computed_at)`. Nothing was removed.
     - **Signals written: none.** `crypto_cvd_engine` persisted 0 â†’ 0 (`/health`). Only `tape-health` fires
       CVD events, and it returned 401.
     - **What a real (logged-in) tab adds:** `tape-health` needs a session. A logged-in tab gets it
       computed, which spends `crypto_bars_tape_health` for BTC/ETH/SOL. That fits BUILD's 4 calls
       per 30 s (`51732bd`): 1 from state plus about 3 from tape-health. This was inferred, not measured, because
       no key or session was used.
     - **A side finding (for the routing branch):** every `/market` request takes about 8.1 s, which is the
       8.0 s venue timeout. One venue hangs on every call from Railway.
     - **Budget accounting:** in the first pass the script's guard counted all tags and stopped on 18
       `option_contracts` calls, which come from an unrelated hub job. The rerun counted crypto tags only.
       The total crypto spend for the whole probe was 1.
   - **After:** the same probe once phase0 is deployed. Expected: `crypto_bars_state_api` 0, no
     `crypto_cycle_log` rows from a GET, and (with a session) no `tape-health` spend from a GET.

## Findings for other lanes (relayed as text; the owners insert)
- **ABACUS:** `app.js` `cryptoMarketLastGood` has no time limit, so it masks the server's nulls. A null CVD direction shows as `NEUTRAL`.
- **BUILD:**
  - `test_frontend_routes.py` hangs when run after the crypto tests in one process. This happens on `main` too.
  - The `polygon-health` route test fails on `main`.
  - Still open from before: the README ownership row and the `data/watchlist.json` test side effect.
## Known defects (left in place by ruling)
- **`btc_market_structure._fetch_cvd` reads `cvd_analysis`**, a key `/crypto/market` has never
  returned. So the CVD leg has scored 0 ("CVD neutral") since the strategy was written, and the
  strategy's whole record is a record without CVD. **Leave it (R-IV.637(c)).** A fix comes later only as a
  shadow score logged next to the live one. Only QUERY's comparison can promote it, because changing
  how a signal scores makes a new signal, not a repaired one.

## Vendor matrix (R-IV.637(d))
- **Recorded on phase0** in `config/crypto_symbol_matrix.py`, with the evidence in
  `docs/strategy-reviews/stater-swap-redesign/symbol-capability-matrix.md`:
  - HYPE's `binance_spot_orderbook` is now LIVE but marked `not_routed`;
  - FARTCOIN's OKX-spot fallback is now UNAVAILABLE (`51001`), and its Binance spot entry stays UNAVAILABLE (`-1121`).
- **Nothing reads those cells**, so routing is unchanged.
- **Routing changes come later, on their own branch, after BUILD merges both:** stop asking venues that
  don't list a coin, use HYPE's Binance spot (after a check from Railway), and fix the 8 s `/market` stall.

## State: holding for BUILD's merge (R-IV.637(e))
Nothing more goes onto `p0-market` or phase0 unless BUILD's review asks for it.

## What the next CC-STATER session should do first
1. Check whether BUILD merged `p0-market`, then phase0, and whether it deployed.
2. After the deploy, take the "after" probe: the same endpoints, the same method, the same 5-call cap.
3. Then, each on its own branch from `main`: the vendor routing changes, the geo-blocked strategy
   engine (`crypto_setups.py` â†’ `fapi.binance.com` 451), and the cycle engine's double count.
