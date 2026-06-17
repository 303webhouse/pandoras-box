# Brief: Anthropic Credit Balance Monitor — Pre-Market Check

**Date:** 2026-04-21
**Priority:** P1 (not blocking trading, but prevents the failure mode we hit 4/16)
**Target:** Claude Code (VSCode)
**Estimated effort:** 20-30 min

## Configuration values (provided by Nick)

```
ANTHROPIC_ORG_ID = 773cd012-fcd6-4fb7-87ad-4363951db502
NICK_USER_ID     = 339527833674317824     # Discord user ID for @-ping
```

Remaining open config question: which Discord channel ID to use for the CRITICAL ping. Use the existing `COMMITTEE_CHANNEL_ID` unless Nick designates a separate ops channel.

**Origin:** On 2026-04-16 Anthropic credits exhausted. Committee bridge kept running the cron, but every run failed with "Your credit balance is too low." SNOW + CRM signals hit the 3-retry max and are now permanently stuck. Nick had no visibility into this until running a full bridge diagnostic on 2026-04-21.

---

## Objective

Add a credit-balance health check to the pre-market briefing so the bridge never silently fails on a funding issue again. Target: see the warning in Discord at 7:30 AM ET, not discover it 5 days later when signals are permanently stuck.

---

## Requirements

1. **New VPS script:** `/opt/openclaw/workspace/scripts/anthropic_credit_check.py`
2. Called from the existing pre-market briefing (11:30 UTC = 7:30 AM ET, weekdays) — append to the end of the briefing Discord post
3. Hits Anthropic's credit-balance endpoint — verify exact path at https://docs.claude.com/en/api before coding
4. **Alert thresholds:**
   - Balance < $25: add LOW CREDIT warning line to briefing
   - Balance < $10: add CRITICAL CREDIT line AND post a separate pinging message to Nick in Discord
   - Balance >= $25: silent (no noise in normal operation)
5. **Burn-rate projection:** read last 7 days of `/var/log/committee_audit.log` to estimate $/day, divide balance by rate, display "X days remaining at current burn"
6. **Fail-open:** if the credit-check call itself errors, log it but do NOT break the pre-market briefing

---

## Implementation details

### File 1: `/opt/openclaw/workspace/scripts/anthropic_credit_check.py`

```python
#!/usr/bin/env python3
"""
Anthropic credit balance health check.
Called from premarket_briefing.py to append credit status to the briefing.
"""
import os
import json
import logging
import pathlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_ORG_ID = os.environ.get("ANTHROPIC_ORG_ID")

AUDIT_LOG = pathlib.Path("/var/log/committee_audit.log")

LOW_THRESHOLD = 25.0
CRITICAL_THRESHOLD = 10.0


def fetch_credit_balance():
    """
    Returns current Anthropic credit balance in USD, or None on error.
    NOTE: Verify the exact endpoint at docs.claude.com/en/api before coding.
    Fallback if no public endpoint exists:
      - Call /v1/messages with a minimal request; on 402/403, parse error body
        for "credit balance is too low" and surface that as a critical state.
    """
    if not ANTHROPIC_API_KEY or not ANTHROPIC_ORG_ID:
        log.warning("ANTHROPIC_API_KEY or ANTHROPIC_ORG_ID not set - skipping credit check")
        return None

    url = f"https://api.anthropic.com/v1/organizations/{ANTHROPIC_ORG_ID}/credits"
    req = urllib.request.Request(
        url,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return float(data.get("balance_usd", data.get("credits", {}).get("balance", 0)))
    except urllib.error.HTTPError as e:
        log.error("Credit check HTTP error %s: %s", e.code, e.read()[:300])
        return None
    except Exception as e:
        log.error("Credit check failed: %s", e)
        return None


def estimate_daily_burn():
    """Read committee_audit.log for last 7 days, estimate daily $ burn."""
    if not AUDIT_LOG.exists():
        return 0.15 * 10

    cutoff = datetime.utcnow() - timedelta(days=7)
    runs_by_day = {}
    try:
        with AUDIT_LOG.open() as f:
            for line in f:
                if "committee_run" in line or "run_committee" in line:
                    try:
                        parts = line.split()
                        ts_str = parts[0] + " " + parts[1]
                        ts = datetime.fromisoformat(ts_str.replace(",", "."))
                        if ts > cutoff:
                            day = ts.strftime("%Y-%m-%d")
                            runs_by_day[day] = runs_by_day.get(day, 0) + 1
                    except Exception:
                        continue
    except Exception as e:
        log.warning("Could not parse audit log: %s", e)
        return 0.15 * 10

    if not runs_by_day:
        return 0.0
    avg_runs = sum(runs_by_day.values()) / max(len(runs_by_day), 1)
    return avg_runs * 0.15


def build_status_block():
    """
    Returns (markdown_string, is_critical).
    is_critical=True triggers a separate Discord alert in addition to the briefing block.
    """
    balance = fetch_credit_balance()
    if balance is None:
        return ("", False)

    burn = estimate_daily_burn()
    days_left = (balance / burn) if burn > 0 else 999

    if balance < CRITICAL_THRESHOLD:
        msg = (
            f"**CRITICAL: Anthropic credits ${balance:.2f}** "
            f"(~{days_left:.1f}d at ${burn:.2f}/day). "
            f"Committee bridge will start failing. Top up NOW at console.anthropic.com."
        )
        return (msg, True)
    elif balance < LOW_THRESHOLD:
        msg = (
            f"**LOW: Anthropic credits ${balance:.2f}** "
            f"(~{days_left:.1f}d at ${burn:.2f}/day). Top up soon."
        )
        return (msg, False)
    else:
        return (f"Anthropic credits: ${balance:.2f} (~{days_left:.0f}d runway)", False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    block, critical = build_status_block()
    print(block)
    if critical:
        exit(2)
```

