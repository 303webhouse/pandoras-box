# Phase 1 Webhook Hardening — FLIP-DAY RUNBOOK (FINAL)

**Status:** ✅ FINAL — approved by PM 2026-06-10 with the two pre-flight rulings below.
**Authored:** 2026-06-10 (post-Chunk D; Hermes addendum post-Chunk E). **Owner:** security session (`sec-work`).
**Scope:** every observe-mode gate currently deployed and awaiting its fail-closed flip.

> **⚠ 2026-06-11 reconciliation trim:** Scout, Hub Sniper, Phalanx, and McClellan were **removed**
> from this runbook — they guard **zero live TV traffic** (0 sigs/30d; McClellan replaced server-side
> by `nyse_proxy`). Their gates were removed in commit `cd56b5f`. **tick/breadth** are retained but
> **held pending an on-chart alert-existence check** (no live data since 06-10 20:00Z). See
> [phase1-webhook-ingress-reconciliation.md](phase1-webhook-ingress-reconciliation.md) for the
> per-feed evidence. Live flip set is now: **footprint, Artemis, Holy Grail, circuit_breaker**
> (+ Hermes addendum), with tick/breadth on hold.

---

## PM PRE-FLIGHT RULINGS (FINAL)

1. ~~**McClellan may flip a session late — never block GATE 3 on it.**~~ **MOOT (2026-06-11):**
   McClellan was removed from flip scope — it's now computed server-side (`nyse_proxy`) and its
   webhook gate was deleted (commit `cd56b5f`). Ruling retained for history only.
2. **Unseen low-frequency families — no forced pipeline alerts, no multi-day waits.** Do **NOT**
   push synthetic alerts through the real pipeline (signal pollution), and do **NOT** stall the
   flip for days waiting on a natural fire. Protocol for a family/feed not yet seen in observe:
   **(a)** visually verify the on-chart "Webhook Secret" input is populated; **(b)** run the
   secretless/secreted **curl pair against the gate** to prove its auth behavior; **(c)** flip the
   gate; **(d)** watch the **first natural fire** land, with **instant rollback ready** (unset the
   flag) if it 401s.
   - *Implementation note (pipeline-coupled gates — TV strategies, footprint, hermes):* the
     **secretless** leg is the safe proof — post-flip it returns **401** at the gate with no
     pipeline entry. The **secreted** positive is best confirmed by the **first natural fire**
     rather than a synthetic secreted POST, because on these endpoints the secret gate sits ahead
     of (and feeds) signal creation, so a synthetic secreted POST would itself pollute. Net: flip
     after (a)+(b-secretless), then the next real signal is the positive confirmation, rollback armed.

> All gates below are LIVE in production in **observe mode** (validate-but-allow, log the
> verdict). Nothing rejects today. This runbook flips them to **fail-closed**, smallest-blast
> first, each fully verified before the next. **Market-hours only** — the feeds only fire during
> the regular session.

---

## What a "flip" is

Each gate calls the shared `validate_webhook_secret()` helper with `observe=<env-driven>`.
Flipping = setting that gate's `WEBHOOK_*_ENFORCE=1` env var in Railway. **No redeploy** — the
flag and the secret are read at request time. Rollback = unset the flag → instant return to observe.

Two preconditions for every flip:
1. `TRADINGVIEW_WEBHOOK_SECRET` is set in Railway (shared by footprint, bias-factors, TV-router).
2. The matching Pine indicator's **"Webhook Secret"** on-chart input is populated with the **same**
   value, **on every chart instance** the indicator runs on.

---

## STEP 0 — One-time prep (do before any flip)

1. **Choose the secret value** (treat as a credential — do not paste it into logs/Discord/tickets).
2. **Set it in Railway:** `TRADINGVIEW_WEBHOOK_SECRET=<value>`.
   - ✅ Safe to set now: every gate still only enforces when its **own** `WEBHOOK_*_ENFORCE` flag
     is on. Setting the shared secret does **not** flip anything — it just lets the observe logs
     start reporting `match=True/False` instead of `env secret UNSET`.
