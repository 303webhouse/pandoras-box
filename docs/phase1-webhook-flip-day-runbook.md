# Phase 1 Webhook Hardening — FLIP-DAY RUNBOOK (DRAFT for architecture review)

**Status:** DRAFT — review at the architecture layer **before any flipping**.
**Authored:** 2026-06-10 (post-Chunk D). **Owner this run:** security session (`sec-work`).
**Scope:** every observe-mode gate currently deployed and awaiting its fail-closed flip.

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
3. **Populate the on-chart "Webhook Secret" input** with that same value on **all 9 indicators**,
   on **every chart/ticker each one runs on** (per-chart — an indicator on 5 tickers = 5 inputs):

   | Group | Indicator (on-chart name) | Pine file |
   |-------|---------------------------|-----------|
   | A footprint | **Footprint Alert for Pandora** (shorttitle "Trojan-Horse") | `webhooks/trojan_horse_footprint_v2.pine` |
   | D bias | **TICK Reporter (Webhook)** | `webhooks/tick_reporter.pine` |
   | D bias | **Breadth Webhook** | `webhooks/breadth_webhook.pine` |
   | D bias | **McClellan Webhook** | `webhooks/mcclellan_webhook.pine` |
   | C strat | **Artemis v3.1** | `webhooks/artemis_v3.pine` |
   | C strat | **Holy Grail Webhook** (shorttitle "HG Webhook") | `holy_grail_webhook_v1.pine` |
   | C strat | **Scout Sniper v3.1 (15m) – Tradeable/Ignore + VWAP Plan** | `webhooks/scout_sniper_v3.1.pine` |
   | C strat | **Hub Sniper v2.1** | `webhooks/hub_sniper_v2.1.pine` |
   | C strat | **Phalanx v2** | `webhooks/phalanx_v2.pine` |

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

### GATE 2 — Chunk D bias factors (medium: 3 feeds, move composite bias)
Flip the three **independently**, each after its own feed confirms:
- **TICK** — `[tick] … PRESENT, match=True` → set `WEBHOOK_TICK_ENFORCE=1`. (Fires every confirmed
  bar in-session — confirms fast.)
- **Breadth** — `[breadth] … PRESENT, match=True` → set `WEBHOOK_BREADTH_ENFORCE=1`. (Every
  confirmed bar — confirms fast.)
- **McClellan** — `[mcclellan] … PRESENT, match=True` → set `WEBHOOK_MCCLELLAN_ENFORCE=1`.
  ⚠ **Fires once/day at the close** — its observe confirmation can take a **full session**. Do NOT
  block GATE 3 waiting on it: flip tick+breadth when confirmed, flip mcclellan on its next daily fire.
- **Verify each:** the factor still scores (composite recompute logs) post-flip; a secretless test
  POST to that path returns 401.

### GATE 3 — Chunk C TV-router + 5 strategy families (HIGHEST: a bad flip drops every live strategy signal)
- **Single flag, all 5 families:** `WEBHOOK_TV_ENFORCE=1` gates `/webhook/tradingview` for
  Artemis, Holy Grail, Scout, Hub Sniper, Phalanx **at once**. There is no per-family flag — so
  **all 5 must be confirmed before the one flip.**
- **Family attribution caveat:** the gate logs a generic label `[tradingview] OBSERVE: payload
  secret PRESENT, match=True` — it does **not** name the strategy. Correlate each observe line with
  the very next log line `📨 Webhook received: <ticker> <dir> (<strategy>)` to attribute the family.
  Tick off all 5 strategy names before flipping.
- **Low-frequency risk:** some families fire only on a setup. A family not seen in the observe
  window = **do not flip** (you'd silently drop it). Either wait for a natural fire, or push a
  forced test alert per family with the secret populated.
- **Flip:** set `WEBHOOK_TV_ENFORCE=1` only after all 5 confirmed.
- **Verify:** a real signal from each family still returns `{"status":"accepted"}`; a secretless
  POST to `/webhook/tradingview` returns 401.

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
| mcclellan | `WEBHOOK_MCCLELLAN_ENFORCE` |
| TV + 5 strategies | `WEBHOOK_TV_ENFORCE` |

> Leaving `TRADINGVIEW_WEBHOOK_SECRET` set during a rollback is harmless (observe just keeps
> logging `match=…`). Only unset it if you intend to fully stand down all gates.

---

## Pre-flight checklist (architecture sign-off)

- [ ] `TRADINGVIEW_WEBHOOK_SECRET` set in Railway (Step 0.2).
- [ ] All 9 indicators' "Webhook Secret" input populated on **every** chart instance (Step 0.3).
- [ ] Observe logs show `PRESENT, match=True` for: footprint; tick; breadth; mcclellan (next daily
      fire); and all 5 strategy families (attributed via the adjacent "Webhook received" line).
- [ ] Flip order honored: GATE 1 → GATE 2 (tick, breadth, mcclellan) → GATE 3, each verified first.
- [ ] Rollback path understood (unset the per-gate flag).
- [ ] Decision logged: McClellan may flip a day later than the rest (once/day fire) — acceptable?
- [ ] Decision logged: any low-frequency strategy family — wait for natural fire vs forced test?

*Pythia (`/api/webhook/pythia`) and mp_levels (`/webhook/mp_levels`) are already AEGIS fail-closed
(B4) and are NOT part of this flip. Circuit Breaker (Chunk F) and Hermes (Chunk E) are separate
upcoming chunks with their own secrets/flags — not in this runbook.*
