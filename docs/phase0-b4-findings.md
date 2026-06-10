# Phase 0 Findings — B4: PYTHIA Market Profile Feed (`hub_get_market_profile`)

**Date:** 2026-06-09 | **Analyst:** Claude Code | **Mode:** Read-only investigation
**Status:** Gate report — awaiting Nick greenlight before any build.
**Repo state at investigation:** `main` @ `84d5df5`, clean (untracked files only).

---

## TL;DR — the brief's framing is partly overtaken by reality

1. **B4 is NOT the hub's first external write surface.** There are 7+ live inbound webhook routers (`tradingview`, `circuit_breaker`, `whale`, `footprint`, `hermes`, `pythia_events`, `mp_levels`). The AEGIS risk is not "first surface" — it's "**two existing PYTHIA write surfaces are completely unauthenticated and live.**"
2. **The PYTHIA ingestion + storage already exist and are actively running.** `/api/webhook/pythia` writes the full v2.3 payload to the `pythia_events` table (9,666 rows, 81 in the last 7 days, most recent **today 19:30 ET**, 174 tickers) + Redis `pythia:{ticker}`. The Pine script already builds the alert JSON.
3. **The actual gap is the MCP read tool.** The *scorer* already consumes PYTHIA data (`get_pythia_profile_position`, pipeline P4B). The *committee* (Claude.ai PYTHIA skill) cannot — it has no `hub_get_market_profile`. That tool is the real deliverable.
4. **HMAC is not achievable with TradingView** (no crypto in alert templating) — the master brief's "HMAC-validated webhook" requirement must be revised to **shared-secret-in-payload + IP allowlist + replay window**.
5. **Two fail-loud violations exist in the current handler** (partial-payload coercion, no idempotency) and must be fixed as part of hardening.

---

## 1. Webhook surface inventory (T2) — "first external write surface?" → **NO**

`backend/webhooks/` contains live routers, all mounted in `main.py`:

| Router | Route(s) | Mount prefix | Actual URL | Auth today |
|---|---|---|---|---|
| `tradingview.py` | `/tradingview`, breadth, TICK, McClellan | `/webhook` | `/webhook/tradingview` | ✅ shared-secret-in-payload (`secret` field vs `TRADINGVIEW_WEBHOOK_SECRET`) |
| `circuit_breaker.py` | … | `/webhook` | … | (shares pattern) |
| `whale.py`, `footprint.py` | … | `/webhook` | … | varies |
| `hermes.py` | … | `/api` | … | varies |
| **`pythia_events.py`** | `/webhook/pythia` | `/api` | **`/api/webhook/pythia`** | ❌ **NONE** |
| **`mp_levels.py`** | `/mp_levels` | `/webhook` | **`/webhook/mp_levels`** | ❌ **NONE** |

**Verdict:** B4 reuses/hardens an existing pattern; it does not introduce the first write surface. **But the two PYTHIA endpoints are unauthenticated** — anyone who knows the URL can POST arbitrary MP levels into `pythia_events`/Redis, which feed the live scorer. This is the pre-existing AEGIS gap the master brief §3 flagged ("Confirm existing TV webhooks validate … Absence = AEGIS veto"). **Confirmed: they do not validate.**

### The existing auth pattern (reusable, with caveats)
`tradingview.py` (used on 4 webhooks):
```python
WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET") or ""
if WEBHOOK_SECRET:                                  # ← FAIL-OPEN if env unset
    if (payload.secret or "") != WEBHOOK_SECRET:    # ← plain !=, NOT constant-time
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
```
Weaknesses to fix in B4: (a) **fail-open** when env var unset, (b) **non-constant-time** comparison, (c) **PYTHIA webhooks don't use it at all.**

---

## 2. Pine payload spec (T1)

`docs/pythia-market-profile-v2.3.pine` is an indicator that computes a session volume profile and **already emits alert JSON** (no Phase-1 Pine work needed to *build* the payload — only to *add a secret + timestamp*, see §5).

**Values computed:** POC, VAH, VAL (volume-profile value area, 70% default); prior-session pVAH/pVAL/pPOC; IB high/low (09:30–10:30 ET); poor high / poor low (>5% volume at extreme bin); volume_quality (high/normal/thin via relative volume); va_migration (higher/lower/overlapping/unknown).

**Events emitted** (`alert(...)`, `freq_once_per_bar`, independent 120-min cooldowns):
`val_cross_below`, `vah_cross_above`, `ib_break_up`, `ib_break_down`, `vah_rejection`, `val_rejection`, `poc_acceptance`, `poc_rejection`.