3. **Populate the on-chart "Webhook Secret" input** with that same value on the indicators below,
   on **every chart/ticker each one runs on** (per-chart — an indicator on 5 tickers = 5 inputs).
   *(Scout/Hub Sniper/Phalanx/McClellan removed per the 2026-06-11 reconciliation — dead feeds.)*

   | Group | Indicator (on-chart name) | Pine file | Status |
   |-------|---------------------------|-----------|--------|
   | A footprint | **Footprint Alert for Pandora** (shorttitle "Trojan-Horse") | `webhooks/trojan_horse_footprint_v2.pine` | flip-ready |
   | D bias | **TICK Reporter (Webhook)** | `webhooks/tick_reporter.pine` | **HOLD** — verify alert exists |
   | D bias | **Breadth Webhook** | `webhooks/breadth_webhook.pine` | **HOLD** — verify alert exists |
   | C strat | **Artemis v3.1** | `webhooks/artemis_v3.pine` | re-arm live Pine first |
   | C strat | **Holy Grail Webhook** (shorttitle "HG Webhook") | `holy_grail_webhook_v1.pine` | re-arm live Pine first |
   | F (GATE 5) | **Circuit Breaker Monitor (SPY)** | `webhooks/circuit_breaker_spy.pine` | verify, then flip |
   | F (GATE 5) | **Circuit Breaker Monitor (VIX)** | `webhooks/circuit_breaker_vix.pine` | verify, then flip |

   > ⚠ The Pine *code* now carries the field, but the on-chart input **defaults to empty**. An
   > un-populated input sends `"secret":""` → that feed will 401 the instant its gate flips.

4. **Watch the logs.** Railway logs, filter on `OBSERVE: payload secret`. The verdict line is:
   `[<label>] OBSERVE: payload secret PRESENT, match=True` — that's the green light per feed.
   `ABSENT` or `match=False` = that feed is NOT ready; do not flip its gate.

---

## Flip order (smallest blast radius → largest)

> Verify each gate fully (✅ all its feeds show `PRESENT, match=True`, ≥3 consecutive POSTs each)
> **before** touching the next. If any feed is missing, stop and fix the on-chart input.

### GATE 1 — Chunk A footprint (smallest: 1 feed, committee-confluence input)
- **Feed/Pine:** Trojan-Horse. **Flag:** `WEBHOOK_FOOTPRINT_ENFORCE=1`.
- **Watch:** `[footprint] OBSERVE: payload secret PRESENT, match=True`.
- **Flip:** set `WEBHOOK_FOOTPRINT_ENFORCE=1`.
- **Verify:** a real footprint still returns `{"status":"received"}`; a hand-rolled secretless POST
  to `/webhook/footprint` now returns **401**.

### GATE 2 — Chunk D bias factors (tick + breadth; move composite bias)
> **⚠ HELD pending Nick's TV-alert existence check** — per the 2026-06-11 reconciliation, neither
> tick nor breadth has delivered live data since 06-10 20:00Z (factors kept "fresh" by recompute on
> stale cache — see the faked-fresh Phase 0). **Do not flip until a live POST is confirmed.**
> McClellan was **removed** from this gate (replaced server-side by `nyse_proxy`).

Flip the two **independently**, each after its own feed confirms a *live* POST:
- **TICK** — `[tick] … PRESENT, match=True` (with a **fresh** `updated_at`) → set `WEBHOOK_TICK_ENFORCE=1`.
- **Breadth** — `[breadth] … PRESENT, match=True` (fresh) → set `WEBHOOK_BREADTH_ENFORCE=1`.
- **Verify each:** the factor still scores (composite recompute logs) post-flip; a secretless test
  POST to that path returns 401.

### GATE 3 — Chunk C TV-router + 2 live strategy families (HIGHEST: a bad flip drops every live strategy signal)
> **⚠ Root-cause precondition (2026-06-11):** the repo `.pine` edits **never propagated** to
> TradingView — the live charts still run the OLD Artemis/Holy Grail Pine **without** the secret
> input. Nick must paste the updated Pine onto each chart **first**, or these will 401 on flip.
> Scout/Hub Sniper/Phalanx removed — **0 sigs/30d**, no live TV source (see reconciliation).

- **Single flag, both families:** `WEBHOOK_TV_ENFORCE=1` gates `/webhook/tradingview` for **Artemis
  and Holy Grail** at once. There is no per-family flag — so **both must be confirmed before the one
  flip.** (These are the only two live webhook strategies; everything else on this route is
  server-side or dead.)
