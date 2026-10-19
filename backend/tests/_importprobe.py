"""Does the name this code imports actually exist? ONE AUTHOR, for the same reason `_srcscan`
has one: I wrote this resolver once for the jobs sweep and it had a hole, and a per-file
re-derivation is how the hole survives in the copy nobody looked at.

THE HOLE, which is why this file exists. The first version answered "a module that will not
import at all is a different (often environmental) problem" and returned PASS for it. That is
right for a third-party package the test environment lacks, and WRONG for one of our own:

    from database.connection import get_db        # database.connection exists NOWHERE

`importlib.import_module("database.connection")` raises `ModuleNotFoundError`, which the
tolerant branch read as "unimportable, not my business" -- so the probe PASSED a line that
could only ever raise at request time. That exact line shipped in an API handler, deferred
into the function body, and served a bare 500 with no log line. The instrument built to catch
it would have cleared it.

So the tolerance is now scoped by OWNERSHIP rather than by exception type:

  * a module whose top-level package is one of OURS (a package or module sitting in
    `backend/`) must import, and a `ModuleNotFoundError` naming one of ours is a FAILURE;
  * a third-party import that is simply not installed here is reported, not asserted on,
    because an absent optional dependency is not a defect in our code.

`ModuleNotFoundError.name` is what distinguishes them: when one of our modules fails because
it imports a missing third-party package, the exception names THAT package, not ours. Checking
the exception's own `name` rather than the string we asked for is the difference between
"our module is missing" and "our module needs something this environment lacks".
"""
from __future__ import annotations

import ast
import importlib
import os
import pathlib
from typing import Iterable, List, Optional, Tuple

_BACKEND = pathlib.Path(__file__).resolve().parents[1]


def first_party_roots() -> frozenset:
    """Top-level import names that belong to this repo, read off the tree, not listed by hand.

    DERIVED, because a hand-kept list is a second place to forget: a new package under
    `backend/` would be silently treated as third party and get the tolerant branch -- the
    hole this file exists to close, re-opened for whichever directory was added last.
    """
    out = set()
    for entry in os.listdir(_BACKEND):
        path = _BACKEND / entry
        if entry.startswith((".", "_")):
            continue
        if path.is_dir() and entry != "__pycache__":
            out.add(entry)
        elif path.is_file() and entry.endswith(".py"):
            out.add(entry[:-3])
    return frozenset(out)


FIRST_PARTY = first_party_roots()


def is_first_party(module: str) -> bool:
    return (module or "").split(".")[0] in FIRST_PARTY


def resolves(module: str, name: Optional[str]) -> Tuple[bool, str]:
    """(ok, why) for `from <module> import <name>`, or `import <module>` when name is None."""
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", None) or ""
        if is_first_party(missing):
            # OURS, and absent. This is the fault the whole file is about.
            return False, "MODULE-MISSING:%s" % missing
        return True, "needs-uninstalled:%s" % (missing or "?")
    except Exception as exc:                                        # noqa: BLE001
        # Imports but raises at import time -- a different problem, and often environmental
        # (no DB, no key). Reported, never asserted on, so a missing credential cannot turn
        # into a false accusation about a name.
        return True, "module-raised:%s" % type(exc).__name__
    if name is None:
        return True, "module-ok"
    if hasattr(mod, name):
        return True, "ok"
    # An unimported SUBMODULE is not an attribute yet -- that is the probe being wrong, not
    # the code. Ask the import system before accusing anything.
    try:
        importlib.import_module("%s.%s" % (module, name))
        return True, "submodule"
    except Exception:                                               # noqa: BLE001
        return False, "MISSING"


def imports_in(node: ast.AST) -> List[Tuple[str, Optional[str], int]]:
    """(module, name, lineno) for every import under `node`, from the PARSED tree.

    From the tree, so a docstring or comment that merely discusses an import -- the ones above
    do -- can neither satisfy nor trip the assertions built on this. Relative and `__future__`
    imports are skipped: neither is a cross-module promise this probe can check.
    """
    out: List[Tuple[str, Optional[str], int]] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.ImportFrom):
            if sub.level or not sub.module or sub.module == "__future__":
                continue
            for alias in sub.names:
                if alias.name != "*":
                    out.append((sub.module, alias.name, sub.lineno))
        elif isinstance(sub, ast.Import):
            for alias in sub.names:
                out.append((alias.name, None, sub.lineno))
    return out


def parse_file(path) -> ast.Module:
    """utf-8-sig: some sources here carry a BOM and `ast.parse` dies on it (see `_srcscan`)."""
    return ast.parse(pathlib.Path(path).read_text(encoding="utf-8-sig"))


def functions_named(tree: ast.AST, name: str) -> List[ast.AST]:
    """Every def with this name, at any nesting. Several matches are unioned by the caller:
    a wrong guess about WHICH def is the handler must not narrow what gets checked."""
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]


def unresolved(pairs: Iterable[Tuple[str, Optional[str], int]]) -> List[Tuple[str, Optional[str], int, str]]:
    """The subset that does not resolve, each with its reason."""
    out = []
    for module, name, lineno in pairs:
        ok, why = resolves(module, name)
        if not ok:
            out.append((module, name, lineno, why))
    return out
