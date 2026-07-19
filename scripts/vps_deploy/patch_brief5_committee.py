"""
Brief #4 + #5: Patch pivot2_committee.py:
- Wire flow_events context injection (Brief #4)
- Extract thales/daedalus from parsed (Brief #5)
- Bump combined analyst max_tokens 2500 -> 3500 (Brief #5)
- Add thales/daedalus to pivot_context (Brief #5)
- Add thales/daedalus to return dict (Brief #5)
"""
from pathlib import Path

TARGET = Path("/opt/openclaw/workspace/scripts/pivot2_committee.py")
content = TARGET.read_text(encoding="utf-8")

# ── Change 1: Inject flow_events context (Brief #4) ──────────────────────────
# Insert after Pythia events injection block
OLD_PYTHIA_INJECT = (
    "    # ── COMBINED ANALYSTS (TORO + URSA + TECHNICALS + PYTHIA in one call) ──"
)
NEW_PYTHIA_INJECT = (
    "    # Inject per-ticker flow_events DB context (Brief #4)\n"
    "    try:\n"
    "        from committee_context import fetch_flow_events_context\n"
    "        _flow_ticker = signal.get(\"ticker\", \"\")\n"
    "        if _flow_ticker:\n"
    "            flow_events_block = fetch_flow_events_context(_flow_ticker)\n"
    "            if flow_events_block:\n"
    "                base_context = base_context + \"\\n\\n\" + flow_events_block\n"
    "    except Exception as e:\n"
    "        log.warning(\"Failed to inject flow_events context: %s\", e)\n"
    "\n"
    "    # ── COMBINED ANALYSTS (TORO + URSA + TECHNICALS + PYTHIA in one call) ──"
)

if "fetch_flow_events_context" in content:
    print("Already patched — flow_events injection exists, skipping change 1")
elif OLD_PYTHIA_INJECT not in content:
    print("ERROR: combined analysts anchor not found — check spacing")
    exit(1)
else:
    content = content.replace(OLD_PYTHIA_INJECT, NEW_PYTHIA_INJECT)
    print("Patched: flow_events context injection added")

# ── Change 2: Bump max_tokens 2500 → 3500 for combined analyst call ──────────
OLD_TOKENS = (
    "        max_tokens=2500,\n"
    "        temperature=0.3,\n"
    "        agent_name=\"ANALYSTS\","
)
NEW_TOKENS = (
    "        max_tokens=3500,\n"
    "        temperature=0.3,\n"
    "        agent_name=\"ANALYSTS\","
)

if "max_tokens=3500" in content:
    print("Already patched — max_tokens already 3500, skipping change 2")
elif OLD_TOKENS not in content:
    print("WARNING: max_tokens anchor not found — skipping change 2")
else:
    content = content.replace(OLD_TOKENS, NEW_TOKENS)
    print("Patched: combined analyst max_tokens 2500 -> 3500")

# ── Change 3: Extract thales/daedalus from parsed ────────────────────────────
OLD_PARSE = (
    "        toro_response = parsed[\"toro\"]\n"
    "        ursa_response = parsed[\"ursa\"]\n"
    "        technicals_response = parsed[\"technicals\"]\n"
    "        pythia_response = parsed[\"pythia\"]"
)
NEW_PARSE = (
    "        toro_response = parsed[\"toro\"]\n"
    "        ursa_response = parsed[\"ursa\"]\n"
    "        technicals_response = parsed[\"technicals\"]\n"
    "        pythia_response = parsed[\"pythia\"]\n"
    "        thales_response = parsed[\"thales\"]\n"
    "        daedalus_response = parsed[\"daedalus\"]"
)

if "thales_response = parsed" in content:
    print("Already patched — thales_response extraction exists, skipping change 3")
elif OLD_PARSE not in content:
    print("ERROR: parsed extraction anchor not found")
    exit(1)
else:
    content = content.replace(OLD_PARSE, NEW_PARSE)
    print("Patched: thales/daedalus extracted from parsed")

# ── Change 4: Add thales/daedalus fallbacks ───────────────────────────────────
OLD_FALLBACK = (
    "        toro_response = {**fallback, \"agent\": \"TORO\"}\n"
    "        ursa_response = {**fallback, \"agent\": \"URSA\"}\n"
    "        technicals_response = {**fallback, \"agent\": \"TECHNICALS\"}\n"
    "        pythia_response = {**fallback, \"agent\": \"PYTHIA\"}"
)
NEW_FALLBACK = (
    "        toro_response = {**fallback, \"agent\": \"TORO\"}\n"
    "        ursa_response = {**fallback, \"agent\": \"URSA\"}\n"
    "        technicals_response = {**fallback, \"agent\": \"TECHNICALS\"}\n"
    "        pythia_response = {**fallback, \"agent\": \"PYTHIA\"}\n"
    "        thales_response = {**fallback, \"agent\": \"THALES\"}\n"
    "        daedalus_response = {**fallback, \"agent\": \"DAEDALUS\"}"
)

if "thales_response = {**fallback" in content:
    print("Already patched — thales fallback exists, skipping change 4")
