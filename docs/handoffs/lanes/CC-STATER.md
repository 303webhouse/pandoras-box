# CC-STATER lane — status

**Written:** 2026-10-06 22:43 MDT (2026-10-07 04:43 UTC)
**Worked against:** `origin/main` = `81bf3ef` (PR #53 agora crypto stale)
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`, on `claude/stater-r700-queue` (cut from `origin/main` `81bf3ef`).
**Hub at read time:** not re-timed this turn. HYPE Binance spot stays (R-IV.700(a)); cache 4 s → 8 s is on `claude/stater-r692-cache` for BUILD (R-IV.699).

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

## R-IV.700(a) — accepted
HYPE's Binance spot stays. It answers from Railway via `data-api.binance.vision`.
`CACHE_TTL_SECONDS` 8 s is BUILD's merge (R-IV.699), not this branch.

## (b) Queue, in order

### 1. Cycle engine double count (wrong number first)
Vendor FIRING is bidirectional. Froth already gates on the top-side extreme;
capitulation copied the vendor flag, so a funding blow-off scored both columns.

`_directed_cap_signal` keeps FIRING on the flush side only:
- funding ≤ −0.03; basis ≤ −5; skew ≥ +5 (put)
- OI only on `accumulation`; term structure only backwardation+falling
- liquidations only `long_heavy`

Vendor flag is kept as `vendor_signal`. Tests in `test_s3_phase2_cycle_engine.py`.

### 2. Geo-blocked strategy engine
`integrations/binance_futures.py` no longer calls `fapi.binance.com` (HTTP 451
from Railway; VPN not rebuilt). Same return shapes for `crypto_setups.py`.
Funding from Coinalyze (percent → fraction) / Hyperliquid / OKX; klines,
ticker, trades, and books from OKX public.

### 3. HYPE Coinalyze history on cold `/crypto/market`
`snapshot_for("HYPE")` skips `get_open_interest` and `get_liquidations`
(the two history endpoints). Funding snapshot still runs. OI can come from
Hyperliquid. Long/short history is still asked.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key. Revisit only if a keyless feed
is published.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r700-queue` | Cycle remap + strategy engine off fapi + HYPE history skip. | **Yes. Merge this.** |
| `claude/stater-r692-cache` | `/crypto/market` cache 4 s → 8 s. | BUILD already accepted (R-IV.699). |
| `claude/stater-r684-matrix` | Pushed `0e3dca4`. Not yet on `origin/main`. | BUILD already accepted (R-IV.688(d)). |
| `claude/stater-perps` | Merged (`30adbd3`). | Done. |

## What the next CC-STATER session should do first
Wait for BUILD to merge this branch and the cache branch, then re-time
`/crypto/market?symbol=HYPE` from Railway. Do not skip HYPE Binance spot
unless a later Railway read shows it dead (400 listing or 451 block).
Do not rebuild the Binance VPN.
