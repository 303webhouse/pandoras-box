#!/usr/bin/env python3
"""Patch pivot2_committee.py for Brief 4E fixes."""

filepath = "/opt/openclaw/workspace/scripts/pivot2_committee.py"
with open(filepath, "r") as f:
    content = f.read()

# 1. Update imports to add COMBINED_ANALYST_SYSTEM_PROMPT and parse_combined_analyst_response
old_prompts_import = """from committee_prompts import (
    TORO_SYSTEM_PROMPT, URSA_SYSTEM_PROMPT,
    TECHNICALS_SYSTEM_PROMPT, PIVOT_SYSTEM_PROMPT,
)"""
new_prompts_import = """from committee_prompts import (
    TORO_SYSTEM_PROMPT, URSA_SYSTEM_PROMPT,
    TECHNICALS_SYSTEM_PROMPT, PIVOT_SYSTEM_PROMPT,
    COMBINED_ANALYST_SYSTEM_PROMPT,
)"""
content = content.replace(old_prompts_import, new_prompts_import, 1)

old_parsers_import = """from committee_parsers import (
    call_agent, parse_analyst_response,
    parse_pivot_response, DEFAULT_MODEL,
)"""
new_parsers_import = """from committee_parsers import (
    call_agent, parse_analyst_response,
    parse_pivot_response, parse_combined_analyst_response,
    DEFAULT_MODEL,
)"""
content = content.replace(old_parsers_import, new_parsers_import, 1)

# 2. Replace the 3 individual analyst calls with 1 combined call
old_three_calls = """    # ── TORO ANALYST ──
    log.info("Calling TORO agent...")
    toro_raw = call_agent(
        system_prompt=TORO_SYSTEM_PROMPT,
        user_message=_agent_context("TORO"),
        api_key=api_key,
        max_tokens=500,
        temperature=0.3,
        agent_name="TORO",
        model=COMMITTEE_MODEL,
    )
    if toro_raw:
        toro_response = parse_analyst_response(toro_raw, "TORO")
    else:
        toro_response = {
            "agent": "TORO",
            "analysis": "[ANALYSIS UNAVAILABLE — TORO agent timed out]",
            "conviction": "MEDIUM",
        }

    # ── URSA ANALYST ──
    log.info("Calling URSA agent...")
    ursa_raw = call_agent(
        system_prompt=URSA_SYSTEM_PROMPT,
        user_message=_agent_context("URSA"),
        api_key=api_key,
        max_tokens=500,
        temperature=0.3,
        agent_name="URSA",
        model=COMMITTEE_MODEL,
    )
    if ursa_raw:
        ursa_response = parse_analyst_response(ursa_raw, "URSA")
    else:
        ursa_response = {
            "agent": "URSA",
            "analysis": "[ANALYSIS UNAVAILABLE — URSA agent timed out]",
            "conviction": "MEDIUM",
        }

    # ── TECHNICALS ANALYST ──
    log.info("Calling TECHNICALS agent...")
    technicals_raw = call_agent(
        system_prompt=TECHNICALS_SYSTEM_PROMPT,
        user_message=_agent_context("TECHNICALS"),
        api_key=api_key,
        max_tokens=750,
        temperature=0.3,
        agent_name="TECHNICALS",
        model=COMMITTEE_MODEL,
    )
    if technicals_raw:
        technicals_response = parse_analyst_response(technicals_raw, "TECHNICALS")
    else:
        technicals_response = {
            "agent": "TECHNICALS",
            "analysis": "[ANALYSIS UNAVAILABLE — TECHNICALS agent timed out]",
            "conviction": "MEDIUM",
        }"""

new_combined_call = """    # ── COMBINED ANALYST (TORO + URSA + TECHNICALS in one call) ──
    log.info("Calling combined analyst agent (TORO + URSA + TECHNICALS)...")
    combined_raw = call_agent(
        system_prompt=COMBINED_ANALYST_SYSTEM_PROMPT,
        user_message=base_context,
        api_key=api_key,
        max_tokens=1500,
        temperature=0.3,
        agent_name="ANALYSTS",
        model=COMMITTEE_MODEL,
    )
    if combined_raw:
        parsed_analysts = parse_combined_analyst_response(combined_raw)
        toro_response = parsed_analysts["toro"]
        ursa_response = parsed_analysts["ursa"]
        technicals_response = parsed_analysts["technicals"]
    else:
        toro_response = {
            "agent": "TORO",
            "analysis": "[ANALYSIS UNAVAILABLE — combined agent call failed]",
            "conviction": "MEDIUM",
        }
        ursa_response = {
            "agent": "URSA",
            "analysis": "[ANALYSIS UNAVAILABLE — combined agent call failed]",
            "conviction": "MEDIUM",
        }
        technicals_response = {
            "agent": "TECHNICALS",
            "analysis": "[ANALYSIS UNAVAILABLE — combined agent call failed]",
            "conviction": "MEDIUM",
        }"""

content = content.replace(old_three_calls, new_combined_call, 1)

# 3. Update raw_responses to reflect combined call
old_raw = """        "raw_responses": {
            "toro": toro_raw,
            "ursa": ursa_raw,
            "technicals": technicals_raw,
            "pivot": pivot_raw,
        },"""
new_raw = """        "raw_responses": {
            "combined_analysts": combined_raw,
            "pivot": pivot_raw,
        },"""
content = content.replace(old_raw, new_raw, 1)

with open(filepath, "w") as f:
    f.write(content)

print("OK - pivot2_committee.py patched")
print(f"  File size: {len(content)} bytes")

# Verify the changes
if "COMBINED_ANALYST_SYSTEM_PROMPT" in content:
    print("  COMBINED_ANALYST_SYSTEM_PROMPT import: OK")
else:
    print("  WARNING: COMBINED_ANALYST_SYSTEM_PROMPT import not found!")

if "parse_combined_analyst_response" in content:
    print("  parse_combined_analyst_response import: OK")
else:
    print("  WARNING: parse_combined_analyst_response import not found!")

if 'agent_name="ANALYSTS"' in content:
    print("  Combined analyst call: OK")
else:
    print("  WARNING: Combined analyst call not found!")

if '"combined_analysts": combined_raw' in content:
    print("  raw_responses update: OK")
else:
    print("  WARNING: raw_responses update not found!")
