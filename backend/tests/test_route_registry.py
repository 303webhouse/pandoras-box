"""THE ROUTE REGISTRY. R-IV.1239(g).

WHAT IT CLOSES. An API handler shipped with `from database.connection import get_db` deferred
into its body. The module imported fine, every unit test patched the reader, and the route
answered a bare 500 with no log line -- because a deferred import fails at REQUEST time, which
is the one moment no test was looking. `test_deferred_imports_resolve.py` sweeps `jobs/*.py`
for exactly this fault and would not have caught this one: routes were outside its sweep, and
its resolver cleared a module that does not exist at all (see `_importprobe`).

So this file builds the registry from the REAL app -- `main.app`, every route FastAPI actually
serves -- and asserts two things against it:

  1. every import inside a route's own handler body resolves;
  2. every import in every file that defines a route resolves, which covers the helpers a
     handler calls and the module-level imports that would 500 the whole router.

THE REGISTRY IS BUILT, NEVER LISTED. A hand-kept list of routes is a second place to forget a
route, and the route that gets forgotten is the new one -- the only kind this check is for.
`scripts/route_registry.py` prints the same registry for reading.

WHAT THIS FILE DOES NOT DO: auth. Which routes must be gated is `test_auth.py`'s question and
it answers it off the resolved dependant tree, which is the only thing that can see
`dependencies=[Depends(require_api_key)]`. The registry records the auth posture it reads so
the two can be compared, and asserts nothing about it.
"""
from __future__ import annotations

import inspect
import os
import pathlib
from functools import lru_cache
from typing import Any, Dict, List

import pytest

from ._importprobe import (functions_named, imports_in, parse_file, resolves,
                           unresolved)

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

#: The names FastAPI's dependant tree carries for this hub's auth dependencies. Shared with
#: `test_auth.py` by value, not by import: this file records the posture, that one rules on it.
_AUTH_DEP_NAMES = {"require_api_key", "require_session_or_key", "verify_api_key"}


def _has_auth(dependant) -> bool:
    for dep in getattr(dependant, "dependencies", ()) or ():
        if getattr(dep.call, "__name__", "") in _AUTH_DEP_NAMES or _has_auth(dep):
            return True
    return False


@lru_cache(maxsize=1)
def registry() -> List[Dict[str, Any]]:
    """One row per route the app serves, with where its handler is defined.

    A route whose endpoint cannot be located on disk (a mounted sub-app, a Starlette default)
    is KEPT with `source: None` rather than dropped, so the census below counts what the app
    has and not what the probe happened to understand.
    """
    from main import app

    rows: List[Dict[str, Any]] = []
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        func = inspect.unwrap(endpoint)
        try:
            source = inspect.getsourcefile(func)
        except Exception:                                           # noqa: BLE001
            source = None
        if source and not os.path.exists(source):
            source = None
        rows.append({
            "methods": sorted(getattr(route, "methods", None) or []),
            "path": getattr(route, "path", ""),
            "module": getattr(func, "__module__", "?"),
            "func": getattr(func, "__name__", "?"),
            "source": os.path.abspath(source) if source else None,
            "auth": (_has_auth(route.dependant) if hasattr(route, "dependant") else None),
        })
    return rows


@lru_cache(maxsize=1)
def handler_imports() -> List[Dict[str, Any]]:
    """Every import written INSIDE a route handler's own body, attributed to its route."""
    out: List[Dict[str, Any]] = []
    for row in registry():
        if not row["source"]:
            continue
        tree = parse_file(row["source"])
        for node in functions_named(tree, row["func"]):
            for module, name, lineno in imports_in(node):
                out.append(dict(row, imported=(module, name), lineno=lineno))
    return out


@lru_cache(maxsize=1)
def endpoint_files() -> List[str]:
    return sorted({r["source"] for r in registry() if r["source"]})


def _label(row) -> str:
    module, name = row["imported"]
    return "%s %s  (%s:%d)  from %s import %s" % (
        ",".join(row["methods"]) or "-", row["path"],
        os.path.basename(row["source"]), row["lineno"], module, name)


