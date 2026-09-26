"""Tests for backend/mcp/envelope.py."""

from hub_mcp.envelope import SUMMARY_MAX_CHARS, make_response
from hub_mcp import SCHEMA_VERSION


def test_status_ok():
    r = make_response("ok", data={"a": 1}, summary="hi")
    assert r["status"] == "ok"
    assert r["data"] == {"a": 1}
    assert r["summary"] == "hi"
    assert r["schema_version"] == SCHEMA_VERSION
    assert r["error"] is None


def test_status_stale_has_staleness_seconds():
    r = make_response("stale", data=None, staleness_seconds=900, summary="aged")
    assert r["status"] == "stale"
    assert r["staleness_seconds"] == 900


def test_status_degraded():
    r = make_response("degraded", data={"partial": True}, summary="x")
    assert r["status"] == "degraded"


def test_status_unavailable_has_error():
    r = make_response("unavailable", error="rate limit")
    assert r["status"] == "unavailable"
    assert r["data"] is None
    assert r["error"] == "rate limit"


def test_summary_truncation():
    long = "x" * (SUMMARY_MAX_CHARS + 50)
    r = make_response("ok", summary=long)
    assert len(r["summary"]) == SUMMARY_MAX_CHARS
    assert r["summary"].endswith("...")


def test_summary_at_boundary_not_truncated():
    exact = "y" * SUMMARY_MAX_CHARS
    r = make_response("ok", summary=exact)
    assert r["summary"] == exact


def test_missing_data_is_none_not_omitted():
    r = make_response("ok", summary="hi")
    assert "data" in r
    assert r["data"] is None


def test_every_envelope_carries_the_declared_version():
    r = make_response("ok")
    assert r["schema_version"] == SCHEMA_VERSION


def test_the_version_literal_is_pinned_in_exactly_one_place():
    """The guard the two rewritten tests above can no longer give.

    They asserted the literal `"v1.0"`, and one was named `test_schema_version_is_always_v1`.
    The constant moved to v2.0 for the Tier 2 Greeks and both assertions were left behind --
    invisible, because this whole directory was outside the main run.

    Asserting against the constant means a bump can never leave a stale assertion. So the
    LITERAL is pinned once, here: a version change is then a deliberate two-line edit, and this
    test is the line that makes someone look.
    """
    assert SCHEMA_VERSION == "v2.0"

    # ...and no LIVE line in the envelope names a version. Docstrings are excluded: the one in
    # `make_response` now recounts the v1.0 mistake deliberately, and a scan that could not tell
    # documentation from behaviour would fail on the sentence explaining the fix. This is the
    # fourth time that trap has been hit in this lane.
    import ast
    import inspect

    from hub_mcp import envelope

    src = inspect.getsource(envelope)
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value not in docstrings]
    assert not [v for v in literals if v.startswith("v") and v[1:2].isdigit()], literals
    # POSITIVE CONTROL: the walk does find the module's other string literals.
    assert any(v == "status" or "schema_version" in v for v in literals), literals
