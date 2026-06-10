# B4 Chunk B — Webhook Hardening + Cutover Runbook

**Date:** 2026-06-09 | **Author:** Claude Code | **For:** architecture-layer review, then cutover night
**Status:** Code written & syntax-clean, **NOT deployed.** Deploy is Step 3 of the cutover. Review this runbook before cutover night.
**Preconditions cleared:** indicator confirmed PRIVATE → Pine-source secret approved. v2.4 source transcribed to `docs/pythia-market-profile-v2.4.pine`.

---

## Census-driven reframing (why the target moved)

The live PYTHIA feed does **not** hit `/api/webhook/pythia` or `/webhook/mp_levels` directly. One armed TradingView alert (**PREY LIST**, "Any alert() function call") POSTs to the **`/webhook/tradingview`** router. That router (`tradingview.py:207-213`) detects `source=="pythia"` and **early-returns to `pythia_webhook(payload=...)` BEFORE its own secret check (lines 217-221).** So:

- The live feed is **unauthenticated** — the secret gate is bypassed by the dispatch.
- Adding a secret to comFields alone does nothing unless the **forward target** enforces it.
- **The chokepoint is `pythia_webhook` itself** — it serves both the router-forward (live) and any direct hit. Enforcing there covers every path with one change. (`/webhook/mp_levels` is dormant — no live writer — but is hardened too, defense in depth.)
- The Level Sheet script is dormant; `/webhook/mp_levels` has no live writer.

**Root cause of the feed degradation:** TradingView freezes a script's code into an alert at creation time. The live PREY LIST alert binds **pre-v2.4** code carrying the "watchlist tickers not calculated" bug. The re-arm (delete + recreate) rebinds **v2.4**, whose changelog fixes exactly that bug → **feed restoration is an expected cutover outcome**, not a side effect.

---

## Code changes (written, ready — deploy on cutover night)

All three files are syntax-checked and staged locally; **do not push until Step 3** (a pre-re-arm deploy would 401 the live feed).

