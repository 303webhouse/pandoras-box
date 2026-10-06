# CC-STATER lane — status

**Written:** 2026-10-06 14:05 MDT (20:05 UTC)
**Worked against:** `origin/main` = `ac885f4` (docs(relay): CC-BUILD to CC-STATER — routing merged…)
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`, on `claude/stater-perps` (cut from `origin/main` `ac885f4`).
**Hub at read time:** prod `2b5150e` (routing merge `ffcc6e9` is an ancestor), `status: healthy`, process started 17:47:20 UTC. Proxy flag false.

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

## R-IV.663(a) — 658 accepted
Perps work was held uncommitted rather than riding the routing merge. Coinalyze refuses over
budget instead of sleeping. Hyperliquid weights are capped. New fields carry venue and age and
null past Phase 0 TTLs. Basis does not call `fapi.binance.com`. The matrix was dated from
Railway, with `predictedFundings` marked UNVERIFIED. Robinhood is noted below.

## (b) Re-time, production, 2026-10-06 20:02 UTC (14:02 MDT)

| Endpoint | HTTP | elapsed | vs 16:53 UTC |
|---|---|---|---|
| `/crypto/market?symbol=BTC` | 200 | **0.515 s** | was 8.10 s |
| `/crypto/state/BTC` | 200 | **1.76 s** | was 11.79 s |

`prices.perps.source=okx`, `binance_perp_proxy_enabled=false`, binance perp null, no `derivatives`
key yet (this branch is not on prod). Matches BUILD's 0.22–0.56 s market range.

## (c) OKX correction
`pick()` prefers a fresh non-OKX reading. If only OKX is answering, it keeps that reading
labelled `venue=okx`. Basis does the same: Hyperliquid mark first, then OKX swap, never fapi.
A field with no other source *configured* is still the thing that's ruled out.

## (d) Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-perps` | Cut from `ac885f4`. US-serving perps + (c). | **Yes. Merge this.** |
| `claude/stater-routing` | Merged (`ffcc6e9`). | Done. |

Hyperliquid `predictedFundings` from Railway is still UNVERIFIED until this branch is live.
Next session: after prod SHA includes this commit, read `/crypto/market` `derivatives.predicted_by_venue` and date the matrix cell.

## Robinhood
US perps are announced for "the coming months", not live, with no market-data feed announced.
Their API would mean holding the principal's trading key, which this charter forbids.
**Revisit only if Robinhood publishes a feed that needs no account key.**

## What the next CC-STATER session should do first
1. Confirm BUILD merged `claude/stater-perps` and prod SHA moved.
2. From the hub, verify Hyperliquid `predictedFundings` (Binance/Bybit) and update the matrix
   from UNVERIFIED to a dated Railway reading.
3. Re-time `/crypto/market` and `/crypto/state/BTC` with the perps pack live (4 s budget).
