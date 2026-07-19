"""
Brief #5: Extend parse_combined_analyst_response to handle THALES + DAEDALUS sections.
"""
from pathlib import Path

TARGET = Path("/opt/openclaw/workspace/scripts/committee_parsers.py")
content = TARGET.read_text(encoding="utf-8")

# Change 1: add THALES + DAEDALUS to agent_names list
OLD_NAMES = '    agent_names = ["TORO", "URSA", "TECHNICALS", "PYTHIA"]'
NEW_NAMES = '    agent_names = ["TORO", "URSA", "TECHNICALS", "PYTHIA", "THALES", "DAEDALUS"]'

if OLD_NAMES not in content:
    if "THALES" in content:
        print("Already patched — THALES already in agent_names, skipping")
    else:
        print("ERROR: agent_names anchor not found")
        exit(1)
else:
    content = content.replace(OLD_NAMES, NEW_NAMES)
    print("Patched: THALES + DAEDALUS added to agent_names")

# Change 2: update return dict to include thales + daedalus
OLD_RETURN = '''    result = {}
    for agent in agent_names:
        if agent in sections:
            result[agent.lower()] = parse_analyst_response(sections[agent], agent)
        else:
            result[agent.lower()] = {
                "agent": agent,
                "analysis": f"[ANALYSIS UNAVAILABLE - {agent} section not found in combined response]",
                "conviction": "MEDIUM",
            }

    return result'''

# This block is already generic — since agent_names now includes THALES/DAEDALUS,
# the loop will automatically handle them. No additional change needed here.
# Just verify the loop is present.
if "for agent in agent_names:" in content:
    print("Parser loop is generic — THALES/DAEDALUS will be handled automatically")
else:
    print("WARNING: generic parser loop not found — manual check needed")

TARGET.write_text(content, encoding="utf-8")
print(f"Done patching {TARGET}")
