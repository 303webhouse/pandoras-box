"""Every factor reads the same clock — R-IV.597(d).

`bias_engine.composite._utc_naive` passes an already-naive datetime through unchanged, assuming
it is UTC. It cannot check: a local 14:00 and a UTC 14:00 are the same object. So a writer using
`datetime.now()` would have its reading stored six or seven hours out, and nothing would raise.

The guard cannot live in `_utc_naive` — only the writer knows which clock it read. It lives here.
"""

import ast
import io
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILTERS = os.path.join(BACKEND, "bias_filters")

_LOCAL_CLOCKS = ("datetime.now()", "datetime.today()", "date.today()")


def _filter_modules():
    return sorted(f for f in os.listdir(FILTERS) if f.endswith(".py"))


@pytest.mark.parametrize("name", _filter_modules())
def test_no_factor_timestamps_itself_from_a_local_clock(name):
    """A reading stamped `datetime.now()` is stored as if it were UTC — six hours out in
    Mountain Time, and seven in winter."""
    src = io.open(os.path.join(FILTERS, name), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.keyword) or node.arg != "timestamp":
            continue
        rendered = ast.unparse(node.value)
        assert not any(c.rstrip("()") in rendered.replace(" ", "")
                       for c in ("datetime.now", "datetime.today", "date.today")), (
            "%s stamps a reading from a local clock: timestamp=%s" % (name, rendered))


def test_the_census_behind_that_rule():
    """POSITIVE CONTROL. If the scan found no timestamp writers at all it would pass
    vacuously, so this pins that there ARE writers and that every one uses `utcnow`."""
    total = 0
    for name in _filter_modules():
        src = io.open(os.path.join(FILTERS, name), encoding="utf-8-sig").read()
        total += len(re.findall(r"timestamp=datetime\.utcnow\(\)", src))
    assert total >= 21, total


def test_utc_naive_still_passes_a_naive_value_through():
    """Pinning the behaviour the rule above compensates for, so that if someone ever makes
    `_utc_naive` assume a local clock instead, this fails rather than the data going quiet."""
    from datetime import datetime, timezone

    from bias_engine.composite import _utc_naive

    naive = datetime(2026, 9, 26, 14, 0)
    assert _utc_naive(naive) == naive
    aware = datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc)
    assert _utc_naive(aware) == naive
