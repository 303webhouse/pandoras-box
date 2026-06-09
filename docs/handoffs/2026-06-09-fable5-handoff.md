# HANDOFF BRIEF — Pandora's Box (for a fresh Fable 5 chat)
*State as of 2026-06-09, post-close. First thing you should do is `git fetch && git status` from `C:\trading-hub` — this project has been burned by stale clones before.*

## What this is
Pandora's Box is a FastAPI/Postgres trading-intelligence platform on Railway (repo `303webhouse/pandoras-box`, local clone `C:\trading-hub`). It ingests Unusual Whales (UW) + TradingView data, scores signals through a 20-factor bias composite, and surfaces trade ideas in three buckets (B1 longer-dated thesis, B2 3-5 day tactical, B3 intraday scalps). **Core rule: automate everything so Nick can focus only on trade execution.**

## How we work (operating model)
- **Two-eyes relay.** This chat = architecture / review / gate layer that produces *briefs*. **Claude Code (CC)** in VSCode = the builder. Nick relays CC's reports back to chat between sessions. Codex is backup builder.
- **Nick is not a coder.** Explain SWE + trading jargon plainly, give exact step-by-step for Windows, minimal assumptions. He has ADHD — chunked, decisive output, one strong rec when you're >=90% sure, sarcasm to reground him if he rabbit-holes.
- **Investigation-first.** Every workstream opens with a read-only Phase 0 -> findings report -> **STOP at the gate** before any code/schema/deploy. Shadow mode mandatory before any scoring change.
- **No production writes, migrations, or deploys without Nick's explicit greenlight relayed in chat.** Deploys only **outside market hours** (Railway restart drops the hub ~60-170s). Market = 7:30am-2:00pm MT.
- **Verify, don't assume.** "Committed != deployed != working" — always ping a live endpoint. Treat fake-healthy states (e.g. a confident `0.0` on missing data) as failures, not safe defaults. The review gates have earned their keep: sub-brief 1 caught three silent GEX bugs this way.

## Stack & access
- **Railway** project `fabulous-essence`, env `production`, service `pandoras-box`. Push to `main` -> auto-deploy. CLI v4.30.3, authed as nickhrtzg@gmail.com.
- **Postgres** (Railway, exclusive — Supabase is INACTIVE). All DB ops via `get_postgres_client()`. Migrations are **manual**, in `C:\trading-hub\migrations\`.
- **Prod DB from a local script:** `railway run python <script>` from `C:\trading-hub` injects creds, BUT the injected `DB_HOST` is internal-only — override host to `trolley.proxy.rlwy.net:25012` with `ssl.CERT_NONE`. (`load_dotenv` at `postgres_client.py:108` uses `override=False`, so Railway-injected vars beat the stale local `.env`.)
- **Hub MCP** — 9 read-only tools at `https://pandoras-box-production.up.railway.app/mcp/v1/`, GitHub OAuth. You have these as `hub_get_*` tools.
- **UW API** — Basic plan, Bearer token from `UW_API_KEY` Railway env var. **Data hierarchy: UW primary for everything incl. OHLCV; yfinance fallback only; Polygon + FMP are deprecated — never add new deps.**
- **VPS** "Pivot II"/OpenClaw at `188.245.250.2` (runs cron: doc syncs, committee bridge, pre-market briefing).
- **Accounts:** Robinhood (options, max 3 contracts, 5% risk/position); Fidelity Roth (inverse/leveraged ETFs only, no options). Always pull live balances via `hub_get_portfolio_balances` — never trust a memory snapshot.

## Active frame
Master brief: `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md`. Three workstreams: (A) outcome self-scoring + committee logging, (B) UW integration, (C) new strategy shadows.

