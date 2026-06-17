# Catalyst Tab v0 — Closure Note (2026-06-12, IPO morning / SPCX)

Brief: `docs/codex-briefs/2026-06-12-catalyst-tab-hotfix-v0.md` (Tasks A, B, C, D).
Market-hours deploy under explicit Nick override (recorded in the brief). Additive-only.

## Deploys

| SHA | Scope | Pushed (UTC) | Live (UTC) | app.js |
|-----|-------|--------------|------------|--------|
| `79be1b2` | Task A backend route + Task B Catalyst tab | 14:21:38 | 14:24:30 (08:24:30 MDT) | v=160 |
| `bfcf34d` | Task D hits strip + Web Audio + `_sv` fix + 🧪 TEST badge | 14:36:14 | 14:38:09 (08:38:09 MDT) | v=161 |
| `b1a04cf` | Task E catalyst↔signal confluence flag (pipeline hook) | 21:06:11 | 21:08:22 (15:08:22 MDT) | v=162 |

Final live SHA: **`b1a04cf`** (main). A/B/D met the morning gate (green by **08:38 MDT**, ahead of 09:30).
Task E was built + boot-tested in the morning and pushed in calm air post-close (Nick flat) per E.8.

## C.3 four-point verification

### Initial (v=160, `79be1b2`)
1. **Hub liveness** — `GET /health` → 200 @ 14:26 UTC (08:26 MDT).
2. **Dashboard loads** — `GET /app` → 200, served `app.js?v=160` @ 14:24:30 UTC.
3. **Catalyst tab renders** — `data-tier="catalyst"` + `#catalystFeed` present in served HTML.
4. **Test event → card** — POST `/api/catalyst/manual` → 200, id `59b64f74…`; row in
   `catalyst_events` @ 14:27:04 UTC; returned as first item of `/api/hermes/alerts`.

Bug caught by the empirical check: `/api/hermes/alerts` serializes `sector_velocity` as a
JSON **string** (jsonb), so initial-load cards rendered near-empty. Fixed in v=161 via `_sv()`.

### Re-verify (v=161, `bfcf34d`) — all GREEN
1. **Hub liveness** — `GET /health` → 200 @ 14:38:22 UTC (08:38 MDT).
2. **Dashboard loads** — `GET /app` → 200, served `app.js?v=161`.
3. **Catalyst tab + Task D elements** — `#catalystFeed`, `#catalystHits`, `#catalystHitCards`,
   `#catalystSoundBtn` all present; deployed `app.js` contains `isTargetedHit` + `_testChip`.
4. **Synthetic event renders correctly** — event `59b64f74…` in read path; `_isTestEvent=True`
   (🧪 TEST chip), `isTargetedHit=True` (pins as ★ TARGET), card body non-empty via `_sv`.

## ⚠️ Synthetic demo event — NOT a live signal

A single verification event was injected. It is **TEST-badged in the UI** and listed here so it
is never mistaken for a live trade signal:

- **id:** `59b64f74-e96e-4de1-87a0-ff5b1fbf8248`
- **created_at:** 2026-06-12 **14:27:04 UTC** (08:27:04 MDT)
- **source:** `c3_verify_test` · `flow_cluster` · SPCX · dominance 0.83 · "Scenario A index confirm — C3 verify"
- Renders with a **🧪 TEST** chip and pins to 🎯 Targeted Hits (it satisfies `isTargetedHit`).

Real scanner events use `source="flow_scanner_v2"` and carry no TEST chip. No other synthetic
events were created.

## Task D — decisions / notes

- **`isTargetedHit` predicate** (single editable function, `DOMINANCE_HIT = 0.80`):
  - `dp_block` → **always** a hit (Nick-approved). Resolves the D.1 conflict: the brief's prose
    ("every SPCX dark-pool block is a targeted hit") vs the literal "ALL hold" conjunction. The
    scanner tags DP blocks `scenario="institutional absorption level"` (not a live-scenario
    string), so the literal reading would make **no DP block ever fire** — contrary to intent.
  - `flow_cluster` → hit when `dominance ≥ 0.80` **and** scenario matches `Scenario A|Scenario
    B|forced-selling`.
  - Predicate self-test: **7/7 cases pass** (node).
