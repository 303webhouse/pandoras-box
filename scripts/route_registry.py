"""Print the route registry. R-IV.1239(g).

The same registry `backend/tests/test_route_registry.py` asserts against, in a form a person
can read: every route the app serves, where its handler is defined, the auth posture FastAPI's
own dependant tree reports, and every import written inside the handler body with whether it
resolves.

BUILT FROM `main.app`, never from a list. A hand-kept inventory of routes is a second place to
forget a route, and the forgotten one is always the newest -- the only kind the check is for.

Usage, from the repo root:

    .venv-test/Scripts/python -B scripts/route_registry.py             # one line per route
    .venv-test/Scripts/python -B scripts/route_registry.py --imports   # + handler imports
    .venv-test/Scripts/python -B scripts/route_registry.py --broken    # only what fails

`--broken` exits 1 when anything fails to resolve, so it can gate a deploy. Nothing here
writes, calls a vendor or touches the database: importing the app is enough to build it.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
#: ONLY `backend/` goes on the path. Putting `backend/tests/` on it as well shadows real
#: packages with the fixture directories that share their names -- `backend/tests/signals/`
#: took over `signals`, and the app died importing `signals.pipeline`, a module that exists.
#: An import error that names a real module is a path problem, not a missing module.
sys.path.insert(0, _BACKEND)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--imports", action="store_true", help="list each handler's own imports")
    ap.add_argument("--broken", action="store_true", help="only unresolved imports; exit 1 if any")
    args = ap.parse_args()

    # Imported here rather than at module scope so --help works without importing the app.
    from tests._importprobe import resolves
    from tests.test_route_registry import handler_imports, registry

    rows = registry()
    imports = handler_imports()

    broken = []
    for row in imports:
        module, name = row["imported"]
        ok, why = resolves(module, name)
        if not ok:
            broken.append((row, why))

    if args.broken:
        for row, why in sorted(broken, key=lambda r: (r[0]["path"], r[0]["lineno"])):
            module, name = row["imported"]
            print("BROKEN  %-7s %-50s %s:%d  from %s import %s  -> %s"
                  % (",".join(row["methods"]) or "-", row["path"],
                     os.path.basename(row["source"]), row["lineno"], module, name, why))
        print("\n%d broken handler import(s) across %d route(s)"
              % (len(broken), len({r["path"] for r, _ in broken})))
        return 1 if broken else 0

    by_path = {}
    for row in imports:
        by_path.setdefault((tuple(row["methods"]), row["path"]), []).append(row)

    for row in sorted(rows, key=lambda r: (r["path"], r["methods"])):
        auth = {True: "gated", False: "open", None: "unreadable"}[row["auth"]]
        print("%-7s %-52s %-28s %-10s %s"
              % (",".join(row["methods"]) or "-", row["path"], row["module"], auth,
                 os.path.basename(row["source"]) if row["source"] else "(no source)"))
        if args.imports:
            for sub in by_path.get((tuple(row["methods"]), row["path"]), []):
                module, name = sub["imported"]
                ok, why = resolves(module, name)
                print("            %-9s line %-5d from %s import %s"
                      % (why if not ok else "ok", sub["lineno"], module, name))

    gated = sum(1 for r in rows if r["auth"] is True)
    print("\n%d route(s), %d endpoint file(s), %d handler import(s), %d broken"
          % (len(rows), len({r["source"] for r in rows if r["source"]}), len(imports),
             len(broken)))
    print("auth posture: %d gated, %d open, %d unreadable (test_auth.py rules on which must "
          "be gated; this only reports what the dependant tree says)"
          % (gated, sum(1 for r in rows if r["auth"] is False),
             sum(1 for r in rows if r["auth"] is None)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
