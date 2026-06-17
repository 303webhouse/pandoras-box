# Brief — `hub_get_trade_ideas`: expose the Trade Ideas / Insights feed to the Olympus committee via MCP

**Status:** Approved by Nick for repo placement. Investigation-first. **No code, no push until Nick says "build" in chat.**
**Author:** Olympus (Claude.ai) · **Builder:** CC (Claude Code) · **Date:** 2026-06-04

---

## 1. Why this exists

The hub's core output is the scored **Trade Ideas / "Insights"** list (TradingView signals -> scanners -> scored -> ranked in the `signals` table -> served to the Agora UI). Today that list is **frontend-only** — the Olympus committee, which runs over MCP, cannot see it. The committee only reasons about tickers Nick hands it manually.

**Goal:** a read-only MCP tool `hub_get_trade_ideas` that returns the **same ranked list the UI shows**, so the committee can factor the hub's own scored ideas into a pass. This is the read-side counterpart to the committee-review-logging build (backlog #3).

---

## 2. Source of truth (verified in Phase 0 by Olympus)

- **Table:** `signals` (Postgres). Access via `get_postgres_client()` from `backend/database/postgres_client.py` (+ `serialize_db_row`).
- **Existing endpoint already produces this feed:** `backend/api/trade_ideas.py`
  - `GET /api/trade-ideas` — flat ranked feed (`get_trade_ideas_feed`)
  - grouped/tiered feed via `_query_tier_groups` (the `/main-feed` path) — groups by ticker+direction, adds confluence tier + `display_score`.
- **Canonical "live ideas" filter** (from `_query_tier_groups`):
  ```sql
  status = 'ACTIVE'
  AND (expires_at IS NULL OR expires_at > NOW())
  AND created_at > NOW() - INTERVAL '24 hours'
  AND user_action IS NULL
  AND COALESCE(signal_category,'TRADE_SETUP') NOT IN ('INTRADAY_SETUP','FOOTPRINT')
  [AND feed_tier = $tier]
  ORDER BY COALESCE(adjusted_score, score_v2, score, 0) DESC, created_at DESC
  ```
- **Grouping:** keyed by `{ticker}:{direction}`; `confluence_tier` in {CONVICTION, CONFIRMED, STANDALONE}; `display_score` = base score + confirmation bonus (capped 100); `related_signals` deduped for scan-based strategies.
- **Effective score precedence:** `adjusted_score` -> `score_v2` -> `score`. Surface the effective value, not raw `score`.

---

## 3. Phase 0 — Investigation (HARD STOP — no code changes)

CC: confirm and report back **before** writing anything.

1. **Which endpoint does the Agora UI actually render** for the Insights list — flat `/api/trade-ideas` or grouped `/main-feed`? grep `frontend/` for `trade-ideas` / `main-feed`. The MCP tool mirrors whichever the UI renders (**expected: grouped**).
2. **Exact `signals` columns** (confirm against live schema via `information_schema.columns` or the model): `adjusted_score, score_v2, score, feed_tier, confluence_tier, signal_category, user_action, status, expires_at, gate_type, ticker, direction, strategy, signal_type, entry_price, stop_loss, target_1, target_2, risk_reward, timeframe, bias_alignment, timestamp, created_at, signal_id`.
3. **Is the canonical query/grouping already a reusable function**, or inline in the route handler? Name the exact function(s) and file/line anchors.
4. **Existing hub-MCP tool pattern:** read `backend/hub_mcp/tools/hydra_scores.py` (or another current tool) and the tool registry / list mechanism. Note the response envelope (`status: ok|degraded|unavailable`), auth (bearer), and the describe/list wiring.

**Deliverable:** findings + proposed exact find/replace anchors. **Then WAIT for Nick's go.**

---

## 4. Phase 1 — Implementation (only after greenlight)

**ATLAS — single source of truth (non-negotiable):**
- Extract the canonical "active grouped trade ideas" query + grouping into **one shared helper** (e.g. `backend/signals/feed_service.py::get_active_trade_ideas(...)`, or reuse the existing function if it's already shared). **Both** `api/trade_ideas.py` **and** the new MCP tool call it. Do **not** duplicate the SQL/filter inside the MCP tool — that's how the committee's view silently drifts from the UI.
- New tool file `backend/hub_mcp/tools/trade_ideas.py`, mirroring the existing hub-tool pattern. Register in the MCP tool registry/list.
- Tool name: `hub_get_trade_ideas`.

**Params (keep minimal):**
- `limit` (int, default 15, max 25)
- `min_score` (float, optional) — filter on effective/display score
- `direction` (optional, LONG|SHORT)
- `include_related` (bool, default false) — include the deduped related-signal summary per group

**Output (curated, per grouped idea):**
`ticker, direction, display_score (effective), confluence_tier, distinct_strategy_count, strategies[], signal_type (primary), entry_price, stop_loss, target_1, target_2, risk_reward, timeframe, bias_alignment, signal_count, newest_at (+ derived age_minutes), signal_id (primary)`.
- **Do NOT** include `triggering_factors` or `bias_at_signal` blobs (the 7 MB of noise). At most a tiny `score_components` summary: `{base_score, confirmation_bonus}` — nothing more.
- Envelope matches other hub tools: `status` (ok/degraded/unavailable), timestamp, `schema_version`.

**AEGIS:**
- Read-only; exposes the same data already served to the authenticated dashboard; gated by the existing MCP bearer token — no new auth surface.
- Explicitly strip the embedded JSON blobs. No secrets/data-source internals in the payload.

---

## 5. Phase 2 — Dry-run + verify (gates around the push)

- **Dry-run (pre-push):** run the shared helper locally against the DB (read-only) and confirm the returned set matches the UI's Insights list — same tickers, order, top-N.
- **Post-deploy:** call `hub_get_trade_ideas` live via MCP; confirm parity with the UI and a sane payload size (no blobs). Railway restart window ~60-170s of tool errors is normal, not a failed deploy.
- Add/extend a test mirroring existing hub-tool tests.
- **Committed != deployed** — verify the live endpoint, never trust commit status alone.

---

## 6. Out of scope / do NOT

- No write or lifecycle actions (no dismiss/accept) — **read-only only**.
- No changes to scoring or the signals pipeline.
- **No `git push` / deploy without Nick's explicit greenlight in chat.**

---

## 7. Notes

- Keep the output shape attribution-friendly for the later committee-review-logging work (always include `signal_id`).
- The **3-10 oscillator stays in shadow** (audited 2026-06-04 — no edge over RSI-alone), so it won't surface in this feed unless promoted later.
