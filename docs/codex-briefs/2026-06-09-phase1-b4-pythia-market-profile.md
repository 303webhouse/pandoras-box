# Phase 1 Build Brief — B4: PYTHIA Market Profile Feed

**Date:** 2026-06-09 | **Author:** Claude Code (from Phase 0 findings) | **Builder:** Claude Code
**Phase 0:** `docs/phase0-b4-findings.md` | **Master brief:** `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md` §B4
**Status:** DRAFT for architecture-layer review. **No code is written until this brief is reviewed and Nick relays the greenlight.**

---

## Locked decisions (Phase 0 §9, approved 2026-06-09)

1. ✅ **Revised auth model** replaces the impossible HMAC: shared-secret-in-payload (constant-time, fail-closed) + IP allowlist + replay window. (TradingView cannot compute an HMAC.)
2. ✅ **Reuse `pythia_events`** — no new `market_profile_snapshots` table.
3. ✅ **Pine payload edits allowed** (`secret`, `bar_time`) — Nick re-arms the TV alerts.
4. ✅ **Harden the two existing unauthenticated webhooks now** (`/api/webhook/pythia`, `/webhook/mp_levels`).
5. ✅ **Ship the tool with `single_prints`/`day_type` as explicit `null`** (Pine v2.3 doesn't compute them).

**Rider (a):** Chunk B's deploy and the TV alert re-arm are **one choreographed after-hours cutover**, spec'd step-by-step below including Nick's exact TradingView actions.
**Rider (b):** **Chunks A and B ship in this same brief, back-to-back.** The unauthenticated endpoints do not outlive this sprint.

---

## Why this shape

Phase 0 established that PYTHIA ingestion + storage already exist and run live (`pythia_events`, 9,666 rows, active today). The committee just can't *read* it. So:
- **Chunk A** closes the committee gap with a pure read tool (shadow-safe, zero new write surface).
- **Chunk B** closes the standing AEGIS gap (two open webhooks) — same brief, deployed right after A.
- **Chunk C** adds replay/idempotency (depends on a Pine field added during B's re-arm).
- **Chunk D** wires PYTHIA's skill and runs the mandatory SPY regression — the only chunk that changes committee behavior, hence the go-live gate.

Each chunk is independently shippable. Deploy order A → B → C → D. **No `backend/hub_mcp/` or webhook deploy during 09:30–16:00 ET** (severs the live Claude.ai MCP session ~60–170s).

---

## CHUNK A — `hub_get_market_profile` MCP tool (read-only, shadow-safe)

**Goal:** expose the already-flowing PYTHIA data to the committee as the 13th hub MCP tool. Pure read; no writes; no new surface.

### Files
1. **NEW** `backend/hub_mcp/tools/market_profile.py` — the tool.
2. **NEW** `backend/services/read_only/market_profile.py` — the read/compose layer (mirrors the `services/read_only/*` pattern used by other hub tools).
3. `backend/hub_mcp/decorators.py` — add `"hub_get_market_profile"` to `REGISTERED_TOOL_NAMES`.
4. `backend/hub_mcp/tools/__init__.py` — add `from . import market_profile as _market_profile  # noqa: F401`.
5. `backend/hub_mcp/tests/test_tools_smoke.py` — bump `tool_count` 12 → 13, add the name to the describe set, add a smoke test (mock the read layer; assert envelope + `unavailable` path).

### Read pattern (latest-row-only — GEX lesson)
Primary: latest `pythia_events` row for the ticker.
```sql
SELECT ticker, alert_type, price, direction, vah, val, poc,
       prev_vah, prev_val, prev_poc, va_migration, poor_high, poor_low,
       volume_quality, ib_high, ib_low, interpretation, timestamp
FROM pythia_events
WHERE ticker = $1
ORDER BY timestamp DESC
LIMIT 1;
```
- Confirm/add index `idx_pythia_events_ticker_ts ON pythia_events (ticker, timestamp DESC)` (check `pg_indexes` first; only create if absent — that index creation is the *only* DDL in Chunk A and is additive/non-locking via `CREATE INDEX CONCURRENTLY` if the table is hot).
- Note: `pythia_events.prev_*` columns are **not** in the table schema (Phase 0 confirmed columns: vah/val/poc/ib/va_migration/poor_high/poor_low/volume_quality/interpretation). The `prev_vah/prev_val/prev_poc` live in `raw_payload` (jsonb). Read them from `raw_payload` (the Pine `comFields` always include them). **Builder: confirm against a live row before finalizing the SELECT** — do not assume column names (UW/api_spec precedent).
- Redis fast-path: `pythia:{ticker}` (24h TTL) and fallback `mp_levels:{ticker}` carry the latest levels; use as a secondary source if the DB read is empty but Redis is warm. DB is source of truth for the full field set.

### Response envelope (matches existing hub tools)
`make_response(status, data, summary, staleness_seconds, error)` with:
```json
{ "status": "ok | stale | unavailable",
  "data": {
    "ticker","poc","vah","val","prev_poc","prev_vah","prev_val",
    "ib_high","ib_low","poor_high","poor_low","va_migration",
    "volume_quality","last_event","interpretation","price_at_event",
    "session_date","as_of","source":"pythia_webhook_v2.3",
    "single_prints": null, "day_type": null },
  "staleness_seconds": <int>, "schema_version":"v1.0", "error": null }
```

### Fail-loud / staleness rules
- No row for ticker → `status:"unavailable"`, `data:null`. **Never a fabricated default.**
- `single_prints` and `day_type` → **explicit `null`** with a `data.note` ("not computed by Pine v2.3"). Never invented.
- Staleness: compute `staleness_seconds = now − latest.timestamp`. During **RTH** (09:30–16:00 ET, weekday), if older than a threshold (proposed **45 min** — but see open item Q-A1), set `status:"stale"`. **Off-hours/weekend: expected freeze — return `status:"ok"`** with the last session's levels (they remain the current structural levels), mirroring composite off-hours behavior. Reuse the ET market-hours helper the composite/MTM loops already use.

### MCP tool DESCRIPTION (FastMCP) — conventions
Follow the existing hub-tool description style (when to call / what it returns / what NOT to use it for):
> "Returns the latest TradingView Market Profile levels for a ticker (POC, VAH, VAL, prior-session value area, initial balance, poor highs/lows, value-area migration, volume quality) as computed by the PYTHIA Pine indicator and pushed via webhook. Call when PYTHIA needs structural levels for a committee pass or when the user asks about value area, POC, IB, day structure, or the 80% rule. `single_prints` and `day_type` are not yet computed (null). Returns `unavailable` when no levels exist for the ticker and `stale` when the feed has gone quiet during market hours — never fabricated levels. Do NOT use for options structure (DAEDALUS) or trend (PYTHAGORAS)."

### Chunk A verification (shadow-safe; deploy off-hours but any day)
- `mcp_describe_tools` returns 13 tools incl. `hub_get_market_profile`.
- Live call on **SPY** (active ticker) returns real POC/VAH/VAL with `status:"ok"`, `as_of` recent.
- Live call on a junk ticker (`ZZZZ`) returns `status:"unavailable"`, `data:null` — no fabrication.
- `single_prints`/`day_type` are `null` with the note.
- No write occurred (read-only); `pythia_events` row count unchanged.

---

## CHUNK B — Harden both PYTHIA webhooks + choreographed cutover (AEGIS)

**Goal:** close the unauthenticated-write gap on `/api/webhook/pythia` (`pythia_events.py`) and `/webhook/mp_levels` (`mp_levels.py`). Ships in this brief, deployed right after Chunk A.

### Server-side changes (both handlers)
1. **Shared secret, constant-time, fail-closed.** New env var `PYTHIA_WEBHOOK_SECRET`.
   - If env **unset** → log ERROR, reject **503** (server can't validate → closed). *(Opposite of the existing `tradingview.py` fail-open.)*
   - If payload `secret` missing or `hmac.compare_digest(payload_secret, PYTHIA_WEBHOOK_SECRET)` is False → reject **401**, log WARNING (ticker only, never the secret).
2. **Required-field validation, fail-loud.** Require `ticker, vah, val, poc` all present and numeric → else **400**, no insert. (Replaces the current silent `float(x) if x else None` partial-row coercion.)
3. **Payload size cap.** Reject body > **8 KB** → **413**.
4. **Logging + persistence hygiene.** Strip `secret` from the dict before any `logger.*` call **and** before storing `raw_payload` (current handler stores `json.dumps(payload)` verbatim — would persist the secret).
5. **IP allowlist (defense-in-depth, app-level).** New env `PYTHIA_WEBHOOK_IP_ALLOWLIST` (comma-sep). Derive client IP from `X-Forwarded-For` taking the correct hop behind Railway's proxy. **Ship in log-only mode first** (log a WARNING on non-allowlisted IP but still process) to avoid locking out a stale TV IP; flip to enforce after one clean session confirms the real source IPs. Verify TV's current published webhook IPs against live TV docs at build time (they change).

### Decision: which URL(s) do PYTHIA alerts actually POST to?
**Builder pre-step (read-only):** confirm with Nick which endpoint his live PYTHIA TV alerts target — `/api/webhook/pythia`, `/webhook/mp_levels`, or both. The Pine v2.3 `alert()` payload (`{"source":"pythia",...}`) is shaped for `/api/webhook/pythia`. Harden whichever endpoint(s) receive live traffic; the secret value is shared across both.

### The choreographed after-hours cutover (rider a)
**Principle:** TradingView must already be sending the secret *before* the enforcing code goes live, so there is **zero data gap** (the current live code ignores the extra `secret` field; the new code requires it). Order:

**Step 1 — Nick sets the secret in Railway (after-hours).**
Railway dashboard → project `fabulous-essence` → service `pandoras-box` → Variables → add `PYTHIA_WEBHOOK_SECRET` = `<a long random string, 32+ chars>`. *(This alone does nothing yet — the live code doesn't read it for these endpoints. If Railway auto-redeploys current code, harmless.)* Optionally also add `PYTHIA_WEBHOOK_IP_ALLOWLIST` (leave blank to skip IP checks initially).

**Step 2 — Nick edits the TradingView alert(s) (after-hours).**
For **each** live PYTHIA alert (TradingView → Alerts panel → pencil-edit each PYTHIA Market Profile alert):
- In the **Message** box, the body is the JSON the Pine script emits. Nick adds **two fields** to the JSON (bundling Chunk C's `bar_time` now so TV is only touched once):
  - `"secret":"<same value as Step 1>"`
  - `"bar_time":"{{timenow}}"`
- *(Exact placement: these are top-level keys in the alert JSON. If the alert uses the Pine `alert()` string verbatim, Nick instead edits the Pine `comFields`/payload — see the Pine note below — re-saves the indicator, and re-creates the alert. CC will provide the exact edited JSON/Pine snippet at build time so Nick pastes, not authors.)*
- Save → the alert re-arms. **The current live server ignores the new fields → no breakage during this window.**

**Pine note:** if the secret/bar_time must be added in the Pine script (because the alert message is the raw `alert()` output), that's a small `comFields` edit (add `'"secret":"<value>",'` and `'"bar_time":"' + str.tostring(timenow) + '",'`). CC supplies the exact diff; Nick pastes it into the TradingView Pine editor, saves, and re-arms the alerts. **Putting a secret in the Pine source is acceptable only because the indicator is private to Nick's TV account** — confirm it is not a published/shared script before this route. The Message-box route (above) keeps the secret out of the Pine source and is preferred if the alert allows a custom message.

**Step 3 — CC deploys Chunk B (after-hours).** Push → Railway redeploys with secret enforcement. Incoming TV alerts already carry the secret → validated and stored. Any POST without the secret (attacker, stale cache) → 401.

**Step 4 — Verify (after-hours).**
- Trigger a TV test alert (or wait for a live one) → confirm **200** + a new `pythia_events` row.
- `curl -X POST .../api/webhook/pythia -d '{"ticker":"TEST","vah":1,"val":1,"poc":1}'` (no secret) → **401**, no row.
- `curl` with a partial payload (missing `poc`) + correct secret → **400**, no row.
- Confirm no `secret` value appears in Railway logs or in any `raw_payload` row.
- Confirm `hub_get_market_profile("SPY")` (Chunk A) still returns fresh data post-cutover.

### Chunk B verification summary
401 on no/bad secret · 400 on partial · 413 on oversized · 503 if env unset · secret never logged/persisted · live TV alert still lands · IP allowlist in log-only mode emits the real source IP for review.

---

## CHUNK C — Replay protection + idempotency

**Depends on:** `bar_time` already arriving (added during Chunk B's TV re-arm).

- **Replay window:** reject if `bar_time` is outside ±**10 min** of server receipt (tolerance for TV delivery lag + clock skew). Malformed/missing `bar_time` → log + treat as un-replayable (process once but flag), OR reject — **decide at review (open item Q-C1)**.
- **Idempotency:** dedup key `(ticker, event, bar_time)`. On duplicate (TV retries on non-2xx) → no-op, return 200 with `{"status":"duplicate"}`. Implement via a Redis SETNX key `pythia_seen:{ticker}:{event}:{bar_time}` (TTL ~30 min) — no schema change.

**Verification:** replay the same payload twice → one row, second returns `duplicate`. Send a `bar_time` 30 min old → rejected. No new write surface; pure additive validation.

---

## CHUNK D — PYTHIA skill wiring + SPY regression (GO-LIVE GATE)

**This is the only chunk that changes committee behavior. It does not ship until A–C are verified live.**

### Skill edit
`skills/pythia/SKILL.md`:
- Add `hub_get_market_profile(ticker=<the ticker>)` to PYTHIA's Context-A tool-call order (after `hub_get_quote`, before/around `hub_get_flow_radar`).
- Update the "PYTHIA-specific data caveat" block: when the tool returns `ok`, PYTHIA uses the real levels; when `stale`/`unavailable`, the existing "MP data not provided — framework only" disclaimer still fires (no fabrication).
- Re-run the skill packager (`scripts/package-skill.ps1 pythia`), produce `dist/skills/pythia.skill`, Nick re-uploads to Claude.ai.

### Mandatory SPY full-committee regression (the gate)
1. Confirm SPY has a recent `pythia_events` row (it's among the 174 active tickers).
2. Run a **full Olympus committee pass on SPY** with the feed live. PYTHIA must call `hub_get_market_profile` and populate her LEVELS block with the real POC/VAH/VAL.
3. Compare to the no-feed baseline (PYTHIA previously emitted "MP data not provided").
4. **Pass criteria (all required):**
   - (a) PYTHIA uses the real levels when `status:"ok"`.
   - (b) When the tool returns `stale`/`unavailable` (test by querying a quiet ticker), PYTHIA **does not fabricate** — the disclaimer fires. (TORO-2026-05-21 fabrication-incident class must not recur.)
   - (c) TORO/URSA/PYTHAGORAS/THALES/DAEDALUS/PIVOT outputs unchanged in shape/behavior.
   - (d) No agent simulates another; PYTHIA stays in her structural lane.
5. Record in `docs/strategy-reviews/b4-pythia-feed-closure-note-<date>.md`. **No go-live without this note.**

---

## AEGIS checklist (consolidated)
- [ ] `PYTHIA_WEBHOOK_SECRET` in Railway env; never in repo; never logged.
- [ ] Constant-time comparison (`hmac.compare_digest`); **fail-closed** when unset.
- [ ] Required fields (ticker, vah, val, poc) or reject 400 — no partial inserts.
- [ ] `secret` stripped before logging and before `raw_payload` persistence.
- [ ] Body size cap (8 KB → 413).
- [ ] IP allowlist (verified current TV IPs), log-only → enforce.
- [ ] Replay window + `(ticker, event, bar_time)` idempotency.
- [ ] Both `/api/webhook/pythia` and `/webhook/mp_levels` hardened.
- [ ] Pine secret route confirmed safe (private indicator) if secret added in Pine source.

---

## Sequencing & gates
| Chunk | Ships | Gate before next |
|---|---|---|
| A — MCP read tool | off-hours, any day | live verify (SPY ok, junk unavailable, nulls correct) |
| B — webhook hardening + cutover | **same brief as A, right after** | the 4-step cutover verification passes |
| C — replay/idempotency | after B's `bar_time` is flowing | duplicate→no-op, stale→reject |
| D — skill wiring + SPY regression | after A–C verified live | **closure note = go-live gate** |

A and B are non-negotiably in this one brief (rider b). A is shadow-safe immediately; B's cutover is the choreographed after-hours op (rider a). D gates go-live.

---

## Env vars Nick must provision
- `PYTHIA_WEBHOOK_SECRET` (required for Chunk B) — 32+ char random string; same value in Railway env and the TV alert payload.
- `PYTHIA_WEBHOOK_IP_ALLOWLIST` (optional, Chunk B) — comma-sep TV source IPs; blank = skip IP check.

## Open items for architecture-layer review
- **Q-A1:** RTH staleness threshold for `status:"stale"` — proposed 45 min (events are sparse, ~120-min cooldowns; too tight = false-stale, too loose = misses a dead feed). Confirm value.
- **Q-A2:** Confirm `prev_vah/prev_val/prev_poc` are read from `raw_payload` jsonb (not columns) against a live row before finalizing the SELECT.
- **Q-B1:** Which endpoint(s) do Nick's live PYTHIA alerts POST to — `/api/webhook/pythia`, `/webhook/mp_levels`, or both?
- **Q-B2:** Secret via TV **Message box** (preferred, keeps it out of Pine source) vs **Pine `comFields`** (only if the alert can't carry a custom message and the indicator is private)?
- **Q-C1:** Missing/malformed `bar_time` — process-once-and-flag, or reject?

---

*End of Phase 1 build brief. No code written. Returns to the architecture layer for review; Nick relays the greenlight before Chunk A is built.*