- **Family attribution caveat:** the gate logs a generic label `[tradingview] OBSERVE: payload
  secret PRESENT, match=True` — it does **not** name the strategy. Correlate each observe line with
  the very next log line `📨 Webhook received: <ticker> <dir> (<strategy>)` to attribute the family.
  Tick off both (Artemis, Holy Grail) before flipping.
- **Low-frequency families (PM RULING 2, FINAL):** if either isn't seen in observe — Do **NOT**
  push forced alerts through the pipeline (signal pollution) and do **NOT** stall for days:
  **(a)** visually verify its on-chart "Webhook Secret" input is populated → **(b)** secretless
  curl against `/webhook/tradingview` (safe liveness probe) → **(c)** flip `WEBHOOK_TV_ENFORCE=1`
  → **(d)** watch that family's first natural fire land, **rollback armed** if it 401s.
- **Flip:** set `WEBHOOK_TV_ENFORCE=1` only after both confirmed.
- **Verify:** a real signal from each family still returns `{"status":"accepted"}`; a secretless
  POST to `/webhook/tradingview` returns 401.

### GATE 5 — Chunk F circuit breaker (rare fires → Ruling 2 protocol)
- **Feed/Pines:** Circuit Breaker SPY + VIX. **Secret:** shared `TRADINGVIEW_WEBHOOK_SECRET`
  (TV-family — inputs populated in Step 0). **Flag:** `WEBHOOK_CB_ENFORCE=1`. **Watch:**
  `[circuit_breaker] OBSERVE: payload secret PRESENT, match=True`. CB fires only on a state change
  (rare) → apply **PM Ruling 2**: visual-verify both CB inputs populated → secretless curl against
  `/webhook/circuit_breaker` (→401 post-flip) → flip → watch the first natural CB fire, rollback
  armed. Closes the unauth bias-state write (`bias_cap`/`bias_floor`/`scoring_modifier`).

---

## Explicitly NOT flipped this sprint

- **Chunk B — whale** (`/webhook/whale`, flag `WEBHOOK_WHALE_ENFORCE`): the alert is **dormant**
  (not wired to a live chart). Per Rider 2 it **stays observe** through sprint end and flips later,
  in the same motion as wiring its live alert. The Pine (`whale_hunter_v2.pine`) is already
  re-armed; nothing to do on flip-day.

---

## Rollback (per gate, instant, no redeploy)

Unset the gate's flag (delete the env var or set it to `0`) → the gate returns to observe-mode on
the next request. Each gate is isolated; rolling one back does not touch the others.

| Gate | Flag to unset |
|------|---------------|
| footprint | `WEBHOOK_FOOTPRINT_ENFORCE` |
| tick | `WEBHOOK_TICK_ENFORCE` |
| breadth | `WEBHOOK_BREADTH_ENFORCE` |
| TV + Artemis/Holy Grail | `WEBHOOK_TV_ENFORCE` |
| Circuit Breaker (GATE 5) | `WEBHOOK_CB_ENFORCE` |
| Hermes ×9 (addendum) | `WEBHOOK_HERMES_ENFORCE` |

> Leaving `TRADINGVIEW_WEBHOOK_SECRET` set during a rollback is harmless (observe just keeps
> logging `match=…`). Only unset it if you intend to fully stand down all gates.

---

## Pre-flight checklist (architecture sign-off)

