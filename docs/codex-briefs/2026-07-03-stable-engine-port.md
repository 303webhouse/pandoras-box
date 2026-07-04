# CC BRIEF — Stable Engine Port (backend only, zero UI)

**Date:** 2026-07-03 · **Author:** Opus (Olympus + Muses + Titans double-pass complete; Nick approved 2026-07-03)
**Scope:** Backend only. No pixels — the UI mockup gate does not apply to this brief.
**Source to vendor:** `C:\trading-hub\stable_market_board_LATEST\stable_market_board` — Stable Market Board by Ryan Scott, shared within Nick's trading group. Credit Ryan in file headers. Personal use inside this private hub only; do not redistribute.
**Quota impact:** ZERO UW calls. All new data via yfinance (sanctioned fallback: this is EOD/context data, not execution-path data).

## Execution rules
1. Pre-flight from repo root: `git fetch && git status`; pull if behind; report state.
2. Explicit pathspecs only, never `git add .`. Five commits as scoped. Push any time today — Fri 2026-07-03 is a market holiday.
3. Do NOT copy from source: `polygon_client.py`, `cboe_ingest.py`, `server.py`, `stable/frontend/`, any Polygon references. The math ports; the plumbing doesn't.
4. Labeling contract (house rule): every stored run and every API envelope carries `as_of` (ISO UTC), `data_age_seconds`, `anchor` ('close'|'provisional'), and `degraded` (bool). Never fabricate freshness; unknown = null + degraded, not zero.

## Task 1 — Vendor the engine (Commit 1)
Create `backend/stable_engine/` with `universe.py`, `metrics.py`, `scoring.py` adapted from source (keep formulas IDENTICAL — breadth, leadership, momentum, acceleration, extension penalty, status labels, EXCLUDED_THEMES). Copy `data/universe.csv` (691 rows: ticker,name,sector,industry,theme,subtheme,liquidity_tier) to `backend/stable_engine/data/`. Replace DuckDB calls with our Postgres client (`backend/database/postgres_client.py`). Header comment in each file: "Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026). Math unchanged; data layer swapped Polygon->yfinance."

## Task 2 — Data layer + backfill (Commit 2)
New module `backend/stable_engine/bars_yf.py`: batched yfinance daily OHLCV downloader (batches of ~100 tickers, retry-once with backoff). New additive tables: `stable_daily_bars(ticker, date, o, h, l, c, v)`, `stable_metrics(ticker, date, ...)`, `stable_theme_scores(theme, date, anchor, score, status, components..., as_of, degraded)`. One-time backfill script `scripts/stable_backfill.py`: 5 years daily for all 691 universe tickers + benchmark/index symbols. Coverage contract: every batch logs fetched/missing counts; if a run's coverage < 90% of the universe, mark the run `degraded=true` and log which tickers failed — NEVER fill gaps with fabricated or stale-as-fresh values.

## Task 3 — Scheduled jobs (Commit 3)
Register via the existing scheduler pattern (see `adx_regime_job` for the template):
- **Nightly full recompute** ~21:00 ET: refresh daily bars, recompute all metrics + theme scores, `anchor='close'`.
- **Provisional snapshots** 08:00 ET, 09:45 ET, 16:05 ET (trading days only): one batched yfinance pull of current-day prices for the universe; recompute theme scores + up/down-3% counts against live prices; store with `anchor='provisional'`. Structural metrics (DMAs, ATR ext, 20D highs) stay anchored to last close — do NOT recompute those intraday.

## Task 4 — Index + rates feed (Commit 4)
Every 10 min during RTH (managed job, market-days only):
- Majors: SPY, QQQ, IWM, RSP, DIA — 1d % change (reuse existing hub price data where already polled; yfinance for the rest).
- Yields: ^IRX (3m), ^FVX (5y), ^TNX (10y), ^TYX (30y). NOTE: Yahoo yield indices are yield×10 — divide by 10. Store as PERCENT (e.g. 4.46) plus day change in BASIS POINTS, plus computed 10y−3m spread. Yields are never displayed as ticker prices — this feeds Nick's "bond market as leading indicator" module.
Table: `stable_live_strip(symbol, kind='index'|'yield', value, day_change, as_of)`.

