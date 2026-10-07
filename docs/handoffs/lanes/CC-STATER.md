# CC-STATER lane — status

**Written:** 2026-10-07 13:24 MDT (2026-10-07 19:24 UTC)
**Worked against:** `origin/main` = `fec4652`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r707-liq`.
**Hub at read time:** not re-timed this turn.

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

## R-IV.725 — in flight, merge held
Coinalyze history callers send UNIX seconds. `convert_to_usd=true` on liquidation-history,
open-interest-history, and funding-rate-history (docs default is false / coin units; hub
consumes OI and liq as USD). R-IV.724(b) has not settled units in this repo.

Coinalyze-sourced liquidations, open_interest, and oi_extreme are state **NA**,
reason `COINALYZE_UNITS_UNVERIFIED`. OKX fallbacks stay `OKX_FALLBACK_UNSCORED`.
Funding and term-structure cells now take `source` from the vendor result and still score
(they are rates, not USD notionals).

**This branch changes BTC's dial:** its liquidations cell stops scoring. Intended.
**When this branch is live, record that date in this file** so the composite history
shows the break. Not live yet.

**Alt cells have not gone LIVE.** Date that too when they first do.

Timestamps: seconds, not milliseconds. Waiting on BUILD's units result and SPINE's ruling
before merge.

long_short: scope-only this turn. Caller already sent seconds. Serves None because
`/long-short-ratio-history` is asked with the same `.A` aggregate as funding; empty
history → `ratio: None`; no OKX fallback. convert_to_usd is not on that endpoint.

## R-IV.718 / R-IV.715 / R-IV.707
Source-from-result for liquidations stands. The 715 "0 of 2,153 OKX-sourced" count
read a literal. Composition `$5M` gate stands. Seed vs hardcoded `$5M`/75% recorded.

## R-IV.700 — merged
Cycle remap + strategy engine off fapi + HYPE history skip is on `main` (`eff4077`).
Spot stays.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r707-liq` | Pushed. Merge held. | No — wait for BUILD's units result and SPINE's ruling. |
| `claude/stater-r700-queue` | Merged (`eff4077`). | Done. |
| `claude/stater-r692-cache` | Cache 4 s → 8 s. | BUILD accepted (R-IV.699). |

## What the next CC-STATER session should do first
Hold the merge. After BUILD's R-IV.724(b) units result and SPINE's ruling, lift
`COINALYZE_UNITS_UNVERIFIED` only if units are USD. When this branch goes live,
date it here (BTC liquidations leave the composite). Do not skip HYPE Binance spot.
Do not rebuild the Binance VPN.