- [ ] `TRADINGVIEW_WEBHOOK_SECRET` set in Railway (Step 0.2).
- [ ] The 7 retained indicators' "Webhook Secret" input populated on **every** chart instance (Step 0.3).
- [ ] **Artemis + Holy Grail live Pine re-pasted on-chart** (repo edits don't propagate — root cause).
- [ ] **tick/breadth alert-existence confirmed by Nick** (held until a fresh live POST is observed).
- [ ] Observe logs show `PRESENT, match=True` for: footprint; both strategy families (Artemis, Holy
      Grail — attributed via the adjacent "Webhook received" line); circuit_breaker (on natural fire).
- [ ] Flip order honored: GATE 1 footprint → GATE 2 (tick, breadth — *if confirmed live*) → GATE 3
      (Artemis, Holy Grail) → GATE 5 circuit_breaker → GATE 4 Hermes (addendum; after Gates 1–3, or
      day 2 — isolated), each verified first.
- [ ] Hermes (GATE 4): `HERMES_WEBHOOK_SECRET` set; all 9 alert messages carry it (saved); dismiss
      PATCH gap noted as a separate follow-up.
- [ ] Rollback path understood (unset the per-gate flag).
- [ ] Decision logged: any low-frequency strategy family — wait for natural fire vs forced test?

*Pythia (`/api/webhook/pythia`) and mp_levels (`/webhook/mp_levels`) are already AEGIS fail-closed
(B4) and are NOT part of this flip. **Circuit Breaker (Chunk F) is GATE 5 above; Hermes (Chunk E)
is covered by the addendum below.***

---

# ADDENDUM — GATE 4: Hermes ×9 (Chunk E)

**Isolated from Gates 1–3 — no coupling.** Hermes uses a **separate secret** (`HERMES_WEBHOOK_SECRET`,
not the shared `TRADINGVIEW_WEBHOOK_SECRET`) and its own flag (`WEBHOOK_HERMES_ENFORCE`). It joins
flip-day **AFTER Gates 1–3 are done**, or **slides to day 2** if the morning runs long — its
isolation means slipping it has zero effect on the other gates.

**Why hardened:** the real risk is the **VPS-scrape-burst lever** (`/api/webhook/hermes` →
`http://188.245.250.2:8000/api/hermes/trigger`, resource-abuse / amplification), not the catalyst
cards.

**Re-arm class — Message-box (easier than the Pine class):** Hermes has **no Pine in the repo**; the
9 alerts are hand-authored JSON in the TradingView alert UI. **Message-box edits apply on save — no
alert recreate, no indicator republish.** This is strictly easier than the Pine re-arm.

### Step 0 (Hermes-specific)
1. **Generate a separate secret value** (Nick, flip-day). Do not reuse `TRADINGVIEW_WEBHOOK_SECRET`.
   PowerShell pattern:
   ```powershell
   # 32-byte URL-safe-ish random secret
   [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 })) -replace '[+/=]',''
   ```
   Treat as a credential — do not paste into logs/Discord/tickets.
2. **Set it in Railway:** `HERMES_WEBHOOK_SECRET=<value>`. Safe to set now — Hermes still only
   enforces when `WEBHOOK_HERMES_ENFORCE=1`.

### Step 1 — Re-arm the 9 Hermes alerts (message-box)
For **each** of the 9 ticker alerts (SPY, QQQ, SMH, XLF, HYG, IYR, TLT, USO, GLD, IBIT — the
`HERMES_CONFIG` set; confirm the live 9 on the TV alerts list), edit the alert's **Message** field
and add a top-level `"secret"` key alongside the existing `hermes_flash` fields. Example message:
```json
{"alert_type":"hermes_flash","ticker":"SPY","velocity_pct":{{...}},"direction":"...","timeframe_min":30,"secret":"<HERMES_WEBHOOK_SECRET>"}
```
- Edit → **Save** (the edit applies immediately; no recreate).
- Keep the same value in all 9.
- ☑ Tick each ticker off as you save it — **all 9 must carry the secret before the flip.**

### Step 2 — Observe
Watch logs for `[hermes] OBSERVE: payload secret PRESENT, match=True`. Because Hermes fires only on
a velocity breach (event-driven, can be infrequent), apply **PM Ruling 2** for any unseen ticker:
visual-verify that alert's message has the secret saved → secretless/secreted curl pair against
`/api/webhook/hermes` (secretless = safe liveness probe) → flip → watch first natural breach land,
rollback armed.

### Step 3 — Flip
Set `WEBHOOK_HERMES_ENFORCE=1`. **Verify:** a secretless POST to `/api/webhook/hermes` returns
**401**; a real velocity breach still creates its catalyst event. **Rollback:** unset
`WEBHOOK_HERMES_ENFORCE` → instant return to observe.

### Not done in Chunk E (separate follow-up)
- The **`PATCH /api/hermes/alerts/{id}/dismiss`** state-mutation is still unauthenticated. It is
  **frontend-driven and the UI sends no API key** (`app.js` `dismissHermesAlert` → bare PATCH), so
  gating it with `require_api_key` would break the dashboard dismiss button. Closing it properly
  needs a coordinated frontend change (send the key) — logged as a follow-up, **not** flipped here.
