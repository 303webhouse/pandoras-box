# CC-STATER lane — status

**Written:** 2026-10-07 12:52 MDT (2026-10-07 18:52 UTC)
**Worked against:** `origin/main` = `a16e697`
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

## R-IV.718 — in flight, merge held
The liquidations cell source is now `vendor_src` from `get_liquidations()`, not a
`"coinalyze"` / `"okx"` literal. Funding, OI, and term-structure cells still pass a
literal `"coinalyze"` while those results carry their own source; listed in the
R-IV.718 reply, not changed.

`crypto_cycle_log` stores no field that distinguishes OKX-served liquidations from
Coinalyze ones (`parsed_rows` / windows were never copied onto the cell). No recount.

Timestamps not touched. Waiting on BUILD's seconds probe (R-IV.717(c)).

**2edd801 stays unmerged.** Taking BTC's OKX fallback out of scoring would change
BTC's dial while Coinalyze `/liquidation-history` still returns `[]`.

**Alt cells have not gone LIVE.** When they first do, record that date here.

## R-IV.715 / R-IV.707
715's "0 of 2,153 OKX-sourced" counted the literal. BUILD's R-IV.714(b) calls got
HTTP 200 `[]` from Coinalyze for BTC too. Composition `$5M` gate stands. Non-BTC
OKX request+units stand. Seed vs hardcoded `$5M`/75% recorded, not changed.

## R-IV.700 — merged
Cycle remap + strategy engine off fapi + HYPE history skip is on `main` (`eff4077`).
Spot stays.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r707-liq` | Pushed. Merge held. | No — nothing merges until SPINE rules after BUILD's probe. |
| `claude/stater-r700-queue` | Merged (`eff4077`). | Done. |
| `claude/stater-r692-cache` | Cache 4 s → 8 s. | BUILD accepted (R-IV.699). |

## What the next CC-STATER session should do first
Hold the merge. Do not touch timestamps. Wait for BUILD's seconds probe and SPINE's
ruling. Do not skip HYPE Binance spot. Do not rebuild the Binance VPN. When alt
liquidations first go LIVE, date it in this file.
