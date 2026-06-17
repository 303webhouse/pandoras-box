# Brief: CreditExhaustedError should NOT burn signal retry counter

**Date:** 2026-04-21
**Priority:** P1 (prevents permanent signal-stuck state during any future credit outage)
**Target:** Claude Code (VSCode)
**Estimated effort:** 20-30 min

---

## Context

The 2026-04-16 credit exhaustion caused SNOW and CRM signals to permanently stick in `COMMITTEE_REVIEW` because each bridge cron cycle counted as a retry attempt. After 3 cycles, the signals hit `MAX_SIGNAL_ATTEMPTS` and got permanently blacklisted — even though the failure was infrastructure-level (no credits), not signal-level (bad data / parse error / etc.).

Current bridge logic in `/opt/openclaw/workspace/scripts/committee_railway_bridge.py` (around lines 390-450):

```python
if attempts >= MAX_SIGNAL_ATTEMPTS:
    log.warning("Skipping %s — max retries exhausted", ...)
    continue

# Count attempt BEFORE running (prevents uncapped retries)
daily["count"] += 1
daily["signal_ids"].append(signal_id)
save_daily_count(daily)

retries[signal_id] = {
    "attempts": attempts + 1,
    ...
}
save_retry_tracker(retries)

result = run_committee_on_signal(signal)

# Circuit breaker: credit/auth error -> stop entire batch
if result == "CREDIT_EXHAUSTED":
    retries[signal_id]["last_error"] = "credit/auth exhausted"
    save_retry_tracker(retries)
    log.error("Credit/auth exhausted — halting all processing")
    break
```

**The bug:** attempt counter is incremented BEFORE the committee call. When the call returns `CREDIT_EXHAUSTED`, the batch halts but the attempt has already been counted. Next cron tick, attempt count is one higher. After 3 ticks during a credit outage, signal is permanently stuck.

---

## Required behavior change

When `run_committee_on_signal` returns `CREDIT_EXHAUSTED`:
1. **Decrement the signal's attempt counter back to its pre-run state** (so this run doesn't count against the signal's retry budget)
2. **Remove the signal from today's `dedup_keys` / `signal_ids` array** (so when credits are restored, the bridge doesn't skip it as "already processed today")
3. Halt the batch (existing behavior, keep)

Same behavior should apply to any future `TransientInfraError` class we add (rate limits, 5xx, timeouts that aren't the signal's fault).

---

## Implementation

Edit `/opt/openclaw/workspace/scripts/committee_railway_bridge.py`. Find the block that counts the attempt:

```python
# Count attempt BEFORE running (prevents uncapped retries)
daily["count"] += 1
daily["signal_ids"].append(signal_id)
save_daily_count(daily)

retries[signal_id] = {
    "attempts": attempts + 1,
    "last_attempt": datetime.utcnow().isoformat(),
    "last_error": None,
}
save_retry_tracker(retries)
```

And the CREDIT_EXHAUSTED handler:

```python
if result == "CREDIT_EXHAUSTED":
    retries[signal_id]["last_error"] = "credit/auth exhausted"
    save_retry_tracker(retries)
    log.error("Credit/auth exhausted — halting all processing")
    break
```

Replace the CREDIT_EXHAUSTED handler with:

```python
if result == "CREDIT_EXHAUSTED":
    # Infra-level failure — don't penalize the signal
    # Roll back the attempt counter and dedup entry
    log.warning("Credit/auth exhausted on %s — rolling back attempt counter", signal_id)
    retries[signal_id] = {
        "attempts": attempts,  # restore to pre-run value
        "last_attempt": retries.get(signal_id, {}).get("last_attempt"),
        "last_error": "credit/auth exhausted — not counted against retries",
    }
    save_retry_tracker(retries)

    # Remove from today's dedup so the bridge re-attempts when credits restore
    if signal_id in daily.get("signal_ids", []):
        daily["signal_ids"].remove(signal_id)
    daily["count"] = max(0, daily["count"] - 1)
    save_daily_count(daily)

    log.error("Credit/auth exhausted — halting all processing")
    break
```

---

## Extend the pattern to other transient failures

Define a small set of "infra transient" error classes that should use the same rollback logic. Start with just `CreditExhaustedError`. Later candidates for the same treatment:

- Railway API 5xx on context fetch (not the signal's fault)
- UW API rate limit (429)
- Anthropic API 529 (overloaded)
- Network timeout (no response)

For now, only `CREDIT_EXHAUSTED` gets the rollback. Flag the others as a follow-up.

---

## Verification

1. Manually simulate credit exhaustion in a staging/test run:
   - Temporarily change `run_committee_on_signal` to always return `"CREDIT_EXHAUSTED"` for one specific signal ID
   - Pre-populate `bridge_signal_attempts.json` with that signal at `attempts=0`
   - Run bridge manually: `python3 committee_railway_bridge.py`
   - Confirm: `bridge_signal_attempts.json` shows `attempts=0` after (NOT `attempts=1`)
   - Confirm: signal NOT in today's `bridge_daily_count.json` dedup list
   - Confirm: `daily["count"]` decremented back
   - Run again immediately: bridge should re-attempt the same signal, not skip it
2. Revert the test modification.
3. In production, after fix is deployed, if a credit outage occurs again, verify via `/var/log/committee_bridge.log` that signals are NOT being blacklisted.

---

## Done when

- [ ] Handler in `committee_railway_bridge.py` rolls back attempt counter + dedup on CREDIT_EXHAUSTED
- [ ] Local staging test confirms rollback behavior
- [ ] Deployed to VPS
- [ ] Comment in code explains the rationale (so a future CC doesn't "fix" it back)
