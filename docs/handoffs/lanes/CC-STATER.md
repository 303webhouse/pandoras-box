# CC-STATER lane — status

**Written:** 2026-10-06 18:30 MDT (2026-10-07 00:30 UTC)
**Worked against:** `origin/main` = `bf0da4e` (Merge pull request #51 … accounts-live)
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`, on `claude/stater-r684-matrix` (cut from `origin/main` `bf0da4e`).
**Hub at read time:** prod `bf0da4e` (perps merge `30adbd3` is an ancestor), `status: healthy`, process started 23:03:36 UTC. Proxy flag false.

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

## R-IV.684 — perps live; matrix dated
BUILD merged `claude/stater-perps` as `30adbd3`. This session verified `predictedFundings`
from the hub and replaced UNVERIFIED in the vendor matrix.

Hub `GET /crypto/market` 2026-10-07 00:28 UTC (18:28 MDT), all six coins:

| Coin | BinPerp | BybitPerp | HlPerp | envelopes | cold s | warm s |
|---|---|---|---|---|---|---|
| BTC ETH SOL ZEC FARTCOIN | present, `hyperliquid:BinPerp` | present, `hyperliquid:BybitPerp` | present | 10 each | 0.57–0.66 | 0.06–0.08 |
| HYPE | **null** | **null** | present | 10 | 0.62 | 0.08 |

Ten venue+age envelopes per coin (60 across six). `ttl_s=900`, not stale. Proxy false.

## Cold `/crypto/market` (HYPE 1.873 s in BUILD's read)
The new pack runs on every 4 s cache miss: two Hyperliquid POSTs (shared 120 s) plus four
Coinalyze GETs per coin (funding, OI, liquidation-history, long/short-history; 300 s cache),
gathered under a 4 s budget, in parallel with the venue fan-out. HYPE is the thin Coinalyze
aggregate (`HYPEUSDT_PERP.A` only); those two history endpoints are the extra wait.
HYPE also still asks Binance spot. Warm reads after those caches hit are ~0.06–0.08 s.

Legacy Agora polls one symbol every **5 s** (`frontend/app.js` `CRYPTO_MARKET_POLL_MS`),
which is longer than the 4 s response cache, so that poll almost always misses it. Stater
fans out all six every 30 s (`frontend/stater.js` `POLL_MS`). 1.873 s is under 5 s.

## Agora last-good crypto price — file and lines
Not `v2.js` (no crypto price poll; the "last good map" at `v2.js:2135` is book exits).
Not a last-good *price* map on Stater (`stater.js` polls `/crypto/market` × 6 and keeps
`_last` for the drawer only).

**Legacy Agora `frontend/app.js`:**
- `480–482` — `cryptoMarketData`, `cryptoMarketLastGood`
- `487` — `CRYPTO_MARKET_POLL_MS = 5 * 1000`
- `1473–1481` — start the 5 s poll when the crypto view is visible
- `5053–5083` — `loadCryptoMarketData`; on fetch fail, re-render the last snapshot
- `5106–5120` — `rememberNumber` / remember into `cryptoMarketLastGood`
- `5177–5182` — render from `cryptoMarketLastGood` when the live field is missing

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter forbids
holding the principal's trading key. Revisit only if Robinhood publishes a feed that
needs no account key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r684-matrix` | Matrix + this file. `predictedFundings` dated from Railway. | **Yes. Merge this** (docs/config only). |
| `claude/stater-perps` | Merged (`30adbd3`). | Done. |

## What the next CC-STATER session should do first
Nothing blocking. If asked: the 4 s `/market` cache vs the 5 s legacy poll, or HYPE's
thin Coinalyze history calls.
