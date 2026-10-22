"""A changed asset behind an unchanged cache pin. R-IV.1257's finding.

THIS IS THE FAULT THE TEST EXISTS FOR, and it shipped twice before anything noticed. The pins
were being bumped with a LINE-NUMBERED `sed` (`sed -i '366s|...|'`). An edit to `v2.html` added
comment lines, the script tag moved from line 366 to 376, and every later bump silently matched
nothing — `sed` reports success when its address matches no line. So:

    eff2a2ed  v2.js changed, pin 80  -> served
    a963f6e6  v2.js changed, pin 81  -> served
    caa87b00  v2.js changed, pin 81  -> NOT served to a cached browser
    c2f243f4  v2.js changed, pin 81  -> NOT served  (this was the yield-box fix)

CLAUDE.md states the rule outright: "A changed asset behind an unchanged pin is a fix that never
reaches the browser." I verified that fix by reading the ROUTE's payload, which was correct, and
the headless gate loads with an empty cache so it saw the new file too. Neither check could see
the delivery failure. That is the lesson: verifying the data is not verifying that the data
reaches the screen.

HOW THIS GUARD WORKS. `frontend/asset-pins.json` records, for every pinned asset, the pin it was
last shipped under and the sha256 of the file at that moment. A changed file whose pin did not
move fails here, in the suite, before the deploy. Updating the manifest is the deliberate act
that says "yes, this pin is now correct for this content" -- exactly the moment to notice the
pin did not move.

To refresh after an intended bump:
    python scripts/update_asset_pins.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parents[2].joinpath("frontend")
MANIFEST = FRONTEND.joinpath("asset-pins.json")
PIN_RE = re.compile(r'["\'](?:/)?([A-Za-z0-9_./-]+\.(?:js|css))\?v=(\d+)')


def _live_pins():
    """{page: {asset: (pin, sha256)}} as the HTML actually stands right now."""
    out = {}
    for page in sorted(FRONTEND.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        for asset, pin in PIN_RE.findall(html):
            target = FRONTEND.joinpath(asset.lstrip("/"))
            if not target.exists():
                continue
            # LF-NORMALISED, and the manifest records the same (R-IV.1321(c)). Raw bytes made
            # this a test of the CHECKOUT, not of the file: with `core.autocrlf` true the same
            # committed app.js hashes ee1c8d92 in an LF worktree and 08ed2565 in a CRLF one,
            # so BUILD read green and ABACUS read red on one unchanged file, each correctly.
            digest = hashlib.sha256(
                target.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            out.setdefault(page.name, {})[asset] = (int(pin), digest)
    return out


def test_THE_HASH_IS_OF_THE_FILE_NOT_OF_THE_CHECKOUT():
    """R-IV.1321(c). THE GUARD DISAGREED WITH ITSELF ACROSS TWO WORKTREES, and both lanes were
    right about what they measured.

    `core.autocrlf` is true on this machine, so one committed file is checked out LF in one
    worktree and CRLF in another. Measured on the SAME commit:

        C:/trading-hub   app.js  583,978 bytes  sha ee1c8d92...   -> test GREEN
        C:/th-abacus     app.js  597,844 bytes  sha 08ed2565...   -> test RED
        LF-normalised                           identical; delta 13,866 = one byte per line

    So the manifest was a record of a CHECKOUT rather than of a FILE. `efaa041c` did not
    "rewrite" app.js's hash -- the recorder ran in a CRLF worktree and stored the CRLF value;
    `7592b592` set it back to the LF value. Those two commits are the same disagreement, and
    without this the two lanes overwrite each other forever while the guard reads red or green
    by accident of where it ran.

    A guard whose answer depends on the machine is worse than no guard: it trains its readers
    to discount it.
    """
    import hashlib

    # Built with chr() rather than escapes: an escape sequence in a scripted patch has
    # collapsed into a real newline five times in this build, which is its own small lesson.
    CRLF = (chr(13) + chr(10)).encode()
    LF = chr(10).encode()
    crlf = b"a = 1;" + CRLF + b"b = 2;" + CRLF
    lf = crlf.replace(CRLF, LF)
    assert crlf != lf, "the two renderings differ as raw bytes"

    def norm(b):
        return hashlib.sha256(b.replace(CRLF, LF)).hexdigest()

    assert norm(crlf) == norm(lf), "and must not differ once normalised"

    # BOTH readers must normalise, or the manifest and the check disagree again.
    import pathlib as _pl

    needle = ".replace(b" + chr(34) + chr(92) + "r" + chr(92) + "n" + chr(34) + ", b" + chr(34) + chr(92) + "n" + chr(34) + ")"
    for path in (_pl.Path(__file__),
                 _pl.Path(__file__).resolve().parents[2] / "scripts" / "update_asset_pins.py"):
        assert needle in path.read_text(encoding="utf-8"), path.name

def test_the_manifest_exists():
    assert MANIFEST.exists(), (
        "frontend/asset-pins.json is missing; run scripts/update_asset_pins.py")


def test_EVERY_PINNED_ASSET_MATCHES_THE_PIN_IT_WAS_SHIPPED_UNDER():
    """THE GUARD. A file whose content changed while its `?v=` stayed put fails here.

    The message names the page and the asset, because the same file is pinned by several pages
    at INDEPENDENTLY DIVERGED values -- v2.css is pinned by v2.html, stater.html and
    abacus.html, and changing it means bumping all three. A reader who is told only "v2.css
    changed" still has to work out which pages missed it.
    """
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    live = _live_pins()
    problems = []
    for page, assets in sorted(live.items()):
        for asset, (pin, digest) in sorted(assets.items()):
            was = (recorded.get(page) or {}).get(asset)
            if was is None:
                problems.append("%s pins %s at v=%d, which the manifest does not record"
                                % (page, asset, pin))
                continue
            if digest != was["sha256"] and pin == was["pin"]:
                problems.append(
                    "%s: %s CHANGED but its pin is still v=%d -- a changed asset behind an "
                    "unchanged pin never reaches a cached browser" % (page, asset, pin))
    assert not problems, "\n  " + "\n  ".join(problems)


def test_A_SHARED_ASSET_IS_PINNED_BY_EVERY_PAGE_THAT_USES_IT():
    """v2.css is pinned by three pages at independently diverged values, and the pages that are
    missed keep serving whatever was cached under their unchanged pin. This asserts the set of
    pages pinning it, so a page that stops pinning it is noticed."""
    live = _live_pins()
    pinners = {page for page, assets in live.items() if "v2.css" in assets}
    assert pinners == {"v2.html", "stater.html", "abacus.html"}, pinners


def test_THE_PINS_ARE_READ_FROM_THE_HTML_AND_NOT_FROM_A_LINE_NUMBER():
    """The bump that failed used `sed -i '366s|...'`, and `sed` reports success when its
    address matches no line. The updater must find the pin by CONTENT.

    Checked on the updater's own source, because the next person to bump a pin will reach for
    whatever that script does.
    """
    script = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "scripts", "update_asset_pins.py")
    if not script.exists():
        pytest.skip("the updater is not in this tree")
    src = script.read_text(encoding="utf-8")
    assert "PIN_RE" in src or "re.sub" in src, "the updater must match on content"