def test_every_deferred_import_inside_a_route_handler_resolves():
    """The fault this file is named for, asserted per ROUTE so the message names the surface
    that would 500 rather than only the file."""
    broken = []
    for row in handler_imports():
        module, name = row["imported"]
        ok, why = resolves(module, name)
        if not ok:
            broken.append("%s  ->  %s" % (_label(row), why))
    assert not broken, ("imports inside route handlers that cannot resolve:\n  "
                        + "\n  ".join(sorted(broken)))


def test_every_import_in_every_file_that_defines_a_route_resolves():
    """One level wider: the helpers a handler calls, and the module-level imports whose
    failure takes the whole router down rather than one route."""
    broken = []
    for path in endpoint_files():
        pairs = imports_in(parse_file(path))
        for module, name, lineno, why in unresolved(pairs):
            broken.append("%s:%d  from %s import %s  ->  %s"
                          % (os.path.basename(path), lineno, module, name, why))
    assert not broken, ("imports in route-defining files that cannot resolve:\n  "
                        + "\n  ".join(sorted(broken)))


def test_the_probe_fails_on_the_import_that_caused_this_file():
    """Positive control (Convention #30), and it is the REAL line: `database.connection` is
    the module the handler imported and nothing defines. The previous resolver returned PASS
    here, which is why the check is scoped by ownership now."""
    ok, why = resolves("database.connection", "get_db")
    assert ok is False and why.startswith("MODULE-MISSING:"), (ok, why)


def test_the_probe_fails_on_a_missing_name_in_a_module_that_exists():
    """The other half: the module is ours and imports fine, the NAME is not there."""
    ok, why = resolves("database.postgres_client", "get_postgres_client_that_never_existed")
    assert ok is False and why == "MISSING", (ok, why)


def test_the_probe_tolerates_a_third_party_package_this_environment_lacks():
    """And the tolerance it must keep: an uninstalled optional dependency is not a defect in
    our code, so it reports rather than fails."""
    ok, why = resolves("a_package_nobody_has_ever_installed", "anything")
    assert ok is True and why.startswith("needs-uninstalled:"), (ok, why)


def test_the_registry_swept_a_real_app():
    """The census (Convention #30's other half): a registry that silently built nothing would
    read as every assertion above passing. Floors, not exact counts -- routes get added."""
    rows = registry()
    assert len(rows) >= 400, len(rows)
    assert len({r["module"] for r in rows}) >= 50, sorted({r["module"] for r in rows})
    assert len(endpoint_files()) >= 50, endpoint_files()
    assert len(handler_imports()) >= 200, len(handler_imports())
    # And it found the surfaces this lane built, which is the cheapest proof it read the real
    # app rather than a partially-imported one.
    paths = {r["path"] for r in rows}
    for expected in ("/health", "/api/stable/regime-strategy", "/api/v2/positions"):
        assert expected in paths, (expected, sorted(p for p in paths if "stable" in p)[:10])


def test_every_route_row_records_its_auth_posture_or_says_it_cannot():
    """`auth` is three-valued on purpose: True, False, or None for a route with no dependant
    to read. A probe that reported an unreadable posture as False would call a mounted
    sub-app's routes ungated and invite a fix to something it never measured."""
    for row in registry():
        assert row["auth"] in (True, False, None), row


@pytest.mark.parametrize("name", ["_importprobe.py", "test_deferred_imports_resolve.py"])
def test_the_shared_probe_is_the_one_both_sweeps_use(name):
    """The hole closed here was a SECOND COPY of the resolver with a tolerant branch. Both
    sweeps must read from `_importprobe`, or the next hole lives in whichever copy was not
    the one edited."""
    src = (_BACKEND / "tests" / name).read_text(encoding="utf-8-sig")
    if name == "_importprobe.py":
        assert "def resolves(" in src
    else:
        assert "_importprobe import" in src, (
            "%s must use the shared resolver, not its own" % name)
