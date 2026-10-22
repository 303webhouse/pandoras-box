r"""Record the cache pins and the hashes they were shipped under.

Run AFTER bumping a `?v=` pin, so `backend/tests/test_asset_pins.py` can tell an intended bump
from a changed asset behind an unchanged pin. That is the fault this pair exists for: a
line-numbered `sed` silently stopped matching when the script tag moved, and two deploys shipped
JS the browser would never fetch.

    python scripts/update_asset_pins.py            # record the current state
    python scripts/update_asset_pins.py --bump v2.js
        # find every page pinning v2.js, raise each page's pin by one, then record

THE BUMP FINDS THE PIN BY CONTENT, never by line number. `sed -i '366s|...'` reports success
when its address matches no line, which is precisely how this went unnoticed.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "frontend")
MANIFEST = os.path.join(FRONTEND, "asset-pins.json")
PIN_RE = re.compile(r'["\'](?:/)?([A-Za-z0-9_./-]+\.(?:js|css))\?v=(\d+)')


def pages():
    return sorted(f for f in os.listdir(FRONTEND) if f.endswith(".html"))


def bump(asset: str) -> int:
    """Raise `asset`'s pin by one on EVERY page that pins it. Returns how many pages changed.

    Every page, because the same file is pinned by several at independently diverged values:
    v2.css is pinned by v2.html, stater.html and abacus.html, and the pages that are missed
    keep serving whatever was cached under their unchanged pin.
    """
    changed = 0
    for page in pages():
        path = os.path.join(FRONTEND, page)
        html = io.open(path, encoding="utf-8", newline="").read()

        def one(m):
            nonlocal changed
            if m.group(1).lstrip("/") != asset.lstrip("/"):
                return m.group(0)
            changed += 1
            return m.group(0).replace("?v=" + m.group(2), "?v=%d" % (int(m.group(2)) + 1))

        new = PIN_RE.sub(one, html)
        if new != html:
            io.open(path, "w", encoding="utf-8", newline="").write(new)
            print("  bumped in %s" % page)
    return changed


def record() -> dict:
    out: dict = {}
    for page in pages():
        html = io.open(os.path.join(FRONTEND, page), encoding="utf-8").read()
        for asset, pin in PIN_RE.findall(html):
            target = os.path.join(FRONTEND, asset.lstrip("/"))
            if not os.path.exists(target):
                continue
            # LF-NORMALISED, R-IV.1321(c). `core.autocrlf` is true on this machine, so the
            # SAME committed file is checked out LF in one worktree and CRLF in another --
            # app.js is 583,978 bytes here and 597,844 in C:	h-abacus, a delta of exactly one
            # byte per line, and identical after normalisation. Hashing raw bytes made this
            # manifest a record of a CHECKOUT rather than of a FILE: two lanes kept overwriting
            # each other's value and the guard was red or green by accident.
            digest = hashlib.sha256(
                io.open(target, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
            out.setdefault(page, {})[asset] = {"pin": int(pin), "sha256": digest}
    io.open(MANIFEST, "w", encoding="utf-8").write(
        json.dumps(out, indent=2, sort_keys=True) + "\n")
    return out


def main() -> int:
    if "--bump" in sys.argv:
        i = sys.argv.index("--bump")
        if i + 1 >= len(sys.argv):
            print("--bump needs an asset, e.g. --bump v2.js")
            return 2
        asset = sys.argv[i + 1]
        n = bump(asset)
        if not n:
            # LOUD, because a silent no-op is the whole fault being fixed here.
            print("NOTHING BUMPED: no page pins %r" % asset)
            return 1
        print("bumped %s on %d page(s)" % (asset, n))
    data = record()
    for page, assets in sorted(data.items()):
        for a, d in sorted(assets.items()):
            print("%-20s %-24s v=%-4d %s" % (page, a, d["pin"], d["sha256"][:12]))
    print("recorded %s" % MANIFEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
