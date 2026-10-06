# CC-STATER lane — status

**Written:** 2026-10-06 10:18 MDT (16:18 UTC)
**Worked against:** `origin/main` = `0a2a4cb` (fix(accounts): a balance row carries its display name…)
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`, on `claude/stater-*` branches only (R-IV.628).
**Hub at read time:** prod runs `0a2a4cb`, `status: healthy`. Phase 0 is live (`df328e8` is an ancestor).

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

## Login (R-IV.645(b))
Postgres tool logs in as `stater_ro` (`current_user` / `session_user`). SELECT works
(`crypto_cycle_log` SELECT privilege true). INSERT is refused: table INSERT privilege is false,
and `INSERT INTO crypto_cycle_log` returned a read-only-transaction error. Not the superuser.

## After reading (R-IV.645(c))
Same endpoints as the before probe, no session, hard stop at 5 UW calls counted on `crypto_bars_*`
tags only. Probe window **16:10:27–16:11:32 UTC** (10:10–10:11 MDT).

| | UW `crypto_bars_*` | GET writes |
|---|---|---|
| baseline | absent (0) | `crypto_cycle_log` max id 12842; `crypto_tape_health_log` max id 45526 |
| after the GETs | **0** (tags still absent) | **0** new rows in either log |

| Endpoint | HTTP | UW | elapsed |
|---|---|---|---|
| `/crypto/regime`, `/crypto/clock` | 200 | 0 | 0.22 s / 0.06 s |
| `/analytics/risk-budget`, `/trade-ideas?limit=50` | 401 | 0 | ~0.1 s |
| `/crypto/market` × 6 coins | 200 | 0 | **8.08 s each** |
| `/crypto/cycle-extremes` | 200 | 0 | 0.17 s |
| `/crypto/state/BTC` | 200 | 0 | 12.04 s (not UW) |
| `/crypto/tape-health` | 401 | 0 | 0.08 s |

Passive, same day: no `crypto_bars_*` tag appears in `/api/uw/health/by_caller` at all (total ~6k
on other callers). BUILD's claim holds: no tracked symbol uses UW for bars.

`/crypto/market` still waited 8.08 s per coin. Live payload (BTC, 16:12:33 UTC):
`prices.perps.binance` null, `bybit` null, `okx` served; `funding.binance`/`bybit` null,
`funding.okx` live; `routing.binance_perp_proxy_enabled` **true**. Errors empty. HYPE
`binance_spot` returned a price from Railway. FARTCOIN Binance spot 400.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-routing` | Cut from `origin/main` `0a2a4cb`. Two commits: `27d4a04` (routing), `794056d` (CVD label). Lane file on top. | **Yes. Merge this.** |
| `claude/stater-phase0` / `claude/stater-p0-market` | Merged (`df328e8` / `087ce2b`). | Done. |
| `s6-stater-build` | Older S-6 cockpit work. Not touched. | Not this lane's to merge. |

## What this session did
1. **Routing (`27d4a04`):** `/crypto/market` no longer asks Binance perps (the 8 s venue — proxied
   `fapi.binance.com` waiting out the 8.0 s client timeout; matrix GEO_BLOCKED) or Bybit.
   FARTCOIN is not asked on Binance spot or OKX spot. HYPE is routed to Binance spot
   (`_BINANCE_SPOT_SYMBOL["HYPE"] = "HYPEUSDT"`), after the Railway check above. Response
   shape unchanged. Test: a fake venue that sleeps 8 s on fapi/bybit cannot delay the snapshot.
2. **CVD label (`794056d`):** `_fetch_cvd` still does not read the real `cvd` key. Missing
   `cvd_analysis` contributes 0 as before, reason `"no data"` instead of `"CVD neutral"`.
   Test parametrizes every existing score path; all scores unchanged. The real CVD fix stays
   a shadow score under R-IV.637(c).

## Still open (not this branch)
- Agora's client-side last-good copy (ABACUS).
- Geo-blocked strategy engine (`crypto_setups.py` → `fapi.binance.com` 451).
- Cycle engine double count.
- `/crypto/state/BTC` took 12 s with zero UW (likely Coinbase candles); not investigated.

## What the next CC-STATER session should do first
1. Confirm BUILD merged `claude/stater-routing` and that prod serves it.
2. Time `/crypto/market` again: it should be well under 8 s.
3. Then the geo-blocked strategy engine and the cycle engine's double count, each on its own branch from `main`.
