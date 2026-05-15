#!/usr/bin/env python3
"""AEGIS-mandated import lint for the MCP module.

Scans every `.py` under `backend/mcp/` and fails if any import references a
write-capable module. This is layer 2 of the three-layer read-only
enforcement (the @mcp_tool decorator is layer 1; AEGIS PR review is layer 3).

Rules:
  - backend/mcp/* may import from backend.services.read_only.*
  - backend/mcp/* may NOT import from backend.services.write.* (does not
    exist yet, defensive guard for v2)
  - backend/mcp/* may NOT import any name from a curated set of write-capable
    modules (e.g., `bias_engine.composite.cache_composite`)
  - backend/mcp/* may NOT import an entire write-heavy module by bare name
    (e.g., `import api.portfolio` would be flagged because api/portfolio.py
    contains POST endpoints)

Exit codes:
  0 — clean
  1 — at least one forbidden import found
  2 — internal lint error (scanned file failed to parse)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_ROOT = REPO_ROOT / "backend" / "mcp"

# Bare module imports that are categorically forbidden because they bundle
# write capability. The full import path or any descendant of these triggers
# a failure. (Names are as they would be imported from inside backend/, since
# the Procfile cd's into backend/ before launch.)
FORBIDDEN_MODULES = {
    "backend.services.write",
    # write-heavy API routers; reads are reached via services/read_only
    "api.unified_positions",
    "api.portfolio",
    "api.hydra",  # POST /refresh
    "api.alerts",  # has POST endpoints
    "api.committee_bridge",
    "api.signals",
    "api.flow_ingestion",
    "api.accept_flow",
    "api.confluence",
    "api.knowledgebase",
    "bias_filters.sector_rotation",  # auto_fetch_and_update writes
    # data-write database modules
    "database.write",
}

# Specific names that cannot be imported even from otherwise-mixed modules.
# Format: (source_module, forbidden_name).
FORBIDDEN_NAMES = {
    ("bias_engine.composite", "cache_composite"),
    ("bias_engine.composite", "log_composite"),
    ("bias_engine.composite", "compute_composite"),
    ("bias_engine.composite", "record_factor_reading"),
}


def _iter_py_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if p.is_file() and "__pycache__" not in p.parts:
            yield p


def _is_forbidden_module(module: str) -> bool:
    """True if `module` is or descends from a forbidden module."""
    for forbidden in FORBIDDEN_MODULES:
        if module == forbidden or module.startswith(forbidden + "."):
            return True
    return False


def _check_file(path: Path) -> List[str]:
    """Return a list of violation strings found in `path`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise RuntimeError(f"{path}: {exc}") from exc

    violations: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    violations.append(
                        f"{path}:{node.lineno} forbidden module import: {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_forbidden_module(module):
                violations.append(
                    f"{path}:{node.lineno} forbidden module: from {module} import ..."
                )
                continue
            for alias in node.names:
                if (module, alias.name) in FORBIDDEN_NAMES:
                    violations.append(
                        f"{path}:{node.lineno} forbidden name: "
                        f"from {module} import {alias.name}"
                    )
    return violations


def main() -> int:
    if not MCP_ROOT.exists():
        print(f"MCP directory not found at {MCP_ROOT}", file=sys.stderr)
        return 1

    all_violations: List[str] = []
    for path in _iter_py_files(MCP_ROOT):
        try:
            all_violations.extend(_check_file(path))
        except RuntimeError as exc:
            print(f"Lint error: {exc}", file=sys.stderr)
            return 2

    if all_violations:
        print("MCP import lint FAILED:", file=sys.stderr)
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        print(
            f"\n{len(all_violations)} violation(s). The MCP module must "
            "import data only from backend.services.read_only.",
            file=sys.stderr,
        )
        return 1

    print("MCP import lint passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
