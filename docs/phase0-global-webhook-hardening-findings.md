# Phase 0-lite — Global Webhook-Hardening Census (read-only findings)

**Authored:** 2026-06-10 22:03 UTC (16:03 MDT) · **Mode:** investigation-only, no code touched
**Source brief:** `docs/codex-briefs/post-b4-webhook-hardening-backlog.md` (#1 + sweep)
**Scope guard:** did NOT touch `backend/scoring|signals|enrichment` (other session's territory).
Read-only into `signals/pipeline.py` to document FOOTPRINT blast radius only.

---

## TL;DR

- **9 inbound POST webhook handlers.** Only **3 are hardened** to the B4/AEGIS standard
  (`mp_levels`, `pythia`, and the `circuit_breaker` *management* routes). The rest are
  either **fail-open** (secret skipped when env unset, plain `!=` compare) or **no auth at all**.
- **Brief #1 is partially overtaken by events.** `footprint_webhook` now has its *own*
  secret gate (footprint.py:219-224), so a FOOTPRINT POST forwarded from the TV router is
  **no longer fully unauthenticated** — but that gate is **fail-open + non-constant-time**,
  not the AEGIS fail-closed standard. The fix was started, not finished. (Details in §2.)
- **Only 1 of the 8 live alert families already sends a secret:** Trojan-Horse (footprint).
  Everything else must be **re-armed** before any server-side gate can flip to fail-closed,
  or live feeds 401/503 and go dark.
- **Hermes is the single Message-box family** (no Pine in repo → JSON hand-authored in the
  TV UI). All other families are Pine `alert()`-style. This drives the re-arm effort split.

---

## 1. Per-endpoint auth table

Prefixes from `backend/main.py:1095-1150`. "Fail-open" = `if WEBHOOK_SECRET:` guard, so an
unset/empty env var disables the check entirely; compare is plain `!=` (not constant-time).

| # | Full path | Method | Handler (file:line) | Auth state | Notes / blast radius |
|---|-----------|--------|---------------------|-----------|----------------------|
| 1 | `/webhook/tradingview` | POST | tradingview.py:192 | **fail-open** `!=` (217-221) | Secret check sits **after two early-return dispatches** (FOOTPRINT 201-205, PYTHIA 207-213). Strategy fan-out: Scout/Holy Grail/Exhaustion/Artemis/Phalanx/generic → signals pipeline. |
| 2 | `/webhook/breadth` | POST | tradingview.py:961 | **fail-open** `!=` (975-978) | Writes `breadth_intraday` factor → composite bias recompute. |
| 3 | `/webhook/tick` | POST | tradingview.py:1015 | **fail-open** `!=` (1032-1035) | Writes `tick_breadth` factor → composite bias. |
| 4 | `/webhook/tick/status` | GET | tradingview.py:1067 | none (read-only) | Status read; acceptable. |
| 5 | `/webhook/mcclellan` | POST | tradingview.py:1081 | **fail-open** `!=` (1099-1102) | Writes `mcclellan_oscillator` factor → composite bias. |
| 6 | `/webhook/outcomes/{signal_id}` | GET | tradingview.py:1192 | **none** | Leaks full `signal_outcomes` row by id. Low (read-only, id-guessing required). |
| 7 | `/webhook/test` | POST | tradingview.py:1222 | **none** | Echoes posted body to logs. Harmless but an open unauth POST + log-injection surface. |
| 8 | `/webhook/circuit_breaker` | POST | circuit_breaker.py:590 | **none (intentional)** | Documented public. Unauth POST can set `bias_cap`/`bias_floor`/`scoring_modifier` → **moves bias engine**. Spoofable DoS on scoring. |
| 9 | `/webhook/circuit_breaker/status` | GET | circuit_breaker.py:629 | none (read-only) | OK. |
| 10 | `/webhook/circuit_breaker/{reset,accept_reset,reject_reset,test}` | POST | circuit_breaker.py:639-686 | **`require_api_key`** ✅ | Hardened (PIVOT_API_KEY). |
| 11 | `/webhook/whale` | POST | whale.py:250 | **fail-open** `!=` (254-259) | Discord post + `whale:recent:` Redis cache (committee confluence) + signals pipeline. |
| 12 | `/webhook/whale/recent/{ticker}` | GET | whale.py:288 | none (read-only) | OK. |
| 13 | `/webhook/footprint` | POST | footprint.py:216 | **fail-open** `!=` (219-224) | Reachable **directly** and via TV-router dispatch. Discord + `footprint:recent:` cache + signals pipeline. See §2. |
| 14 | `/webhook/footprint/recent/{ticker}` | GET | footprint.py:253 | none (read-only) | OK. |
| 15 | `/webhook/mp_levels` | POST | mp_levels.py:57 | **AEGIS hardened** ✅ | Fail-closed, `hmac.compare_digest`, size cap, secret-strip. Uses `PYTHIA_WEBHOOK_SECRET`. |
| 16 | `/api/webhook/pythia` | POST | pythia_events.py:57 | **AEGIS hardened** ✅ | Fail-closed + replay window + idempotency. Chokepoint for TV-router PYTHIA dispatch **and** direct hits. |
| 17 | `/api/webhook/hermes` | POST | hermes.py:76 | **none** | Field-validate only (`alert_type=="hermes_flash"`). Unauth POST → inserts `catalyst_events`, can create `lightning_cards`, **triggers VPS scrape burst** (188.245.250.2:8000), WS broadcast. Highest unauth write blast radius. |
| 18 | `/api/hermes/analysis` | POST | hermes.py:300 | **X-API-Key** ✅ | PIVOT_API_KEY; updates catalyst row. Hardened. |
| 19 | `/api/hermes/alerts` | GET | hermes.py:381 | none (read-only) | OK. |
| 20 | `/api/hermes/alerts/{event_id}/dismiss` | PATCH | hermes.py:423 | **none** | Unauth state mutation (marks alert dismissed). Low impact, but should match the analysis route's auth. |

**Auth-state rollup:** hardened ✅ = #10, #15, #16, #18. fail-open = #1, #2, #3, #5, #11, #13.
no-auth write = #7, #8, #17, #20. read-only no-auth = #4, #6, #9, #12, #14, #19.

---

## 2. FOOTPRINT early-return — write path & blast radius (brief #1)

**Dispatch (tradingview.py:201-205):**
```python
if payload.get("signal") == "FOOTPRINT":
    from webhooks.footprint import footprint_webhook, FootprintSignal
    fp_data = FootprintSignal(**payload)
    return await footprint_webhook(fp_data)
```
This returns **before** the router's own secret check (217-221) — the early-return class the
brief flagged. **However**, `footprint_webhook` (footprint.py:216-224) now enforces its *own*
secret, and `FootprintSignal.secret` carries through the `**payload` splat. So:

> **Correction to brief #1:** FOOTPRINT is **not** "externally POST-able, unauthenticated"
> as written — when `TRADINGVIEW_WEBHOOK_SECRET` is set, the footprint chokepoint rejects a
> bad secret on both the direct and the router-forwarded path. The brief's recommended fix
> ("enforce a shared secret inside `footprint_webhook`") **has already been partially applied.**
> What remains is that footprint's gate is **fail-open** (`if WEBHOOK_SECRET:` → no env var =
> no auth) and uses a **plain `!=`** rather than `hmac.compare_digest`. The residual risk is
> "auth disabled if env unset / timing side-channel," **not** "no auth exists."

**Write path when the gate is open (env unset) — `_process_footprint_background` (footprint.py:132-213):**
1. **Discord** — arbitrary embed posted to `DISCORD_WEBHOOK_SIGNALS` (spam / social-engineering surface).
2. **Redis** — poisons `footprint:recent:{TICKER}` (30-min TTL) which feeds **committee confluence context**.
3. **Pipeline** — `process_signal_unified(... source="footprint")` → per pipeline.py:946-964:
   scores the signal, **persists to `signals` + `signal_outcomes` tables**, caches in Redis,
   **broadcasts via WebSocket**. A forged FOOTPRINT (LONG/SHORT) becomes a first-class signal
   row that can surface in the UI and color committee/confluence reads.

**Blast radius summary:** unauth (only if env unset) → fake order-flow signals injected into
the signals table + committee cache + Discord channel + live WS feed. Confined to EQUITY,
`signal_category=FOOTPRINT`, `base_score≈40`; no order placement (system is advisory).

---

## 3. Per-alert re-arm-class table (2026-06-09 alert log families)

**Re-arm class** = what it takes to make a live alert start sending the shared secret (required
before any server gate flips fail-closed, or the feed goes dark):

- **Pine-alert()** — secret lives in compiled Pine; add `input.string` + concat into the
  `alert(...)` JSON, re-save the script. One edit per script, auto-applies on next fire.
- **Message-box** — JSON is hand-authored in the TV alert UI (no Pine in repo); secret added
  by editing each alert's *Message* field. One edit **per alert instance**.

| Alert family (log) | Pine script in repo | Payload build | Sends secret today? | Re-arm class | Re-arm effort |
|--------------------|---------------------|---------------|---------------------|--------------|---------------|
| **TICK** | `tick_reporter.pine:28` | dynamic `alert()` string | ❌ | Pine-alert() | edit 1 script |
| **Breadth** (×2) | `breadth_webhook.pine:11` | dynamic `alert()` | ❌ | Pine-alert() | edit 1 script (both fire from it) |
| **McClellan** | `mcclellan_webhook.pine:11` | dynamic `alert()` | ❌ | Pine-alert() | edit 1 script |
| **Artemis** | `artemis_v3.pine:358/364` | dynamic `alert_msg` | ❌ | Pine-alert() | edit 1 script (long+short) |
| **Circuit Breaker** | `circuit_breaker_spy.pine` / `_vix.pine` | **static literal** JSON in `alert()` | ❌ | Pine-alert() (trivial literal edit) | 2 scripts — *but endpoint is intentionally public; secret optional* |
| **Trojan-Horse** (×N = footprint) | `trojan_horse_footprint_v2.pine:84` | dynamic `alert()` | ✅ **already** (`webhookSecret` input) | Pine-alert() | **none** — already wired; just set env var |
| **Hermes** (×9) | **none in repo** | hand-authored JSON in TV UI | ❌ | **Message-box** | edit **9** alert message fields |

**Key implications:**
- **Trojan-Horse is the safe starting point** — it already ships a secret, so gating
  `/webhook/footprint` fail-closed only requires the env var to be present (no re-arm).
- **Hermes is the costliest re-arm** (9 message-box edits, no recompile, but 9× human-error
  surface) — and it's also the **highest-impact unauth endpoint** (#17). Prioritize but stage.
- **Circuit Breaker** secret is essentially a policy decision: the endpoint is documented-public,
  the Pine edits are trivial literals. Cheap to add a shared secret if we want to close the
  bias-spoofing hole; otherwise leave documented-public.

---

## 4. Recommended chunks (for the full brief — NOT executed here)

Ordered by risk-adjusted ease. Each chunk is "add secret to the alert(s) → verify traffic
carries it → flip server to fail-closed," never flip-first.

- **Chunk 0 — Shared helper (foundation).** Add `validate_webhook_secret(payload, secret_env)`
  in `backend/utils/` — constant-time (`hmac.compare_digest`), fail-closed (503 if env unset),
  size cap, secret-strip — mirroring the AEGIS blocks in `mp_levels.py` / `pythia_events.py`.
  Every handler below calls it instead of copy-pasting. No re-arm.

- **Chunk A — Footprint fail-closed (lowest risk).** Swap footprint.py:219-224 to the shared
  helper. Trojan-Horse **already sends the secret**, so this only needs the env var set.
  Closes brief #1 properly. Also tighten the TV-router FOOTPRINT dispatch so the forwarded
  path can't regress.

- **Chunk B — Whale fail-closed.** Same swap in whale.py:254-259. Re-arm: `whale_hunter_v2.pine`
  (currently 🟡 not wired per inventory — low live traffic, good test case).

- **Chunk C — TV-router core + strategy fan-out.** Upgrade tradingview.py:217-221 to the shared
  helper and ensure the gate covers the early-return dispatches. **Largest blast radius** — gates
  Artemis/Holy Grail/Scout/Hub Sniper/Phalanx. Stage: re-arm those pines first (Artemis is in the
  6-09 log; others are adjacent), confirm secret present in logs, then flip. *Touches the router
  only — coordinate timing with the scoring/signals session since these feed the pipeline.*

- **Chunk D — Bias-factor webhooks.** Fail-closed for `/webhook/tick`, `/webhook/breadth`,
  `/webhook/mcclellan`. Re-arm 3 pines. These move the composite bias, so an unauth POST is a
  bias-spoofing vector. *Handlers live in tradingview.py (mine to edit); the factor-scoring
  modules they call are read-only for this session — gate is in the handler, no scoring change.*

- **Chunk E — Hermes.** Add a secret (or API-key) gate to `/api/webhook/hermes` (#17) and match
  auth on the `/api/hermes/alerts/{id}/dismiss` PATCH (#20). Re-arm **9 message-box** alerts.
  Highest unauth-write impact; stage carefully across the 9.

- **Chunk F — Circuit Breaker (policy call).** Decide: keep documented-public, or add a shared
  secret (trivial Pine literal edit ×2) to close the unauth bias-state write (#8). Recommend a
  secret — the cost is near-zero and it removes a scoring-DoS vector.

- **Chunk G — Cleanup.** Remove or gate `/webhook/test` (#7); decide whether
  `/webhook/outcomes/{id}` (#6) should require auth. Apply the **R-4 router-level raw-body size
  cap** centrally at the `/webhook/tradingview` request read (AEGIS endpoints already cap per-handler).

---

## 5. Rulings (Nick, 2026-06-10) — feeds Phase 1 build brief

1. **Q1 CONFIRMED: `TRADINGVIEW_WEBHOOK_SECRET` is NOT set in Railway.** Therefore the **six
   fail-open endpoints are currently UNAUTHENTICATED**: `tradingview`, `breadth`, `tick`,
   `mcclellan`, `whale`, `footprint` (#1, #2, #3, #5, #11, #13). This is the live exposure.
2. **Cutover discipline is mandatory, per chunk:** re-arm the alert(s) to send the secret →
   verify traffic carries it → **set the env var as part of that chunk's cutover** → flip the
   handler fail-closed. The env var is set **per-chunk during cutover, never preemptively**
   (a preemptive set would 503 every still-unarmed endpoint at once).
3. **Hermes: harden all 9, no trim.** Justification is the **VPS-scrape-burst lever**
   (`vps_trigger_url` → 188.245.250.2:8000, resource-abuse / amplification risk), **not** the
   catalyst cards. All 9 alerts get re-armed.
4. **Circuit Breaker: add the cheap shared secret** (closes the unauth bias-state write, #8).
5. **Priority = Olympus-feeding wiring is core:** bias factors (tick/breadth/mcclellan),
   strategy signals (tradingview fan-out), and committee-confluence inputs (whale/footprint).
   Pure-QoL is deprioritized — **Chunk G is the explicit slack-cutter** if the timeline tightens.
6. Severity-ordered sequence retained.

➡ **Phase 1 build brief:** `docs/codex-briefs/2026-06-10-phase1-global-webhook-hardening.md`

---

## 6. Post-sprint queue — Hermes raw observations (do NOT action this sprint)

Captured opportunistically during the census for a **dedicated Hermes-audit Phase 0**. Raw
observations only — not a task, not in security scope for this sprint.

- **What the Hermes webhook writes** (`/api/webhook/hermes`, hermes.py):
  - `catalyst_events` — every velocity breach (`event_type='velocity_breach'`, tier 1/2,
    trigger ticker, move %, correlated tickers, sector_velocity, trip_wire_status). Insert at
    hermes.py:483-502.
  - `lightning_cards` — created **only on Hydra convergence** (involved ticker also in squeeze
    territory, `composite_score ≥ 50`). Insert at hermes.py:235-256. Carries position
    relationship (CONFIRMING/OPPOSING/UNRELATED) vs `unified_positions`.
  - `/api/hermes/analysis` (VPS callback) later back-fills `headline_summary`,
    `catalyst_category`, `pivot_analysis` onto the same `catalyst_events` row + linked cards.
- **Is `hub_get_hermes_alerts` wired into live committee passes?** — **Apparent name-collision /
  decoupling worth the audit:** the MCP tool `hub_get_hermes_alerts`
  (`backend/hub_mcp/tools/hermes_alerts.py`) does **NOT** read the `catalyst_events` table the
  webhook writes. It reads `services/read_only/catalysts.get_upcoming_catalysts` →
  `api.catalyst_calendar.get_upcoming_catalysts` — a forward-looking **catalyst calendar**
  (earnings/FDA/FOMC), a different source. Its description advertises it to TORO/URSA/PYTHAGORAS/
  PYTHIA/THALES/DAEDALUS/PIVOT, so the *calendar* is committee-wired — but the **velocity-breach
  `catalyst_events` written by the webhook appear to reach the committee via a different path or
  not at all.** (Whether any live pass surfaces the webhook rows = the audit's job.)
- **How it surfaces in the UI:** front-end **Hermes Flash** widget polls `/api/hermes/alerts`
  (the REST reader of `catalyst_events`) every 10s (`app.js:12538-12567`, `initHermesFlash`/
  `fetchHermesAlerts`); **Lightning Cards** rendered via `initLightningCards` with a
  `lightning_confirmation` WebSocket handler (`app.js:1238-1255`, 8188-8190). So the webhook's
  writes are primarily a **frontend** surface today, distinct from the MCP catalyst-calendar tool.

---

## 7. STOP — gate reached

Census + rulings recorded. No production code modified. Proceeding to author the Phase 1 build
brief (security lane only).