- **Sound** — self-contained Web Audio (two tones ~150ms), behind a one-time "🔔 Enable sound"
  gesture, 3s debounce. Visual pin always fires; sound is enhancement only. Beep/pin DOM is
  inherently browser-side — confirm visually in your browser (the TEST event above pins on load).
- **Severability** — Task D rode Task B and was built only after B's live cards verified.

## Task E — Catalyst↔Signal confluence flag (v=162, `b1a04cf`)

Extends the existing event-driven hook in `signals/pipeline.py` (adjacent to the lightning-card
hook), after the signal persists. On a same-ticker catalyst event within `CONFLUENCE_WINDOW_MIN`
(15), it dedupes via Redis SETNX and writes a `confluence_flag` via `_store_catalyst_event` +
WS broadcast — rendering in the Catalyst tab automatically (pins + beeps via Task D).

- **Matching**: `dp_block` is direction-agnostic (`direction_match="dp_agnostic"`); `flow_cluster`
  requires aligned direction (`direction_match="aligned"`).
- **FAIL-OPEN (E.3)**: entire check wrapped try/except, double-wrapped at the call site. Confluence
  never blocks, delays, or breaks signal emission.
- **Untouched (E.6)**: no scoring, no `signals` schema, no `confluence/engine.py`, no auth.
  Writes ONLY via `_store_catalyst_event`. The 15-min batch confluence engine (`main.py:220`) was
  not modified — it remains the weekend home for the richer version.

### E.7 verification — all GREEN
- Local boot test: `py_compile` + import of `signals.pipeline` (helper present, `_norm_dir` correct).
- **Pre-push e2e** (flow_cluster aligned case) and **post-deploy e2e** (dp_block dp_agnostic case),
  both against live prod DB/Redis via the public proxy, TEST-labeled and auto-cleaned:
  - 1 flag on match · **SETNX dedupe held** on re-run (still 1) · **0** on a signal with no catalyst.
  - Post-deploy headline: `CONFLUENCE — Holy_Grail signal aligns with dp_block on ZZTEST (context,
    not entry timing)`; cleanup left 0 rows.
- Deploy health: 200 after the normal restart window (502s t+50–100s), **no crash-loop** from the
  core `pipeline.py` change.

### ⚠️ Synthetic E2E events — NOT live signals (all cleaned up)
The confluence e2e used sentinel tickers **`ZZTEST` / `ZZNOCAT`** with `source="etest_confluence_TEST"`
and TEST headlines. All rows were deleted at end of each run (verified 0 remaining). Redis dedupe
keys (`catalyst:confluence:etest-*`) were also deleted. No `ZZTEST`/`ZZNOCAT` rows persist.

### E.9 — Calibration note (REQUIRED)
`confluence_flag` is **CONTEXT-ONLY** until **n ≥ 50** flagged events are backtested against the
non-confluence baseline (hit rate + lead/lag `delta_seconds` distribution). **No agent, card, or
sizing logic treats it as conviction input before that gate.** Primary v0 purpose is data capture
on a record-volatility day. URSA requirement honored: payload carries `strategy` so backtests can
separate independent-source confluence (price-based, e.g. Holy_Grail) from shared-source echo
(flow-derived scanners confirming flow clusters — same UW well, not independent).

## Unchanged / gates honored
- No schema changes, no scheduler/scoring/webhook-auth changes, no new unauthenticated routes
  (`/api/catalyst/manual` is behind `require_api_key`), no secrets logged. Existing tabs untouched.
- PowerShell `flow_scanner.py` ran throughout as the independent fallback radar (untracked,
  not deployed). Rollback path (`git revert HEAD && git push`) not needed.
