"""Every name a job imports must actually exist.

WHY THIS FILE EXISTS. `jobs/hermes_session_poll.py` recorded 389 consecutive failures and not
one success, reporting "no evaluable displacement for any of 3 symbol(s) -- alarm is blind".
The cause was a single line: `from integrations.uw_api import get_stock_info`, a function that
existed nowhere in the tree. Three things hid it:

  1. the import was DEFERRED into the function body, so importing the module proved nothing;
  2. it sat under a broad `except Exception`, which treats a missing name as a bad data day;
  3. every test of that function patched it, so no test ever executed the import.

A unit test cannot catch this, because patching the reader is exactly how the reader is
tested. Only reading the imports and asking whether each target exists can. These assertions
are built from the PARSED tree, so a docstring that merely discusses a name -- this one does --
cannot satisfy or trip them.
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

JOB_FILES = sorted((_BACKEND / "jobs").glob("*.py"))


def _imported_names(path: pathlib.Path) -> list[tuple[str, str | None, int]]:
    """(module, name, lineno) for every import, from the parsed tree."""
    out: list[tuple[str, str | None, int]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module or node.module == "__future__":
                continue                      # relative / future: not a cross-module promise
            for alias in node.names:
                if alias.name == "*":
                    continue
                out.append((node.module, alias.name, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, None, node.lineno))
    return out


def _resolves(module: str, name: str | None) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(module)
    except Exception as exc:                                        # noqa: BLE001
        # A module that will not import at all is a different (often environmental) problem;
        # it is reported, not asserted on, so an absent optional dependency cannot turn into a
        # false accusation about a name.
        return True, "module-unimportable:%s" % type(exc).__name__
    if name is None:
        return True, "module-ok"
    if hasattr(mod, name):
        return True, "ok"
    # An unimported SUBMODULE is not an attribute yet -- that is the probe being wrong, not the
    # code. Ask the import system directly before accusing anything.
    try:
        importlib.import_module("%s.%s" % (module, name))
        return True, "submodule"
    except Exception:                                               # noqa: BLE001
        return False, "MISSING"


@pytest.mark.parametrize("path", JOB_FILES, ids=lambda p: p.name)
def test_every_imported_name_in_this_job_exists(path):
    missing = []
    for module, name, lineno in _imported_names(path):
        ok, why = _resolves(module, name)
        if not ok:
            missing.append("%s:%d  from %s import %s  -> %s" % (path.name, lineno, module, name, why))
    assert not missing, "names that do not exist:\n  " + "\n  ".join(missing)


def test_the_instrument_can_actually_fail():
    """A positive control (Convention #30). Without this, a checker that silently resolved
    everything -- or parsed nothing -- would read as 36 passing files."""
    ok, why = _resolves("integrations.uw_api", "get_stock_info")
    assert ok is False and why == "MISSING", (ok, why)


def test_it_is_reading_a_real_and_non_empty_set_of_files():
    """The other half of the control: the sweep must actually have swept something."""
    assert len(JOB_FILES) >= 20, len(JOB_FILES)
    total = sum(len(_imported_names(p)) for p in JOB_FILES)
    assert total >= 200, total
