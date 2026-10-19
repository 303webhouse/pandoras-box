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

R-IV.1239(g): THE RESOLVER MOVED OUT, and it had a hole. This file's own copy answered PASS
for a module that will not import at all -- so `from database.connection import get_db`, a
module defined nowhere, cleared it. That line then shipped in an API handler. The resolver now
lives in `_importprobe`, scopes its tolerance by OWNERSHIP rather than by exception type, and
is shared with `test_route_registry.py`: a second copy is how the hole survives in the one
nobody edited.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

from ._importprobe import imports_in, parse_file, resolves

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

JOB_FILES = sorted((_BACKEND / "jobs").glob("*.py"))


def _imported_names(path: pathlib.Path):
    """(module, name, lineno) for every import in the file, from the parsed tree."""
    return imports_in(parse_file(path))


@pytest.mark.parametrize("path", JOB_FILES, ids=lambda p: p.name)
def test_every_imported_name_in_this_job_exists(path):
    missing = []
    for module, name, lineno in _imported_names(path):
        ok, why = resolves(module, name)
        if not ok:
            missing.append("%s:%d  from %s import %s  -> %s" % (path.name, lineno, module, name, why))
    assert not missing, "names that do not exist:\n  " + "\n  ".join(missing)


def test_the_instrument_can_actually_fail():
    """A positive control (Convention #30). Without this, a checker that silently resolved
    everything -- or parsed nothing -- would read as 36 passing files."""
    ok, why = resolves("integrations.uw_api", "get_stock_info")
    assert ok is False and why == "MISSING", (ok, why)


def test_the_instrument_no_longer_clears_a_module_that_does_not_exist():
    """THE HOLE THIS FILE HAD. `database.connection` is defined nowhere, and the old local
    resolver returned PASS for it because it could not be imported at all. A probe that
    clears the absent is worse than no probe: it reports the surface as checked."""
    ok, why = resolves("database.connection", "get_db")
    assert ok is False and why.startswith("MODULE-MISSING:"), (ok, why)


def test_it_is_reading_a_real_and_non_empty_set_of_files():
    """The other half of the control: the sweep must actually have swept something."""
    assert len(JOB_FILES) >= 20, len(JOB_FILES)
    total = sum(len(_imported_names(p)) for p in JOB_FILES)
    assert total >= 200, total
