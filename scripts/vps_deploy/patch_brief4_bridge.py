"""
Brief #4: Fix committee_railway_bridge.py to pass technical_data to run_committee.
Brief #5: Extract thales/daedalus from recommendation.
"""
from pathlib import Path

TARGET = Path("/opt/openclaw/workspace/scripts/committee_railway_bridge.py")
content = TARGET.read_text(encoding="utf-8")

# Change 1: pass technical_data to run_committee
OLD_CALL = "        context = get_cached_context(signal, api_url, api_key, build_market_context)\n        recommendation = run_committee(signal, context, anthropic_key)"
NEW_CALL = (
    "        context = get_cached_context(signal, api_url, api_key, build_market_context)\n"
    "        # Brief #4: fetch per-ticker technical snapshot\n"
    "        try:\n"
    "            from committee_context import fetch_technical_snapshot as _fetch_tech\n"
    "            _tech_ticker = signal.get(\"ticker\", \"\")\n"
    "            tech_data = _fetch_tech(_tech_ticker) if _tech_ticker else {}\n"
    "        except Exception as _te:\n"
    "            log.warning(\"Tech snapshot failed for %s: %s\", signal.get(\"ticker\"), _te)\n"
    "            tech_data = {}\n"
    "        recommendation = run_committee(signal, context, anthropic_key, technical_data=tech_data)"
)

if OLD_CALL not in content:
    print("ERROR: run_committee call anchor not found — check spacing")
    exit(1)

if "technical_data=tech_data" in content:
    print("Already patched — technical_data already wired, skipping change 1")
else:
    content = content.replace(OLD_CALL, NEW_CALL)
    print("Patched: run_committee now passes technical_data")

# Change 2: extract thales/daedalus after ursa/technicals
OLD_EXTRACT = (
    "        ursa = recommendation.get(\"agents\", {}).get(\"ursa\", {})\n"
    "        technicals = recommendation.get(\"agents\", {}).get(\"technicals\", {})"
)
NEW_EXTRACT = (
    "        ursa = recommendation.get(\"agents\", {}).get(\"ursa\", {})\n"
    "        technicals = recommendation.get(\"agents\", {}).get(\"technicals\", {})\n"
    "        thales = recommendation.get(\"agents\", {}).get(\"thales\", {})\n"
    "        daedalus = recommendation.get(\"agents\", {}).get(\"daedalus\", {})"
)

if OLD_EXTRACT not in content:
    print("WARNING: extraction anchor not found — skipping change 2")
elif "thales = recommendation.get" in content:
    print("Already patched — thales extraction exists, skipping change 2")
else:
    content = content.replace(OLD_EXTRACT, NEW_EXTRACT)
    print("Patched: added thales/daedalus extraction")

TARGET.write_text(content, encoding="utf-8")
print(f"Done patching {TARGET}")