## Task 5 — Read-only endpoints + signal enrichment (Commit 5)
Endpoints (all envelopes per labeling contract):
- `GET /api/stable/regime` — regime label + thresholds used, dominant/emerging/fading themes, highs/lows counts, up/down 3%, %>50dma, %>200dma.
- `GET /api/stable/themes` — full ranked theme table (score, 1d delta, status, components).
- `GET /api/stable/theme/{theme}/members?top=5&bottom=5` — members ranked by 1d %, with last price, 1d %, RS vs benchmark (all from our tables — no UW calls in this endpoint).
- `GET /api/stable/index-strip` and `GET /api/stable/rates` — latest live-strip values.
Signal enrichment (READ-TIME ONLY): where the signals API returns a ticker, join ticker->theme via universe.csv and attach `theme`, `theme_score`, `theme_status`. No schema changes to signals/signal_outcomes, no write-path changes. Attribution logging of theme fields = a future ticket, not this brief.

## Do-NOT-touch list
`unified_positions` · `signal_outcomes` writes · any UW caller or Governor tag · Olympus skill files · `frontend/` (nothing visual ships in this brief) · scoring/bias composite live math.

## Done definition
- [ ] Backfill complete: row counts reported per table; coverage % reported; degraded runs (if any) listed with failing tickers
- [ ] Nightly + 3 snapshot jobs registered and visible in scheduler logs; one manual run of each executed and logged
- [ ] `/api/stable/regime` and `/api/stable/themes` return values in the ballpark of Ryan's 2026-06-18 board for overlapping fields (theme ranks ordering sane, breadth 40-60% range plausibility)
- [ ] Simulate a partial batch (block 20% of tickers): run marked degraded=true, nothing fabricated, endpoints expose the flag
- [ ] Yield endpoint returns 10y as a percent near 4.5 with bp day-change and 10y−3m spread
- [ ] Unit test adapted from source `tests/test_metrics_synthetic.py` passes against our port
- [ ] Grep confirms zero new UW callers and zero polygon imports
- [ ] All envelopes carry as_of, data_age_seconds, anchor, degraded

## Olympus impact
None now (no MCP contract changes). Future ticket: `hub_get_stable_regime` MCP tool so the committee can read the board directly.

## Rollback
`git revert` per commit; all tables additive; no existing data touched.

---
## ADDENDUM A (added 2026-07-03 after mockup markup — if you have already passed Commit 4, execute this as Commit 6)

**A1. Sector ETFs into the engine.** Add the 11 SPDR sector ETFs (XLK, XLF, XLV, XLY, XLC, XLI, XLP, XLE, XLU, XLRE, XLB) to the daily bars pull + metrics computation, tagged theme='Scan Only' (or equivalent) so they are EXCLUDED from theme scoring per the EXCLUDED_THEMES pattern. Their 50dma/200dma states feed the sector-divergence legend.

**A2. Expand the 10-min live strip.** Add to the RTH 10-min job: the 11 sector ETFs (kind='sector', store day % change), DX-Y.NYB as DXY (kind='fx'), USDJPY=X (kind='fx'). New small table `stable_intraday_points(symbol, ts, value)` — append each 10-min reading for sector/fx/yield symbols, retain 7 days, so intraday line charts have a series to draw.

**A3. New endpoints (same labeling contract):**
- `GET /api/stable/sector-divergence?window=1d|5d` — per-sector normalized %-change series from stable_intraday_points (1d) or daily closes (5d), PLUS per-sector `above_50dma` / `above_200dma` booleans from stable_metrics.
- `GET /api/stable/fx` — DXY + USDJPY latest values, day change, intraday series.
- Extend `GET /api/stable/rates` with `curve_points` (3m, 5y, 10y, 30y yields) and `curve_points_5d_ago` for the ghost line.

**A4. Done-definition additions:** sector-divergence returns 11 series with DMA booleans; fx returns two series; rates returns both curve arrays; all still zero UW calls (grep governor tags unchanged).

---
## ADDENDUM B (added 2026-07-03 — movers tape feed; execute as its own commit after Addendum A)

**B1. Movers screener job.** Every 10 min during RTH (+ one best-effort premarket pull ~08:00 ET): pull Yahoo's predefined `day_gainers` and `day_losers` screeners via yfinance. Apply junk filters (configurable, defaults: last price >= $2, avg volume >= 500k). Keep top 15 gainers and bottom 15 losers after filtering. For each ticker in our universe.csv, attach its theme. Store latest snapshot in `stable_movers(side, rank, ticker, pct, price, theme, as_of)`.

**B2. Endpoint.** `GET /api/stable/movers` → `{gainers:[15], losers:[15], as_of, data_age_seconds, degraded}`. Same labeling contract. If a screener pull fails, serve the last snapshot with honest data_age — never an empty-but-fresh response.

**B3. Done-definition additions:** movers endpoint returns 15+15 with themes where applicable; simulated screener failure serves stale-labeled data, not fake-fresh; still zero UW calls (grep governor tags unchanged).
