"""Tests for backend/mcp/rate_limit.py."""

from mcp.rate_limit import EXEMPT_TOOLS, LIMITS_PER_MINUTE, RateLimiter


def test_under_limit_allowed():
    rl = RateLimiter()
    for _ in range(LIMITS_PER_MINUTE):
        assert rl.check("token-a", "hub_get_bias_composite") is None


def test_minute_limit_triggers():
    rl = RateLimiter()
    for _ in range(LIMITS_PER_MINUTE):
        rl.check("token-b", "hub_get_bias_composite")
    err = rl.check("token-b", "hub_get_bias_composite")
    assert err is not None
    assert "Rate limit" in err
    assert "minute" in err


def test_mcp_ping_is_exempt():
    rl = RateLimiter()
    for _ in range(LIMITS_PER_MINUTE + 10):
        assert rl.check("token-c", "mcp_ping") is None
    assert "mcp_ping" in EXEMPT_TOOLS


def test_per_token_bucket_isolation():
    rl = RateLimiter()
    for _ in range(LIMITS_PER_MINUTE):
        rl.check("token-d", "hub_get_bias_composite")
    # token-d is over; token-e should still be clean
    assert rl.check("token-e", "hub_get_bias_composite") is None
