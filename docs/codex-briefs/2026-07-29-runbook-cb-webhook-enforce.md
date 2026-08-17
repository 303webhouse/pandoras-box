# RUNBOOK — CIRCUIT BREAKER WEBHOOK: OBSERVE → ENFORCE

**Owner:** Nick (executes by hand — no AI touches the secret)
**Origin:** AEGIS Pass 1 finding, Titans review 2026-07-29
**Deadline:** complete before **2026-08-04**
**Time required:** ~25 minutes
**Reversible:** yes, instantly, no deploy

---

## WHAT THIS DOES, IN PLAIN TERMS

The circuit breaker is armed by TradingView sending a message to a web address on your server. That address is currently **public** — it checks for a password but lets the message through either way. Anyone who knows the URL could arm your breaker and throttle your own signal scoring.

Right now that's tolerable because the tile is ambiguous anyway. Once the honesty fix ships, you'll *believe* the tile — so the input needs to be trustworthy before the output becomes authoritative. That's the whole reason this is on the list.

**The flip itself is one setting.** The work is all in verifying it won't break anything first.

**The failure mode to respect:** if you flip enforcement on and TradingView isn't actually sending the password, the breaker stops arming — silently, with no error anywhere you'd look — for the entire vacation. That is strictly worse than leaving it alone. Every step below exists to make that impossible.

---

## BEFORE YOU START — THREE TIMING RULES

1. **Not during market hours.** Preferably evening or weekend.
2. **Not in the same session as the A-4 kill-switch drill.** They test two different doors into the same room. A passing A-4 drill uses the API-key route and never touches the password path — it would happily go green on a dead webhook. Do these on different days so you don't confuse the results.
3. **Before Aug 4, not during the freeze.** Changing a Railway variable restarts the service, and a restart reloads breaker state from Redis. Harmless while the breaker is CLEAR (it is), but not something to do blind from a beach.

---

## PHASE 1 — CONFIRM THE PASSWORD EXISTS ON THE SERVER

If this variable is missing, enforcement returns an error for **every** breaker message and the breaker dies completely. This step is not a formality.

1. Open **railway.app** → your project → the **pandoras-box** service
2. Click the **Variables** tab
3. Find **`TRADINGVIEW_WEBHOOK_SECRET`**
4. Click the eye icon to reveal it. Confirm it is **not empty**
5. Copy the value somewhere you can paste from in Phase 3 (a scratch note you delete afterward — not a file in the repo)

> **STOP CONDITION:** if `TRADINGVIEW_WEBHOOK_SECRET` doesn't exist or is blank — stop here. Do not continue. That's a different task (create the secret first, then restart this runbook).

---

## PHASE 2 — RE-ARM THE TRADINGVIEW ALERTS

**This is the step that silently breaks things, so read it before doing it.**

TradingView captures an indicator's settings at the moment you create the alert. If the Pine script or its inputs changed *after* the alert was made, the alert keeps sending the **old** payload forever. There is no warning and nothing in the TradingView interface tells you the alert is stale.

Your two Circuit Breaker alerts predate the change that added the password to the payload. **Assume they are stale.** Rather than trying to work out whether they need re-arming, just re-arm both — it takes two minutes and removes the question.

### For EACH of the two charts (SPY and VIX):

1. Open the chart with **Circuit Breaker Monitor** on it
2. Hover the indicator name → click the **gear icon** (Settings)
3. Find the **Webhook Secret** input field
4. Confirm it contains the same value you copied in Phase 1. If it's blank, paste it in
5. Click **OK**
6. Open the **Alerts** panel (right sidebar, clock icon)
7. **Delete** the existing "Circuit Breaker Monitor" alert
8. Create it fresh:
   - Condition: **Circuit Breaker Monitor (SPY)** *(or VIX)* → **Any alert() function call**
   - Notifications tab → **Webhook URL**, checked
   - URL: `https://pandoras-box-production.up.railway.app/webhook/circuit_breaker`
   - Expiration: **Open-ended**
   - Click **Create**

Repeat for the second chart. **Both must be done** — one re-armed and one stale is the worst outcome, because the system will look half-working.

---

## PHASE 3 — PROBE THE PASSWORD CHECK (STILL IN OBSERVE — NOTHING CAN BREAK)

You're going to send the server a message with a **deliberately invalid trigger name**. The server checks the password first, then rejects the unknown trigger and stops — before it writes anything, arms anything, re-scores anything, or sends any Discord alert.

**This is a completely side-effect-free way to test the password path.** It's why you're not using a real trigger name here.

### Run the probe

Open **PowerShell** (Start menu → type `powershell` → Enter). Paste this whole block, replacing the placeholder with your secret from Phase 1:

```powershell
$uri  = "https://pandoras-box-production.up.railway.app/webhook/circuit_breaker"
$body = '{"trigger":"auth_probe_invalid","secret":"PASTE_YOUR_SECRET_HERE"}'
try {
  $r = Invoke-WebRequest -Uri $uri -Method POST -ContentType "application/json" -Body $body -UseBasicParsing
  "STATUS: $($r.StatusCode)"
} catch {
  "STATUS: $($_.Exception.Response.StatusCode.value__)"
}
```

**Expected: `STATUS: 500`**

500 is the **pass** here. It means the password was accepted and the request got all the way to the trigger name, which was rejected because you made it up. That is exactly what you want to see.