**Payload shape today** (`comFields`, lines 329–342) — every event carries:
```json
{"source":"pythia","event":"<event>","ticker":"…","price":…,
 "val":…,"vah":…,"poc":…,"prev_val":…,"prev_vah":…,"prev_poc":…,
 "va_migration":"…","ib_high":…,"ib_low":…,
 "poor_high":true|false,"poor_low":true|false,
 "volume_quality":"high|normal|thin","interpretation":"…"}
```

**Cadence:** event-driven (threshold crossings only), max once per cooldown window (~120 min) per event type per ticker — **sparse**, a handful per ticker per session. NOT a per-bar snapshot. Implication: between events, "latest levels" persist as the current session's levels and may be legitimately hours old.

**Gaps vs what PYTHIA wants (see §3):** payload does **NOT** include `single_prints`, `day_type`, a **secret**, or a **timestamp/bar-time**. Single prints and day-type are not computed by v2.3 at all.

---

## 3. `hub_get_market_profile` data contract (T3)

PYTHIA's skill (`skills/pythia/SKILL.md`) documents the need and **already names `hub_get_market_profile`** as the planned tool (lines 72–78, 165). PYTHIA's output template wants: POC, VAH, VAL, value area, IB, single prints, poor high/low, day type, prior-session values, 80%-rule inputs, va_migration, volume_quality.

Proposed envelope (matches existing hub tools — `status`/`data`/`summary`/`staleness_seconds`/`schema_version`/`error`):
```json
{
  "status": "ok | stale | unavailable",
  "data": {
    "ticker": "SPY",
    "poc": 597.2, "vah": 599.1, "val": 595.4,
    "prev_poc": 596.0, "prev_vah": 598.0, "prev_val": 594.1,
    "ib_high": 598.5, "ib_low": 595.9,
    "poor_high": false, "poor_low": true,
    "va_migration": "higher",
    "volume_quality": "high",
    "last_event": "vah_rejection",
    "interpretation": "…",
    "price_at_event": 598.9,
    "session_date": "2026-06-09",
    "as_of": "2026-06-09T19:30:56Z",
    "source": "pythia_webhook_v2.3",
    "single_prints": null,        // NOT in feed — explicit null, never fabricated
    "day_type": null              // NOT in feed — explicit null, never fabricated
  },
  "staleness_seconds": 1200,
  "schema_version": "v1.0",
  "error": null
}
```
**Fail-loud rule:** `single_prints` and `day_type` are not produced by Pine v2.3 → return **explicit `null` with a note**, never a confident default (GEX lesson). If no row for the ticker → `status:"unavailable"`, `data:null`. PYTHIA's skill already has the correct fallback prose ("MP data not provided — framework only").

---

## 4. MCP registration pattern (T4)

