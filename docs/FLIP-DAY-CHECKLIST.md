# Flip-Day Checklist — 2026-06-11 AM

**Golden rule:** nothing rejects until YOU flip it. Every flip undoes in ~10 sec
(unset the flag → back to observe). No step is time-critical.

---

## ☐ PREP (~5 min, before market open is fine)

- [ ] Open runbook: `docs/phase1-webhook-flip-day-runbook.md`
- [ ] Railway → fabulous-essence → pandoras-box → Variables → confirm
      `TRADINGVIEW_WEBHOOK_SECRET` exists (don't change it)
- [ ] Generate Hermes secret in PowerShell:
      `-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})`
- [ ] Add it to Railway as `HERMES_WEBHOOK_SECRET`
- [ ] Keep both secret values in Notepad for the next ~30 min

## ☐ STEP 0 — Arm indicators (~20 min, the tedious part)

Paste the secret into each indicator's **"Webhook Secret"** input (use runbook's
name→file table to find them all).

- [ ] TV-family indicators use the `TRADINGVIEW_WEBHOOK_SECRET` value:
      footprint, tick, breadth, mcclellan, Artemis, Holy Grail, Scout,
      Hub Sniper, Phalanx, circuit breaker (SPY + VIX)
- [ ] Hermes ×9 use the **`HERMES_WEBHOOK_SECRET`** value (don't cross them)
- [ ] An indicator on N tickers = N separate input fields to fill (per-chart)
- [ ] DOUBLE-CHECK none are left blank — a blank field 401s that feed on flip
      (this is THE failure mode)

## ☐ STEP 1 — Flip gates, smallest blast first (across the session)

For each gate: watch Railway logs for `[<label>] OBSERVE: payload secret
PRESENT, match=True` from EVERY feed in it, THEN set its flag.

- [ ] GATE 1 — footprint → `WEBHOOK_FOOTPRINT_ENFORCE=1`
- [ ] GATE 2 — tick → `WEBHOOK_TICK_ENFORCE=1`
- [ ] GATE 2 — breadth → `WEBHOOK_BREADTH_ENFORCE=1`
- [ ] GATE 2 — McClellan → `WEBHOOK_MCCLELLAN_ENFORCE=1`
      ⚠ fires once/day at close — DON'T wait on it, flip it whenever it confirms
- [ ] GATE 3 — confirm ALL 5 strategy names in logs first, then ONE flip:
      `WEBHOOK_TV_ENFORCE=1` (covers Artemis/HolyGrail/Scout/HubSniper/Phalanx)
- [ ] GATE 4 — Hermes → `WEBHOOK_HERMES_ENFORCE=1`
- [ ] GATE 5 — circuit breaker → `WEBHOOK_CB_ENFORCE=1`

**Rare feed not showing in logs?** Open its indicator settings, eyeball the
secret field is filled, flip it, watch its first real fire with rollback ready.
DON'T fake a signal (pollutes the pipeline).

**Rollback any gate:** unset its `_ENFORCE` flag → instant observe. Isolated.

## ☐ HAPPENING IN BACKGROUND (no action — just know)

- [ ] Scoring shadows start logging at the open: ADX regime writer's first
      read, iv-rank shadow, flow-reconciliation shadow. CC reports the numbers
      in a few days. You do nothing.

---

## 📌 NEXT UP (AFTER flip-day + current to-dos — not today)

### Flow Radar fix — SPY priority (NEW 0DTE scalping strategy)
- Day trading now permitted for smaller accounts (PDT rule eliminated
  Apr 2026) → Nick is running an intraday 0DTE SPY scalping strategy.
- `hub_get_flow_radar` needs to reliably serve SPY intraday flow — it
  errored on a post-close test (req_011CbvSj...) and the B3 family relies
  on it. Needs: a Phase 0 on why flow_radar errors / caps (it caps at 24h
  regardless of param per the handoff brief), what "0 SPY events in 4h"
  really means (unusual-activity filter vs dead pipeline — CC found 1,275
  events/4h with 26 SPY on 6/9, so the radar's SPY view may be filter-
  masked rather than empty), and what an intraday-scalp-grade SPY flow
  feed actually requires.
- Bucket: B3 (intraday scalp) — structural Pythia trigger + flow + tape only.
- Queue position: AFTER current sprints (hardening flip-day, sb3 shadow
  promotes). Architecture layer to draft the Flow Radar Phase 0 when the
  current to-dos clear.

### Other racked briefs (already drafted, awaiting their gates)
- Global webhook hardening — flip-day execution (this checklist), then
  done bar 2 follow-ups (Hermes dismiss PATCH, outcomes GET — both need
  coordinated changes)
- sub-brief 3 shadow promotes: iv (1c, ~1wk), ADX (3c, few sessions),
  flow-reconciliation (2R-b, 5-10 sessions)
- Hermes audit Phase 0 (racked)
- PYTHAGORAS feed Phase 0 (racked, gated on sb3 Chunk 3 — now landed,
  so unblockable)
