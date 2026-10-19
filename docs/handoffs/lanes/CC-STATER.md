# CC-STATER lane — status

**Written:** 2026-10-19 13:55 MDT (2026-10-19 19:55 UTC)
**Worked against:** `origin/main` = `c2f243f4`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r1254-comments`.
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
- The database login is read-only (`stater_ro`, SELECT only).
- No Railway CLI, no deploys, no environment-variable changes.

## R-IV.1254 — rulings
SPINE accepted the R-IV.1197 report (window 2026-10-08 05:41Z to 2026-10-15 05:41Z, 169 cycles
per symbol), the state of all seven /stater sections, and `claude/stater-r1197-report` at `c22abb17`.
R-IV.1253 duplicated R-IV.1197. If it arrives, the reply is `see R-IV.1197 report` and nothing else.

**Thresholds, ruled. Nothing in code changed, and no revisit is scheduled.**
- The $5M liquidation gate stays for BTC, ETH and SOL.
- `oi_extreme` holds at 5.0.
- FARTCOIN liquidations stay unscored. One week is too thin to base a gate on its p99.

Crypto scanners remain display-only (salvage plan 10-12). They stay off the trade-idea surface
and are graded against always-long BTC. LAB's long-history replay is unchanged (by 2026-11-30).

**Comments.** The header comments in `frontend/stater.js` and `frontend/stater.html` no longer
say the macro, tape, cycle, feed and drawer are placeholders pending the SG-1 layout gate.
Those seven sections are live. The cache pins were left as they were: a comment does not change
what the browser renders.

**SG-3.** Closed in `docs/strategy-reviews/stater-swap-redesign/s6-rulings-ledger.md`: not run;
superseded by the principal's use of the live page since 2026-07-24. It gates nothing.

## 7-day collection (accepted; full tables on `claude/stater-r1197-report`)
The liquidation cell is the sum of the last two 1-hour buckets, not one clock hour. BTC/ETH/SOL
cycles at or above $5M: 22 / 23 / 8 of 169. `oi_extreme` fired 0 times on BTC, ETH and SOL
(max positive change 1.74 / 4.79 / 3.55 against a gate of 5.0).

## Remap break (R-IV.753(a) / R-IV.745)
First cycle on the USDT-linear map: **2026-10-08 05:41:24.698 UTC (2026-10-07 23:41:24 MDT)** —
BTC. ETH 05:41:25.209Z, SOL 05:41:26.969Z. That is also BTC's first genuinely Coinalyze-sourced
liquidations date. No computation compares a value across this switch (R-IV.725(c)4).

## Merged
- R-IV.753 dates: `1ad8eea2` is on `main`.
- R-IV.745 `25d579e` / `304412c`; R-IV.742 `e9e746e` / `43342ae`; R-IV.741 `1bd7810`;
  R-IV.727 `ed5491c`; R-IV.700 `eff4077`.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r1254-comments` | Comment headers, the SG-3 ledger line, and these lane files. | Yes. Merge this one. |
| `claude/stater-r1197-report` | Accepted report at `c22abb17`. Not on `main`. | Do not merge after this branch. Its lane file is the older copy and would overwrite this one. |

Merging `claude/stater-r1254-comments` touches `frontend/`, so Railway will redeploy. The page
behavior does not change.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter forbids holding
the principal's trading key.

## What the next CC-STATER session should do first
Nothing is open. Do not change a threshold. Do not schedule a revisit. Do not skip HYPE Binance
spot. Do not rebuild the Binance VPN. Do not edit `bias_scheduler.py`. If R-IV.1253 arrives,
answer `see R-IV.1197 report` only.
