#!/usr/bin/env python3
"""
One-shot patch: Anthropic Credit Monitor brief (2026-04-21)

Applies three changes to VPS scripts:
  1. pivot2_committee.py  — fix earnings check (yfinance dict vs DataFrame)
  2. committee_context.py — add missing `import os`
  3. premarket_briefing.py — splice in credit balance health check

Run once, then delete:
  python3 /opt/openclaw/workspace/scripts/patch_credit_monitor.py
"""
import pathlib
import sys

SCRIPTS = pathlib.Path("/opt/openclaw/workspace/scripts")


def apply(label: str, path: pathlib.Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    if old not in content:
        print(f"  SKIP {label}: pattern not found (already patched?)")
        return
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
    print(f"  OK   {label}")


# ── Bug 1: pivot2_committee.py — earnings check (yfinance dict/DataFrame) ──
apply(
    "pivot2_committee earnings check",
    SCRIPTS / "pivot2_committee.py",
    old=(
        'not cal.empty and "Earnings Date" in cal.index:\n'
        '            earn_date = cal.loc["Earnings Date"][0]\n'
        '            if hasattr(earn_date, "date"):\n'
        '                earn_date = earn_date.date()'
    ),
    new=(
        'isinstance(cal, dict) and "Earnings Date" in cal:\n'
        '            earn_dates = cal["Earnings Date"]\n'
        '            earn_date = earn_dates[0] if isinstance(earn_dates, list) else earn_dates\n'
        '            if hasattr(earn_date, "date"):\n'
        '                earn_date = earn_date.date()'
    ),
)

# ── Bug 2: committee_context.py — missing `import os` ──────────────────────
apply(
    "committee_context import os",
    SCRIPTS / "committee_context.py",
    old="from pathlib import Path\n",
    new="from pathlib import Path\nimport os\n",
)

# ── Splice: premarket_briefing.py — credit check before Discord post ────────
apply(
    "premarket_briefing credit check splice",
    SCRIPTS / "premarket_briefing.py",
    old=(
        "    if webhook:\n"
        "        post_to_discord(webhook, briefing)\n"
    ),
    new=(
        "    # Anthropic credit balance health check (fail-open — never breaks briefing)\n"
        "    try:\n"
        "        from anthropic_credit_check import (\n"
        "            build_status_block as _credit_block,\n"
        "            post_critical_alert as _credit_alert,\n"
        "        )\n"
        "        _credit_msg, _credit_critical = _credit_block()\n"
        "        if _credit_msg:\n"
        '            briefing["synthesis"] = (\n'
        '                briefing.get("synthesis", "") + f"\\n\\n---\\n{_credit_msg}"\n'
        "            )\n"
        "        if _credit_critical:\n"
        "            _credit_alert(_credit_msg)\n"
        "    except Exception as _ce:\n"
        '        log.error("Credit check failed (non-fatal): %s", _ce)\n'
        "\n"
        "    if webhook:\n"
        "        post_to_discord(webhook, briefing)\n"
    ),
)

print("\nAll patches applied. Verify with:")
print("  python3 -c \"from anthropic_credit_check import build_status_block; print(build_status_block())\"")
print("  grep -n 'credit_block' /opt/openclaw/workspace/scripts/premarket_briefing.py")
print("  grep -n 'isinstance.*dict.*Earnings' /opt/openclaw/workspace/scripts/pivot2_committee.py")
print("  grep -n 'import os' /opt/openclaw/workspace/scripts/committee_context.py")