elif OLD_FALLBACK not in content:
    print("ERROR: fallback anchor not found")
    exit(1)
else:
    content = content.replace(OLD_FALLBACK, NEW_FALLBACK)
    print("Patched: thales/daedalus fallbacks added")

# ── Change 5: Add thales/daedalus raw trackers ───────────────────────────────
OLD_RAW = (
    "    toro_raw = combined_raw\n"
    "    ursa_raw = combined_raw\n"
    "    technicals_raw = combined_raw\n"
    "    pythia_raw = combined_raw"
)
NEW_RAW = (
    "    toro_raw = combined_raw\n"
    "    ursa_raw = combined_raw\n"
    "    technicals_raw = combined_raw\n"
    "    pythia_raw = combined_raw\n"
    "    thales_raw = combined_raw\n"
    "    daedalus_raw = combined_raw"
)

if "thales_raw = combined_raw" in content:
    print("Already patched — thales_raw exists, skipping change 5")
elif OLD_RAW not in content:
    print("WARNING: raw trackers anchor not found — skipping change 5")
else:
    content = content.replace(OLD_RAW, NEW_RAW)
    print("Patched: thales/daedalus raw trackers added")

# ── Change 6: Add thales/daedalus to pivot_context ───────────────────────────
OLD_PIVOT_CTX = (
    '        f"## PYTHIA (MARKET PROFILE) REPORT\\n"\n'
    '        f"Analysis: {pythia_response[\'analysis\']}\\n"\n'
    '        f"Conviction: {pythia_response[\'conviction\']}"\n'
    '        f"{bias_challenge}"'
)
NEW_PIVOT_CTX = (
    '        f"## PYTHIA (MARKET PROFILE) REPORT\\n"\n'
    '        f"Analysis: {pythia_response[\'analysis\']}\\n"\n'
    '        f"Conviction: {pythia_response[\'conviction\']}\\n\\n"\n'
    '        f"## THALES (SECTOR/MACRO) REPORT\\n"\n'
    '        f"Analysis: {thales_response[\'analysis\']}\\n"\n'
    '        f"Conviction: {thales_response[\'conviction\']}\\n\\n"\n'
    '        f"## DAEDALUS (OPTIONS/DERIVATIVES) REPORT\\n"\n'
    '        f"Analysis: {daedalus_response[\'analysis\']}\\n"\n'
    '        f"Conviction: {daedalus_response[\'conviction\']}"\n'
    '        f"{bias_challenge}"'
)

if "THALES (SECTOR/MACRO) REPORT" in content:
    print("Already patched — THALES in pivot_context exists, skipping change 6")
elif OLD_PIVOT_CTX not in content:
    print("ERROR: pivot_context PYTHIA anchor not found — check string literals")
    exit(1)
else:
    content = content.replace(OLD_PIVOT_CTX, NEW_PIVOT_CTX)
    print("Patched: thales/daedalus added to pivot_context")

# ── Change 7: Add thales/daedalus to return dict ─────────────────────────────
OLD_RETURN = (
    '            "toro": toro_response,\n'
    '            "ursa": ursa_response,\n'
    '            "technicals": technicals_response,\n'
    '            "pythia": pythia_response,\n'
    '            "pivot": pivot_response,'
)
NEW_RETURN = (
    '            "toro": toro_response,\n'
    '            "ursa": ursa_response,\n'
    '            "technicals": technicals_response,\n'
    '            "pythia": pythia_response,\n'
    '            "thales": thales_response,\n'
    '            "daedalus": daedalus_response,\n'
    '            "pivot": pivot_response,'
)

if '"thales": thales_response,' in content:
    print("Already patched — thales in return dict, skipping change 7")
elif OLD_RETURN not in content:
    print("ERROR: return dict anchor not found")
    exit(1)
else:
    content = content.replace(OLD_RETURN, NEW_RETURN)
    print("Patched: thales/daedalus added to return dict")

# ── Change 8: Add thales/daedalus to raw_responses ───────────────────────────
OLD_RAW_RESP = (
    '            "toro": toro_raw,\n'
    '            "ursa": ursa_raw,\n'
    '            "technicals": technicals_raw,\n'
    '            "pythia": pythia_raw,\n'
    '            "pivot": pivot_raw,'
)
NEW_RAW_RESP = (
    '            "toro": toro_raw,\n'
    '            "ursa": ursa_raw,\n'
    '            "technicals": technicals_raw,\n'
    '            "pythia": pythia_raw,\n'
    '            "thales": thales_raw,\n'
    '            "daedalus": daedalus_raw,\n'
    '            "pivot": pivot_raw,'
)

if '"thales": thales_raw,' in content:
    print("Already patched — thales in raw_responses, skipping change 8")
elif OLD_RAW_RESP not in content:
    print("WARNING: raw_responses anchor not found — skipping change 8")
else:
    content = content.replace(OLD_RAW_RESP, NEW_RAW_RESP)
    print("Patched: thales/daedalus added to raw_responses")

TARGET.write_text(content, encoding="utf-8")
print(f"Done patching {TARGET}")