### File 2: `premarket_briefing.py` — splice in the credit block

Find where the briefing builds its final Discord message. Add at the end, just before posting:

```python
# Credit balance health check
try:
    from anthropic_credit_check import build_status_block as _credit_block
    credit_msg, credit_critical = _credit_block()
    if credit_msg:
        briefing_md += f"\n\n---\n{credit_msg}\n"
    if credit_critical:
        post_discord_message(
            discord_token,
            NICK_DM_CHANNEL_ID,
            f"<@{NICK_USER_ID}> {credit_msg}",
        )
except Exception as e:
    log.error("Credit check failed (non-fatal): %s", e)
```

### File 3: `/etc/openclaw/openclaw.env` — add env var

```
ANTHROPIC_ORG_ID=<paste from console.anthropic.com/settings/organization>
```

(`ANTHROPIC_API_KEY` is already present — the bridge uses it.)

---

## Verification steps (run after deploy)

1. SSH to VPS, invoke the check manually:
   ```bash
   cd /opt/openclaw/workspace/scripts
   source /etc/openclaw/openclaw.env
   python3 anthropic_credit_check.py
   ```
   Expected: prints a status line, exits 0 (or 2 if critical).

2. Force a "low" case by temporarily setting `LOW_THRESHOLD = 9999`, rerun, confirm warning appears.
3. Force a "critical" case by setting `CRITICAL_THRESHOLD = 9999`, confirm both briefing block AND separate Discord ping.
4. Revert thresholds. Run the real briefing:
   ```bash
   python3 premarket_briefing.py
   ```
   Confirm credit block appears at bottom of Discord briefing.
5. Let it run one real pre-market cycle, verify no regressions.

---

## Questions for Nick that might block implementation

1. **Does Anthropic expose a balance-check endpoint in current API?** Verify at docs.claude.com/en/api BEFORE coding `fetch_credit_balance()`. If not, use the message-attempt-and-parse-error fallback.
2. **Which Discord channel gets the critical alert?** Existing `COMMITTEE_CHANNEL_ID`, or dedicated ops channel?
3. **Nick's Discord user ID for the ping?** Needed for `<@{NICK_USER_ID}>`.

---

## Related cleanup (include in same PR)

While in the committee bridge codebase, fix these non-fatal bugs spotted 2026-04-21:

1. `Earnings check failed: 'dict' object has no attribute 'empty'`
   - Expects pandas DataFrame, receiving dict. Wrap in `if hasattr(df, "empty"): df.empty else not df`.

2. `fetch_pythia_events failed: name 'os' is not defined`
   - Missing `import os` at top of whichever module defines `fetch_pythia_events`.

---

## Out of scope for this brief (follow-up briefs)

- Distinguishing "credit error" from other API errors for retry-limit bypass. Worth doing but separate change: make the bridge's retry logic treat `CreditExhaustedError` as "pause all, don't count against retries" instead of burning the 3-strike limit.
- Auto-topping-up credits via Anthropic's billing API. Too risky — keep manual approval.

---

## Done when

- [ ] `anthropic_credit_check.py` committed to `/opt/openclaw/workspace/scripts/`
- [ ] `premarket_briefing.py` calls it and appends to Discord message
- [ ] `ANTHROPIC_ORG_ID` in `/etc/openclaw/openclaw.env`
- [ ] Manual verification of healthy / low / critical paths all pass
- [ ] One real pre-market briefing cycle completes with new block visible
- [ ] Two non-fatal bugs fixed in same PR
