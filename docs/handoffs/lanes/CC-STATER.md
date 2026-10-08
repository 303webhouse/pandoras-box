# CC-STATER lane — status

**Written:** 2026-10-07 18:23 MDT (2026-10-08 00:23 UTC)
**Worked against:** `origin/main` = `600694a`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r741-lsr`.
**Hub at read time:** not re-timed this turn.

## Why this lane exists
SPINE chartered CC-STATER (R-IV.618) to own Stater Swap, the hub's crypto surface.
- **Frontend:** `frontend/stater.*`.
- **Crypto backend:** `api/crypto_market.py`, `api/btc_signals.py`, `bias_filters/crypto_*`,
  `config/crypto_*`, `jobs/crypto_*`, `strategies/crypto_setups.py`, `strategies/btc_market_structure.py`,
  `services/read-only/crypto_*`, `hub_mcp/tools/crypto_*` and `utils/crypto_sessions.py`.

It inherits S-6M's ownership of `stater.*`. It never touches Agora files, `backend/signals/`,
`main.py`, schema or migrations, or positions and cash. It holds no exchange credentials and places
no orders.

**On the principal's PC (R-IV.628(b)):**
- Never check out, commit to or push `main`; BUILD merges.
- The database login is read-only.
- No Railway CLI, no deploys, no environment-variable changes.

## R-IV.741 — in flight (BUILD merges after SPINE ruling)
`_make_request()` no longer returns bare `None`. Budget refuse is `CoinalyzeMiss`
with reason `COINALYZE_BUDGET_REFUSED`. Vendor fail/empty (no key, HTTP 429,
non-200, exception, empty body) is `COINALYZE_VENDOR_FAILED`. Every getter cell
that is still None carries that reason. Budget refuse does not use the "no data"
error string. `bias_scheduler.py` was not touched (R-IV.740).

**Hourly cycle Coinalyze count (evaluate_all_symbols, six symbols):**
cap and froth run in parallel, so funding and OI each fire twice on a cold cache.
Per symbol: 6 HTTP (`/funding-rate` ×2, `/funding-rate-history`,
`/open-interest-history` ×2, `/liquidation-history`). Across six symbols,
sequential: **36 calls**. LSR is not in this job. Against the shared 40/minute
budget that leaves 4 slots if nothing else runs in the same window.

**Gather order does not guarantee LSR is the one refused.** The four-way gather
is `snapshot_for` (page poll), not the hourly job: funding, OI, liq, then LSR.
`_coinalyze_allow()` is sync and runs at first `_make_request`, so LSR is last
among that gather's four checks — likeliest when remaining slots are 1, not
the only refuse when remaining is 0 or 2. HYPE's gather is funding + LSR only.

**Proposed (no code):** singleflight so cap/froth share one funding and one OI
call (36 → 24); put LSR first in the page gather or reserve it a token; keep
the 300s getter cache and raise the 30s snapshot cache so a Stater poll in the
same minute as the hourly job does not spend the leftover 4 slots.

## Composite-break dates (R-IV.727(e))
Still waiting on BUILD's first hourly cycle after the r707 deploy.

- Date BTC liquidations and open interest became genuinely Coinalyze-sourced:
  **TBD.**
- First LIVE liquidations date per alt: ETH / SOL / HYPE / ZEC / FARTCOIN **TBD.**

## R-IV.727 — merged
`claude/stater-r707-liq` is on `main` (`ed5491c`). Units USD; Coinalyze OI/liq
score again; OKX stays unscored. `$5M` is hourly liquidations.

## R-IV.700 — merged
Cycle remap + strategy engine off fapi + HYPE history skip (`eff4077`). Spot stays.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r741-lsr` | Pushed. | After SPINE's merge ruling. |
| `claude/stater-r707-liq` | Merged (`ed5491c`). | Done. |
| `claude/stater-r700-queue` | Merged (`eff4077`). | Done. |

## What the next CC-STATER session should do first
Hold the r741 merge until SPINE rules. If BUILD reported the first post-r707
hourly cycle, fill the composite-break dates above. Do not skip HYPE Binance
spot. Do not rebuild the Binance VPN. Do not edit `bias_scheduler.py`.