### Check the log

1. Railway → your service → **Deployments** → click the active deployment → **View Logs**
2. Search the logs for `circuit_breaker`
3. You are looking for this line:

```
[circuit_breaker] OBSERVE: payload secret PRESENT, match=True — allowing
```

**`PRESENT` and `match=True` together are the green light.** Nothing else in this runbook matters if you don't see that line.

| What you see | What it means | What to do |
|---|---|---|
| `secret PRESENT, match=True` | Password correct | **Continue to Phase 4** |
| `secret PRESENT, match=False` | Wrong password — mismatch between Railway and what you sent | Stop. Re-check Phase 1 value |
| `secret ABSENT` | Your probe didn't include the secret | Stop. Re-check you pasted it into the PowerShell block |
| `env secret UNSET` | Railway variable is missing | Stop. Go back to Phase 1 STOP CONDITION |
| No log line at all | Message never arrived | Stop. Check the URL for typos |

---

## PHASE 4 — FLIP IT

1. Railway → **pandoras-box** service → **Variables**
2. Click **New Variable**
3. Name: `WEBHOOK_CB_ENFORCE`
4. Value: `1`
5. **Save / Deploy** — the service restarts (~30–60 seconds). This is a restart, not a rebuild from your code.
6. Wait for the service to show healthy before continuing

---

## PHASE 5 — CONFIRM IT ACTUALLY ENFORCES

Two probes. Both are still side-effect-free — same invalid trigger name.

### 5a — Correct password should still get through

Re-run the exact PowerShell block from Phase 3.

**Expected: `STATUS: 500`** — same as before. Password accepted, made-up trigger rejected.

### 5b — Missing password should now be REJECTED

Run this version, with the secret removed entirely:

```powershell
$uri  = "https://pandoras-box-production.up.railway.app/webhook/circuit_breaker"
$body = '{"trigger":"auth_probe_invalid"}'
try {
  $r = Invoke-WebRequest -Uri $uri -Method POST -ContentType "application/json" -Body $body -UseBasicParsing
  "STATUS: $($r.StatusCode)"
} catch {
  "STATUS: $($_.Exception.Response.StatusCode.value__)"
}
```

**Expected: `STATUS: 401`**

**401 is the whole point of this runbook.** Before the flip this returned 500 (allowed through). Now it's refused. The door is shut.

| Result of 5b | Meaning | Action |
|---|---|---|
| **401** | Enforcement live and working | **Done — you're finished** |
| 500 | Still allowing everything — flip didn't take | Check the variable name is spelled exactly `WEBHOOK_CB_ENFORCE`, value `1` |
| **503** | Server can't find the password at all — **breaker is now dead** | **Roll back immediately** (below), then fix Phase 1 |

### Final check

Open `/v2` on the dashboard. Kill-switch tile should still read **CLEAR**. Nothing you did in this runbook arms anything.

---

## ROLLBACK — IF ANYTHING LOOKS WRONG

Instant, no deploy, safe to do from your phone:

1. Railway → **Variables**
2. Set `WEBHOOK_CB_ENFORCE` to `0` — or delete the variable entirely
3. Save. Service restarts. You are back to OBSERVE mode, exactly as before.

Anything other than `1`, `true`, or `yes` turns enforcement off, so `0` is sufficient.

---

## WHAT "DONE" LOOKS LIKE

- [ ] `TRADINGVIEW_WEBHOOK_SECRET` confirmed present and non-empty in Railway
- [ ] Both Circuit Breaker alerts deleted and recreated on TradingView
- [ ] Both indicators' **Webhook Secret** input confirmed populated
- [ ] Probe in OBSERVE returned **500**, log showed `secret PRESENT, match=True`
- [ ] `WEBHOOK_CB_ENFORCE=1` set, service restarted healthy
- [ ] Probe with correct secret returned **500**
- [ ] Probe with no secret returned **401**
- [ ] Dashboard kill-switch still reads CLEAR
- [ ] Date + time of completion recorded for the closure note

---

## NOTES FOR THE RECORD

**Why not wait for a real breaker fire to verify?** The documented cutover procedure in `backend/utils/webhook_auth.py` says to watch for several genuine secret-bearing messages before flipping. Circuit breaker triggers are rare-fire — VIX last fired 2026-06-09 — so waiting could easily run past Aug 4. Your own `docs/phase1-webhook-flip-day-runbook.md` already carries a ruling for exactly this case: verify the alerts exist on-chart, then flip under **Ruling 2 (rare-fire)**. The invalid-trigger probe is strictly better evidence than that ruling requires, since it exercises the real password path end to end.

**One thing this runbook does NOT prove.** It confirms the server accepts a correct password and refuses a missing one. It does not prove TradingView is sending the password, because TradingView won't send anything until a breaker condition actually occurs. Phase 2's re-arm is the mitigation, and it's why re-arming both alerts is mandatory rather than optional. The first real fire after this is the true confirmation — if a genuine breaker condition occurs and the tile does *not* go ARMED, check Railway logs for `[circuit_breaker] rejected — invalid webhook secret` and roll back.

**Known gap, deferred deliberately:** an armed breaker cannot currently be cleared from a phone without an authenticated request, and there is no dashboard button for it. That's covered by the separate vacation card (Part C of the kill-switch brief), not this runbook.
