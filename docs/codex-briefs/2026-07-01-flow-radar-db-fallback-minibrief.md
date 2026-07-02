# CC Mini-Brief — flow_radar Redis Outage: flow_events DB Fallback + Write-Failure Visibility

**Date:** 2026-07-01 · **Owner:** CC (build) / Claude (verify) / Nick (greenlight)
**Status:** READY FOR CC — small scope, read-path only. Parent: P0.1 RCA in the Triton Step-0 brief (§9.4).
**Problem class:** honest-but-blind — the committee's live flow read went dark for a full RTH session while the data existed.

---

## 0. What happened (7/1) — plain terms

The flow poller writes to two places: **Redis/Upstash** (the fast scratchpad that `hub_get_flow_radar` reads) and **Postgres `flow_events`** (the durable ledger). On 7/1, a transient Upstash write failure during RTH left the scratchpad empty while the ledger kept filling normally. The radar read the empty scratchpad and reported "0 events / flow_data_available: false" all day — honest, but the committee flew blind on data we actually had. Poller, UW quota, and the table were all healthy (RCA, Triton Step-0 P0.1).

## 1. The locked contract (from the 7/1 Olympus pass — non-negotiable)

Any fallback must LABEL itself. The radar payload (REST + `hub_get_flow_radar` MCP passthrough) gains:
- `source`: `"redis"` (normal) · `"db_fallback"` (Redis empty/error, served from `flow_events`) · `"none"` (both empty)
- `data_age_seconds`: now − newest event timestamp in the returned set; `null` when no events. **NEVER default to 0** — a fabricated-fresh fallback is exactly the fake-healthy bug class we hunt.

## 2. Phase 0 (read-only — report findings before building)

1. **Poller write-failure handling today:** what does the poller do when the Redis write throws — swallow silently? (That is how 7/1 stayed invisible.) Identify the exact write call-sites for the canonical `uw:flow:*` keys.
2. **flow_events read shape:** confirm the timestamp column + any index; expected volume ~1.4k rows/RTH day, so a time-window `SELECT … ORDER BY ts DESC LIMIT n` should be cheap. If an index is missing, flag it — don't migrate unless trivial.
3. **Radar read path:** locate where the REST endpoint / MCP tool assembles the payload from Redis, and the cleanest seam for the fallback.
4. Confirm **zero UW calls** anywhere in this path (DB + Redis only — governor untouched).

## 3. Build (small chunks, one commit each)

- **F1 — Fallback read:** in the radar assembly path: try Redis → on error OR zero events for the lookback window → query `flow_events` for the same window (bounded LIMIT) → serve with `source:"db_fallback"` + computed `data_age_seconds`. Happy path unchanged except it now carries `source:"redis"` + age. Both empty → today's honest empty + `source:"none"`.
- **F2 — Write-failure visibility:** poller Redis-write failures log WARNING with a distinct greppable tag, and `GET /api/uw/health` gains `flow_redis: {last_successful_write_age_seconds, status}` — mirror of Triton's B4 line — so an Upstash outage is visible same-day instead of via a dark radar.
- **F3 (only if trivial, ~10 lines):** retry-once with short backoff on the poller's Redis write. If bigger, skip — F1+F2 are the durable fix.

## 4. Guardrails

Read-path only · no schema migrations · no scoring/pipeline/L1a coupling · no new pollers · zero UW budget impact. Committee behavior: the age field feeds the EXISTING stale-degradation rules — do NOT hardcode a new staleness threshold. Frontend `db_fallback` badge = out of scope (HELIOS ticket later). Repo discipline + deploy windows per house rules.

## 5. Verification (CC runs, Claude re-verifies from a chat session)

1. Force the fallback via a temporary env flag (e.g., `FLOW_RADAR_FORCE_DB_FALLBACK=true`) or a test seam — do NOT flush prod Redis keys. Confirm payload: `source:"db_fallback"`, sane `data_age_seconds`, events match `flow_events` rows.
2. Normal path: `source:"redis"` + age present.
3. `hub_get_flow_radar` (MCP) surfaces both fields end-to-end.
4. Health line shows a real `last_successful_write_age_seconds` during RTH.

## 6. Out of scope

Upstash provider swap/hardening · UI changes · L1a gate changes · any write-path restructuring beyond F2/F3.
