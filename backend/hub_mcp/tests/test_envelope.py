"""Tests for backend/mcp/envelope.py."""

from hub_mcp.envelope import SUMMARY_MAX_CHARS, make_response


def test_status_ok():
    r = make_response("ok", data={"a": 1}, summary="hi")
    assert r["status"] == "ok"
    assert r["data"] == {"a": 1}
    assert r["summary"] == "hi"
    assert r["schema_version"] == "v1.0"
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


def test_schema_version_is_always_v1():
    r = make_response("ok")
    assert r["schema_version"] == "v1.0"
