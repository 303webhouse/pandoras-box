"""R-IV.1251: the yield-curve box is never blank, and its five tenors come from one source.

THE BUG THIS FILE EXISTS FOR was a race nobody owned. `loadRegimeBand` rebuilds the band's
innerHTML, destroying the box's filled markup; `refreshMarket` fills it on a SECOND,
independent 60-second timer. Band-last order leaves the empty template on screen — a title, an
em dash and nothing — which is what Nick's screenshot caught DURING RTH.

Guarded structurally, because no unit test can observe two browser timers racing: the painter
must be separate from the fetch, must read a cache, and must be called from the band rebuild.
"""
from __future__ import annotations

import pathlib
import re

from models import yield_curve_b3 as yc

V2 = pathlib.Path(__file__).resolve().parents[2].joinpath("frontend", "v2.js")


def _js() -> str:
    return V2.read_text(encoding="utf-8")


def test_THE_PAINTER_IS_SEPARATE_FROM_THE_FETCH_AND_READS_A_CACHE():
    """A fetch-and-paint in one function can only repaint by going to the network, which on a
    band tick would turn one blank box into a request storm."""
    js = _js()
    assert "function paintYieldCurve()" in js
    assert "let _ycData = null" in js
    paint = js[js.index("function paintYieldCurve()"):]
    paint = paint[:paint.index("\n  // ── b6 USD carry")] if "\n  // ── b6 USD carry" in paint else paint[:8000]
    assert "apiFetch(" not in paint, "the painter must not fetch"
    assert "const d = _ycData;" in paint


def test_THE_BAND_REBUILD_REPAINTS_THE_BOX_IN_THE_SAME_TICK():
    """THE FIX. Without this call the box stays blank for up to a minute after every band
    rebuild, and permanently whenever the two timers settle into band-last order."""
    js = _js()
    i = js.index("band.innerHTML = `")
    j = js.index("band.querySelectorAll('[data-drawer]')", i)
    rebuild = js[i:j]
    assert "paintYieldCurve();" in rebuild, (
        "the band rebuild must repaint the box it just destroyed")


def test_THE_BOX_NEVER_RENDERS_BLANK():
    """R-IV.1251(b). Every exit from the painter writes something into `ycHeads`: a curve, or a
    sentence naming what is missing. There is no `return` that leaves it as it was."""
    js = _js()
    paint = js[js.index("function paintYieldCurve()"):]
    paint = paint[:paint.index("const spreadRows")]
    # The only bare return is the one for "this element does not exist on this page".
    bare = [ln.strip() for ln in paint.splitlines() if ln.strip() == "return;"]
    assert len(bare) == 1, bare
    assert "if (!heads) return;" in paint
    assert "yield curve unavailable" in paint


def test_THE_UNAVAILABLE_PATHS_NAME_THE_SERIES():
    """A reader can act on "5Y (DGS5) returned no usable observation" and cannot act on a gap."""
    js = _js()
    paint = js[js.index("function paintYieldCurve()"):]
    paint = paint[:paint.index("heads.innerHTML = '<div class=\"yc-tenors\"")]
    assert "no reading yet from /api/yield-curve" in paint
    assert "t.unavailable_reason" in paint, "a dead tenor shows ITS OWN reason"


def test_ALL_FIVE_TENORS_COME_FROM_ONE_SOURCE():
    """R-IV.1251(c). The box drew its table from /api/stable/rates (3M/5Y/10Y/30Y) while the
    labels came from the FRED route (3M/2Y/10Y/30Y): 2Y had a z-score and no row, 5Y had a row
    and no z-score, and the two lists disagreed about which tenors the curve has."""
    assert list(yc.SERIES) == ["3M", "2Y", "5Y", "10Y", "30Y"]
    assert yc.SERIES["2Y"] == "DGS2" and yc.SERIES["5Y"] == "DGS5"
    js = _js()
    paint = js[js.index("function paintYieldCurve()"):]
    paint = paint[:paint.index("const spreadRows")]
    # The rows and the chart are built from the SAME array, so they cannot disagree.
    assert "const tenors = (d.tenors || []);" in paint
    assert "const drawn = tenors.filter((t) => t.level_pct != null);" in paint
    # COMMENTS STRIPPED. The first version of this assertion tripped on the comment that
    # EXPLAINS the old two-source mixing — the strip-the-prose fault, which this repo has now
    # hit fifteen times and which I hit again an hour after writing the ast-based guard for it.
    # A scan over prose cannot tell an explanation from an offence.
    code = "\n".join(ln for ln in paint.splitlines()
                     if not ln.strip().startswith("//"))
    assert "/api/stable/rates" not in code, "the box no longer mixes two tenor lists"


def test_THE_LABEL_TINTS_THE_TENOR_AND_THE_DASHED_LINE_IS_A_MONTH():
    js = _js()
    paint = js[js.index("function paintYieldCurve()"):]
    paint = paint[:paint.index("const spreadRows")]
    assert "yc-t-extreme" in paint and "yc-t-unusual" in paint
    assert "borderDash: [4, 3]" in paint
    assert "1 month ago" in paint
    assert yc.MONTH_AGO_SESSIONS == 21


def test_THE_DASHED_LINE_IS_OMITTED_RATHER_THAN_DRAWN_ON_TOP():
    """A dashed line equal to the solid one would say "unchanged in a month", which is a claim
    about the curve rather than an absence of history."""
    js = _js()
    paint = js[js.index("function paintYieldCurve()"):]
    paint = paint[:paint.index("const spreadRows")]
    assert "if (ago.some((v) => v != null))" in paint