Registry lives in `backend/hub_mcp/`. Current `REGISTERED_TOOL_NAMES` has **12** entries (the docstring saying "10th tool" is stale). Adding the 13th requires **three edits**:
1. `decorators.py` — add `"hub_get_market_profile"` to the `REGISTERED_TOOL_NAMES` frozenset (hard assert at import; server won't boot otherwise).
2. `tools/__init__.py` — add `from . import market_profile as _market_profile  # noqa: F401`.
3. New `tools/market_profile.py` — `@mcp_tool(name="hub_get_market_profile", description=…)` returning `make_response(...)`.

Plus update the stale smoke-test assertions in `tests/test_tools_smoke.py` (`tool_count == 12` → `13`, add to the name set) — same chore done for `hub_get_trade_ideas`.

**Restart caveat:** per PROJECT_RULES.md, any `backend/hub_mcp/` change triggers a Railway redeploy that **severs the active Claude.ai MCP session for ~60–170s** → do NOT deploy during 09:30–16:00 ET. No restart pattern beyond the normal deploy window.

---

## 5. Storage design (T5) — **recommend reusing `pythia_events`, not a new table**

`pythia_events` already exists with exactly the right columns: `id, ticker, alert_type, price, direction, vah, val, poc, va_migration, poor_high, poor_low, volume_quality, ib_high, ib_low, interpretation, raw_payload (jsonb), timestamp (timestamptz)`. Redis `pythia:{ticker}` (24h TTL) and `mp_levels:{ticker}` carry the latest levels for fast reads.

**Recommended read pattern (latest-row-only, GEX lesson):**
```sql
SELECT * FROM pythia_events
WHERE ticker = $1
ORDER BY timestamp DESC
LIMIT 1;
```
with an index `CREATE INDEX idx_pythia_events_ticker_ts ON pythia_events (ticker, timestamp DESC);` (confirm it doesn't already exist before adding). The MCP tool reads the latest row + applies the §6 staleness guard. **No new table needed.**

A dedicated `market_profile_snapshots` table would **duplicate** existing storage — recommend **not** building it unless a future need for a clean one-row-per-ticker materialized view emerges. If Nick wants it anyway, draft DDL (next migration number, **draft only**):
```sql
-- OPTIONAL / NOT RECOMMENDED (pythia_events already covers this)
CREATE TABLE IF NOT EXISTS market_profile_snapshots (
    ticker        VARCHAR(16) PRIMARY KEY,         -- one row per ticker (latest)
    poc NUMERIC, vah NUMERIC, val NUMERIC,
    prev_poc NUMERIC, prev_vah NUMERIC, prev_val NUMERIC,
    ib_high NUMERIC, ib_low NUMERIC,
    poor_high BOOLEAN, poor_low BOOLEAN,
    va_migration VARCHAR(16), volume_quality VARCHAR(16),
    last_event VARCHAR(32), session_date DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Retention: `pythia_events` grows ~80 rows/week — trivial; no retention policy needed near-term.

---

## 6. Security design (T6) — AEGIS lane, the heart of Phase 0

### TradingView capability constraints (verified against codebase evidence)
- **No custom HTTP headers** — CONFIRMED. *Every* existing webhook authenticates via an in-payload `secret` field, never a header. The codebase already designed around this limitation. (External TV-docs confirmation should still be re-checked at build time.)
- **No HMAC possible** — TV alert templating substitutes static placeholders (`{{ticker}}`, `{{close}}`) into a fixed body; it has no crypto functions to compute an HMAC of the body. **The master brief's "HMAC-validated webhook" is not achievable with TV** and must be revised. Shared-secret-in-payload is the only viable cryptographic auth.

### Recommended auth model (defense in depth)
1. **Shared secret in JSON payload** (primary). Add `"secret":"{{...}}"` to the Pine alert payload. Server compares with **`hmac.compare_digest`** (constant-time) against `PYTHIA_WEBHOOK_SECRET` (Railway env var). **Fail-closed:** if the env var is unset, **reject all** (opposite of the current `if WEBHOOK_SECRET:` fail-open). Strip `secret` before logging *and* before storing `raw_payload`.
2. **TradingView IP allowlist** (defense-in-depth, app-level). TV publishes ~4 webhook source IPs (historically `52.89.214.238`, `34.212.75.30`, `52.32.178.7`, `52.89.214.238`) — **must be verified against TV's live docs at build time; they change.** Railway's proxy has no edge WAF, so enforce app-level from `X-Forwarded-For` (take the correct hop, not the spoofable first element). Treat as secondary, never primary.
3. **Replay protection** — requires a payload timestamp the Pine script does NOT currently send. **Add `"bar_time":"{{time}}"`** (or `{{timenow}}`) to the Pine payload; server rejects if outside a tolerance window (e.g., ±10 min vs server receipt). Without it, only weak protection is possible.
4. **Idempotency** — dedup key `(ticker, event, bar_time)` once `bar_time` is in the payload; reject/no-op duplicates (TV retries on non-2xx).
5. **Payload size cap** — Starlette does not cap body size by default; add an explicit cap (e.g., reject > 8 KB).
6. **Logging hygiene** — never log the `secret` field; strip it from `raw_payload` before the DB insert (current handler stores `json.dumps(payload)` verbatim — would persist a secret once added).

### AEGIS checklist for the build
- [ ] `PYTHIA_WEBHOOK_SECRET` in Railway env, never in repo, never logged.
- [ ] Constant-time comparison (`hmac.compare_digest`).
- [ ] **Fail-closed** when secret env unset (reject, don't pass).
- [ ] Required fields present (ticker, vah, val, poc) or **reject 400** — no partial inserts.
- [ ] `secret` stripped before logging and before `raw_payload` persistence.
- [ ] Payload size cap enforced.
- [ ] IP allowlist (verified current TV IPs) as defense-in-depth.
- [ ] Replay window + idempotency key (needs Pine `bar_time` addition).
- [ ] Apply the same hardening to **both** `/api/webhook/pythia` and `/webhook/mp_levels`.

---

## 7. Failure-mode table (T7)

| Failure | Current behavior | Required B4 behavior |
|---|---|---|
| TV alerts stop arriving | latest row just ages silently | MCP tool: `status:"stale"` when latest `timestamp` older than threshold **during RTH**; staleness_seconds reported |
| Market closed (overnight/weekend) | events naturally freeze | Expected freeze — mirror composite off-hours behavior; do NOT flag stale outside RTH |
| Partial payload (missing vah/val/poc) | **FAIL-SILENT** — coerces to `None`, inserts partial row (`float(vah) if vah else None`) | **Reject 400**, no partial insert (fail-loud) |
| Duplicate delivery (TV retry) | **inserts duplicate rows** (no idempotency) | Idempotency key `(ticker, event, bar_time)` → no-op on dup |
| Unauthenticated POST | **accepted** | 401 (shared-secret, fail-closed) |
| Malformed JSON / oversized body | unhandled / unbounded | reject 400 + size cap, logged |
| No row for ticker on read | n/a (tool doesn't exist) | `status:"unavailable"`, `data:null` — never a fabricated default |

---

## 8. Olympus impact map + regression plan (T8)

**Committee artifacts referencing market-profile data:**
- `skills/pythia/SKILL.md` — names `hub_get_market_profile` (lines 78, 165), documents the current gap (lines 72–78), and lists PYTHIA's MCP call order (lines 65–68). **Wiring the new tool into PYTHIA's checklist is a SKILL EDIT** → triggers the Olympus regression requirement.
- `docs/committee-training-parameters.md` — M.01/M.02/M.04/M.05/M.06, F.01/F.02/F.08 (PYTHIA's structural rules).
- `backend/strategies/btc_market_structure.py` — separate crypto MP computation (not this feed).
- Scorer path: `get_pythia_profile_position()` (pipeline P4B) already consumes `pythia_events`/Redis — **unaffected by adding the read tool** (it reads the same store, doesn't change writes).

**Regression plan (GO-LIVE GATE, not optional):**
1. Pick **SPY** (known-good; confirm SPY is among the 174 active `pythia_events` tickers and has a recent row).
2. Run a full Olympus committee pass on SPY **with the feed live** — PYTHIA calls `hub_get_market_profile`, must use the real POC/VAH/VAL in her LEVELS block.
3. Compare against the **no-feed baseline** — PYTHIA currently emits "MP data not provided — framework only."
4. Verify: (a) PYTHIA uses real levels when available; (b) **no fabrication** when the tool returns `stale`/`unavailable` — the disclaimer still fires; (c) other agents (TORO/URSA/PYTHAGORAS/THALES/DAEDALUS/PIVOT) are unchanged; (d) the 2026-05-21 TORO fabrication-incident class of failure does not recur.
5. Record the pass in a closure note. No go-live without it.

---

## 9. Open questions for Nick / architecture layer

1. **HMAC is impossible with TV.** Approve the revised auth model (shared-secret constant-time + fail-closed + IP allowlist + replay window) in place of the master brief's "HMAC-validated webhook"?
2. **Reuse `pythia_events`, skip the new table?** Recommended. Confirm — or do you want the dedicated `market_profile_snapshots` materialized-latest table anyway?
3. **Pine payload additions** (`secret`, `bar_time`) require re-saving the TV indicator/alerts on your side. OK to include those as a Phase-1 Pine edit (small, you re-arm the alerts)?
4. **Harden the two existing unauthenticated webhooks now** (they're live and open today), even though they predate B4? Recommend yes — it closes a standing AEGIS gap.
5. **single_prints / day_type** aren't computed by Pine v2.3. Ship the tool returning them as explicit `null`, and treat adding them as a later Pine enhancement? (Recommend yes — don't block the tool on it.)

---

## 10. Recommended Phase 1 build chunks (smallest-first, each shippable in shadow)

**Chunk A — `hub_get_market_profile` MCP tool (read-only, zero new write surface).**
Reads latest `pythia_events` row + Redis, returns the §3 envelope with §6/§7 staleness + fail-loud rules. Add to registry (3 edits) + fix smoke-test counts. *Lowest risk — pure read of data already flowing. Independently shippable.* This alone closes the committee's data gap.

**Chunk B — Harden the two PYTHIA webhooks (AEGIS).**
Add shared-secret (constant-time, fail-closed), required-field validation (reject 400, no partial insert), size cap, secret-stripping before log/persist, to `/api/webhook/pythia` + `/webhook/mp_levels`. Pine edit: add `"secret"`. *Closes the standing AEGIS gap. Ship after Chunk A so the read path is proven first.*

**Chunk C — Replay/idempotency.**
Pine edit: add `"bar_time"`. Server: timestamp tolerance window + `(ticker, event, bar_time)` idempotency. *Depends on Chunk B's Pine re-arm; smallest incremental.*

**Chunk D — PYTHIA skill wiring + Olympus regression (GO-LIVE GATE).**
Add `hub_get_market_profile` to PYTHIA's checklist; run the §8 SPY regression; closure note. *Last — the only chunk that changes committee behavior, hence the gate.*

Sequencing: A → B → C → D. A is shadow-safe immediately (read-only). D is the go-live gate.

---

*Phase 0 complete. No code, schema, migrations, or deploys performed. Awaiting greenlight on the build brief (and the §9 decisions) before Phase 1.*