### 1. `backend/webhooks/pythia_events.py` — `pythia_webhook` (the chokepoint)
- **Size cap:** body > 8 KB → **413**.
- **Shared secret:** `PYTHIA_WEBHOOK_SECRET`, `hmac.compare_digest` (constant-time). **Fail-closed:** env unset → **503**; missing/wrong → **401**.
- **Secret stripped** from the dict before any `logger.*` and before `raw_payload` persistence.
- **Required fields:** `vah`, `val`, `poc` present + numeric + **> 0** → else **400**, no insert. (Rejects the `nz(x,0)` confident-zeros v2.4 emits when levels aren't computed.)
- **0.0 → null** for `ib_high`/`ib_low` (and `prev_*` on the read side) — confident zero is not data.

- **R-4:** Content-Length pre-check (reject oversized bodies before reading them) added to the direct-hit path — ≤5 lines, per PM.

### 2. `backend/webhooks/mp_levels.py` — same secret gate + Content-Length pre-check + size cap + secret-strip (dormant endpoint, hardened anyway).

### 3. `backend/services/read_only/market_profile.py` (Chunk A read) — `prev_*`/`ib` `0.0 → null` for contract consistency. Read-only, shadow-safe; bundled into this deploy to avoid a second hub_mcp redeploy.

**Blast radius:** only `pythia_webhook` + `mp_levels`. The `/webhook/tradingview` router, the main signal path, and FOOTPRINT are untouched.

---

## Exact `comFields` diff for Nick to paste (TradingView Pine editor, v2.4)

In `docs/pythia-market-profile-v2.4.pine` the `comFields` block ends at the `volume_quality` line (line 368). Change the **last line** and append two fields:

**FROM:**
```pine
     '"volume_quality":"' + volQuality + '"'
```
**TO:**
```pine
     '"volume_quality":"' + volQuality + '",' +
     '"secret":"PASTE_YOUR_SECRET_HERE",' +
     '"bar_time":"' + str.tostring(timenow) + '"'
```
Notes:
- `timenow` = alert **fire time** (epoch ms), not `time` (bar start) → tighter replay window. Emitted as a quoted string for deterministic parsing.
- `PASTE_YOUR_SECRET_HERE` = the **exact same value** Nick sets in the Railway env var (Step 1). Acceptable in Pine source because the indicator is **private/never published**.
- `comFields` is shared by **every** `alert()` call (val/vah/ib/rejections/poc) — editing it **once** covers all event types.

---

## The cutover (one evening, after-hours — NOT 09:30–16:00 ET)

**Ordering principle (zero data-gap):** TradingView must already be sending the secret **before** the enforcing code deploys. The current live `pythia_webhook` ignores the extra `secret` field, so the re-arm causes no breakage; after deploy, TV is already compliant. The small window between re-arm and deploy is a secret-*leak* window (cleaned in Step 5), not a data-*gap* window. Deploying first would 401 the live feed — do not.

### Step 1 — Nick: set the Railway env var
Railway → project `fabulous-essence` → service `pandoras-box` → Variables → add
`PYTHIA_WEBHOOK_SECRET` = `<32+ char random string>`.
*(Current deployed code doesn't read this for these endpoints, so it has no effect yet. If Railway auto-redeploys current code, it's a harmless ~60–170s MCP blip — fine off-hours.)*

### Step 2 — Nick: re-arm the TV alert (delete + recreate → rebinds v2.4 + adds secret/bar_time)
1. Confirm the v2.4 indicator on the chart has the `comFields` edit above saved (CC supplies the exact snippet).
2. TradingView → **Alerts** panel → **delete** the existing PREY LIST PYTHIA alert.
3. **Create** a new alert:
   - **Condition:** PREY LIST · **"Any alert() function call"**
   - **Webhook URL:** `https://pandoras-box-production.up.railway.app/webhook/tradingview`
   - Notification: Webhook URL enabled. (Message box is ignored for "Any alert() function call" — the body is the Pine `alert()` string, which now carries the secret.)
4. Save → the alert re-arms on **v2.4** and now sends `secret` + `bar_time`. **Secret-leak window starts** (note the wall-clock time).

### Step 3 — CC: deploy Chunk B
`git push origin main` (the three files) → Railway redeploys with enforcement. TV is already sending the secret → **zero data-gap**. **Secret-leak window ends** (note the time). Record the commit SHA for rollback.

### Step 4 — Verify (after-hours)
- **Auth:** `curl -X POST .../webhook/tradingview -d '{"source":"pythia","ticker":"TEST","vah":1,"val":1,"poc":1}'` (no secret) → **401**, no row.
- **Confident-zero reject:** same with correct `secret` but `"vah":0` → **400**, no row.
- **Happy path:** a real TV alert (or `curl` with correct secret + vah/val/poc > 0) → **200** + new `pythia_events` row; confirm **no `secret`** in Railway logs or in the row's `raw_payload`.
- **Feed restoration (the v2.4 win):** over the **next market session**, confirm event volume across **many tickers** (not just META/AMD/TSLA) — the watchlist bug is fixed.
- **Chunk A still live:** `hub_get_market_profile("SPY")` returns data; once a fresh SPY event lands post-cutover, SPY flips `stale → ok` (clears Chunk D's SPY regression ticker).

### Step 5 — Scrub the gap-window secret leak (AEGIS amendment)
Rows created in the Step 2 → Step 3 window were stored by the **old** handler, which did not strip `secret` from `raw_payload`. Remove it:
```sql
UPDATE pythia_events
SET raw_payload = raw_payload - 'secret'
WHERE raw_payload ? 'secret'
  AND timestamp >= '<Step-2 wall-clock UTC>';
```
Verify clean:
```sql
SELECT count(*) FROM pythia_events WHERE raw_payload ? 'secret';   -- must be 0
```
*(Run via the read-only-proxy/asyncpg path used for migrations. This is the only write in the cutover beyond the live feed.)*

---

## Rollback
If the cutover breaks the feed (e.g., secret mismatch → persistent 401), revert the code (fail-closed means unsetting the env var yields 503, not recovery):
```
git revert <Chunk-B SHA> && git push origin main
```
Railway redeploys the prior (unauthenticated) handler and the feed flows again. Then diagnose the secret mismatch and re-attempt. Keep the v2.4 re-arm — only the server code reverts.

**Rider 2 — the revert also reverts the Chunk A `0→null` rider** (`market_profile.py`, bundled in this commit). On re-attempt, re-apply that rider so `prev_*`/`ib` confident-zeros stay nulled.

---

## AEGIS checklist (cutover)
- [ ] `PYTHIA_WEBHOOK_SECRET` set in Railway; same value in Pine `comFields`; never logged.
- [ ] Constant-time compare; fail-closed (503) when unset.
- [ ] vah/val/poc present + numeric + > 0 or 400; no partial inserts.
- [ ] `secret` stripped before log + `raw_payload`.
- [ ] 8 KB size cap (413).
- [ ] `/webhook/mp_levels` hardened (dormant) with the same gate.
- [ ] Step 5 scrub run + verified zero `secret` keys remain.
- [ ] Gap window kept to one evening.
- [ ] **Rider 1:** `grep -r '<the real secret value>' .` across the repo → **0 hits** (the committed `.pine` keeps the `PASTE_YOUR_SECRET_HERE` placeholder forever; the real value lives only in Nick's TV editor + Railway env).

## Open confirmations for review
- **R-1:** Dedicated `PYTHIA_WEBHOOK_SECRET` (chosen) vs reusing `TRADINGVIEW_WEBHOOK_SECRET`. Dedicated keeps PYTHIA auth self-contained and avoids touching the main signal path — recommend keep.
- **R-2:** `bar_time` emitted as quoted epoch-ms string; Chunk C will parse `int(float(bar_time))`. Confirm acceptable.
- **R-3:** Size cap 8 KB — PYTHIA payloads are ~400 B; ample headroom. Confirm.
- **R-4:** ✅ RESOLVED — Content-Length pre-check added to both handlers (≤5 lines). Router-level raw-body cap remains deferred to the post-B4 global webhook-hardening brief (logged).

---

*Runbook ready for architecture review. No deploy until reviewed + cutover night. Chunk C (replay/idempotency on `bar_time`) and Chunk D (PYTHIA skill wiring + SPY regression go-live gate) follow.*
