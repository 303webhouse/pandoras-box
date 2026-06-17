r"""L0.4 coverage check — every presentation surface shows the codename.

Two checks, both static / no DB:

  1. MAP — the canonical map (backend/config/strategy_aliases.py) resolves the
     full rebuild roster to the expected codenames.
  2. SURFACES — each known presentation surface is wired to the alias layer
     (references codename / the JS display helpers / the script-local resolver).
     This guards against a surface drifting back to a raw-only render.

The raw signal_type/strategy logic/CSS/filter sites are intentionally NOT
required to reference the alias (they must stay raw). This check only asserts
the DISPLAY surfaces are covered.

Run from C:\trading-hub (or the l0-alias worktree):
    python scripts\l0_alias_coverage_check.py
Exits non-zero if any check fails.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from config.strategy_aliases import codename  # noqa: E402

# Roster (master brief §11): raw identifier -> expected codename.
EXPECTED = [
    # (signal_type, strategy, expected_codename)
    ("GOLDEN_TOUCH", "CTA Scanner", "Midas"),
    ("TRAPPED_SHORTS", "CTA Scanner", "Hector"),
    ("APIS_CALL", "CTA Scanner", "Apis"),
    ("KODIAK_CALL", "sell_the_rip", "Kodiak"),
    ("SELL_RIP_EMA", "sell_the_rip", "Achilles"),
    ("SELL_RIP_VWAP", "sell_the_rip", "Achilles"),
    ("SELL_RIP_EARLY", "sell_the_rip", "Achilles"),
    (None, "sell_the_rip", "Achilles"),
    ("WHALE_LONG", "Whale_Hunter", "Triton"),
    ("NEMESIS_LONG", "nemesis", "Nemesis"),
]

# Presentation surfaces -> marker(s) that prove alias wiring is present.
SURFACES = {
    "frontend/app.js": ["signalDisplayName", "relatedDisplayName", "signal.codename"],
    "backend/api/trade_ideas.py": ["attach_codename", "codename("],
    "backend/signals/feed_service.py": ["attach_codename", "codename("],
    "backend/hub_mcp/tools/trade_ideas.py": ["codename("],
    "backend/discord_bridge/bot.py": ["_alias_codename"],
    "scripts/signal_notifier.py": ["_codename_for"],
    "scripts/pivot2_committee.py": ["_codename_for"],
}


def check_map() -> list[str]:
    failures = []
    for st, strat, expected in EXPECTED:
        got = codename(st, strat)
        if got != expected:
            failures.append(f"  codename({st!r}, {strat!r}) = {got!r}, expected {expected!r}")
    return failures


def check_surfaces() -> list[str]:
    failures = []
    for rel, markers in SURFACES.items():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            failures.append(f"  MISSING surface file: {rel}")
            continue
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        missing = [m for m in markers if m not in text]
        if missing:
            failures.append(f"  {rel}: missing alias wiring marker(s): {missing}")
    return failures


def main() -> int:
    print("=" * 60)
    print("L0.4 ALIAS COVERAGE CHECK")
    print("=" * 60)

    map_fail = check_map()
    print(f"\n[1] Map resolves roster: {'FAIL' if map_fail else 'PASS'} "
          f"({len(EXPECTED)} entries)")
    for f in map_fail:
        print(f)

    surf_fail = check_surfaces()
    print(f"\n[2] Presentation surfaces wired: {'FAIL' if surf_fail else 'PASS'} "
          f"({len(SURFACES)} surfaces)")
    for f in surf_fail:
        print(f)
    if not surf_fail:
        for rel in SURFACES:
            print(f"  ok  {rel}")

    ok = not (map_fail or surf_fail)
    print("\n" + ("ALL CHECKS PASS" if ok else "COVERAGE CHECK FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
