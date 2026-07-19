"""
Brief #5: Add THALES + DAEDALUS fields to build_committee_embed in pivot2_committee.py.
"""
from pathlib import Path

TARGET = Path("/opt/openclaw/workspace/scripts/pivot2_committee.py")
content = TARGET.read_text(encoding="utf-8")

if "THALES" in content and "\U0001f3db THALES" in content:
    print("Already patched — THALES embed field exists")
    exit(0)

# Insert THALES + DAEDALUS fields after PYTHIA field, before timeframe alignment
OLD_AFTER_PYTHIA = (
    '        {\n'
    '            "name": f"\\U0001f52e PYTHIA ({pythia.get(\'conviction\', \'?\')})",\n'
    '            "value": truncate(pythia.get("analysis", "N/A"), 512),\n'
    '            "inline": True,\n'
    '        },\n'
    '    ]\n'
    '\n'
    '    # Timeframe alignment'
)

NEW_AFTER_PYTHIA = (
    '        {\n'
    '            "name": f"\\U0001f52e PYTHIA ({pythia.get(\'conviction\', \'?\')})",\n'
    '            "value": truncate(pythia.get("analysis", "N/A"), 512),\n'
    '            "inline": True,\n'
    '        },\n'
    '    ]\n'
    '\n'
    '    # THALES + DAEDALUS (Brief #5)\n'
    '    thales = agents.get("thales", {})\n'
    '    daedalus = agents.get("daedalus", {})\n'
    '    thales_analysis = thales.get("analysis", "")\n'
    '    daedalus_analysis = daedalus.get("analysis", "")\n'
    '    _unavail = "[ANALYSIS UNAVAILABLE"\n'
    '    if thales_analysis and not thales_analysis.startswith(_unavail):\n'
    '        fields.append({\n'
    '            "name": f"\\U0001f3db THALES ({thales.get(\'conviction\', \'?\')})",\n'
    '            "value": truncate(thales_analysis, 512),\n'
    '            "inline": True,\n'
    '        })\n'
    '    if daedalus_analysis and not daedalus_analysis.startswith(_unavail):\n'
    '        fields.append({\n'
    '            "name": f"\\U0001f5ff DAEDALUS ({daedalus.get(\'conviction\', \'?\')})",\n'
    '            "value": truncate(daedalus_analysis, 512),\n'
    '            "inline": True,\n'
    '        })\n'
    '\n'
    '    # Timeframe alignment'
)

if OLD_AFTER_PYTHIA not in content:
    print("ERROR: PYTHIA embed anchor not found — check string literals")
    exit(1)

content = content.replace(OLD_AFTER_PYTHIA, NEW_AFTER_PYTHIA)
TARGET.write_text(content, encoding="utf-8")
print(f"Patched {TARGET} — THALES + DAEDALUS embed fields added")