## SHIPPED (sub-brief 1 + sub-brief 2 core)
- **Sub-brief 1 — DONE.** B2 options-P&L resolver (`signal_options_expressions`, shadow, forward-only — does NOT re-grade history). GEX bias-factor fix (reads the *latest row* of UW's daily series, fail-loud, staleness guard, price-decoupled).
- **B1 Layer 1 — SHIPPED & LIVE** (`36afa09`): `gex_regime` label on the composite, currently reads **MOMENTUM**.
- **B3 — SHIPPED** (`fc28349`, shadow): darkpool confluence into `score_v2`, spread-relative dead-band (`SPREAD_FRACTION_K=0.5`).
- **A3 — SHIPPED** (`a6f33d3`, shadow): outcome self-scoring, `FWD_RETURN` + `OPTIONS_PNL` resolvers. Migrations 017-019 run + verified.
- **A4 — SHIPPED** (`8f22d79`): committee-review logging into the `committee_passes` table. Migration 020 run (adds `recommendation`, `committee_run_id`, `key_risk` + unique constraint).

## OPEN / IN-FLIGHT (pick up here)
1. **A4 end-to-end verify — PENDING.** Need the first *live* committee pass to write a non-null `recommendation` row to `committee_passes`. (Gate-3 verify script `d24cabb` was rolled back; open question whether to re-commit an `a4_gate3_verify.py` for parity with A3.)
2. **FWD_RETURN historical backfill — awaiting Nick's go.** Script is `scripts/backfill_fwd_returns.py`. Committing the script is not running it — the backfill is manual and gated on Nick's explicit go.
3. **OPTIONS_PNL live verify** — auto-happens the first time B2 exits a row during regular trading hours. Just watch for it.
4. **Stale local `config/.env`** — points to a dead Supabase project; fix before the next migration. The Railway public-proxy pattern above is the working workaround meanwhile.

## NEXT (sub-brief 2 remainder -> sub-brief 3)
- **B4** — PYTHIA market-profile feed (`hub_get_market_profile`) via a TradingView webhook. **Must validate HMAC (AEGIS).** Requires a full Olympus committee regression pass before go-live.
- **Sub-brief 3 (shaping up):** B1 Layer 2 (GEX into the *scorer's* regime gate, not just the composite label); retire P2 (the yfinance flow path); **restore `iv_rank`** (broken since late April — missing Railway env var is silently zeroing `iv_bonus`); reconcile GEX-based regime vs the ADX-based regime in `trade_ideas_scorer.py`.

## Hard-won gotchas (do NOT re-learn these)
- **`outcome_source` discipline:** `FWD_RETURN` / `OPTIONS_PNL` / `COMMITTEE_REVIEW` must NEVER overwrite `ACTUAL_TRADE` or pollute the `signal_outcomes` `BAR_WALK` rows.
- **UW `/greek-exposure` is a DAILY TIME SERIES** (~251 rows). Use the **latest row**; never sum. Date param changes behavior: no date ~ 1yr daily history; with date -> 30-day cap.
- **UW api_spec is unreliable** — verify field names against live data (real GEX fields are `call_gamma`/`put_gamma`, not the spec's `call_gex`/`put_gex`). UW REST URLs are kebab-case (`/stock-state`); the MCP tools are snake_case.
- **`/option-contracts` caps at 500** — always pass `?expiry=` and `?option_type=` or chains truncate silently.
- **Postgres is fine (~60%)**; the brief's old "94% / drop tables" line was stale. The deprecated `positions`/`open_positions`/`options_positions` tables are **NOT droppable** — they still have live code paths. The `unified_positions` migration (011) is incomplete, so "unified_positions is the single source of truth" is currently *false in prod* — that's a separate portfolio-reconciliation brief, not part of this work.
- **UW `/stock-state` (quotes) is flaky.** `hub_get_quote` erroring post-market = UW offline, not a server failure. Hub staleness tells: all three timeframes returning identical composite = off-hours data freeze; `hub_get_flow_radar` caps at 24h regardless of param.
- **Windows git:** commit with `git commit -F C:\temp\commitmsg.txt` (avoids nested-quote mangling); `git add <files>` explicitly (the working tree has ~70 untracked files you don't want to sweep in); run git via `cmd` with a `cd /d C:\trading-hub &&` prefix.
- **Price verification:** before anchoring any analysis to a specific spot level, web-search to confirm it. Never use a stale hub read for price (TORO fabrication-incident precedent).
- **Olympus Impact:** anything touching PYTHIA / THALES / PIVOT / DAEDALUS or the Insights feed needs a post-build full committee pass on a known-good ticker before go-live.

## First actions in this chat
1. `git fetch && git status` from `C:\trading-hub`; confirm you're current.
2. Pull `hub_get_bias_composite`; confirm `gex_regime` is populated and the `gex` factor is non-zero (confirms sub-brief 1 + B1 L1 are live).
3. Ask Nick which thread he wants: **A4 end-to-end verify**, **FWD_RETURN backfill** (needs his explicit go), or **B4**. Default recommendation if he's unsure: close out A4's e2e verify first — it's the cheapest open loop and unblocks committee-outcome attribution.
