"""R-IV.1461(g)2: XLK read ROTATING_IN while ranked last.

That is the state's own rule (5d RS - 20d RS >= +3 with 20d RS < 0: a laggard improving), so
the state is unchanged. What was hidden is WHY, and that the breadth score counts it as a
leader. Display only: the rule is served with the data, each sector carries the two numbers
that decide it, and the summary says when a ROTATING_IN sector sits at the bottom.
"""
import asyncio
from unittest.mock import AsyncMock, patch


def _raw():
    rows = {"Technology": ("XLK", -1.17, -8.35, 1.2, 9.55, "SURGING")}
    for i, etf in enumerate(("XLE", "XLV", "XLP", "XLU", "XLB", "XLRE", "XLF", "XLY")):
        rows["S%d" % i] = (etf, 3.0, 13.0 - i, 2.0, -11.0 + i, "DUMPING")
    rows["Industrials"] = ("XLI", 0.77, 0.31, 0.5, 0.2, "STEADY")
    rows["Communication Services"] = ("XLC", -8.46, -7.64, -7.0, 0.6, "STEADY")
    return {n: {"etf": e, "rs_10d": a, "rs_20d": b, "rs_5d": c, "rotation_momentum": m,
                "status": st} for n, (e, a, b, c, m, st) in rows.items()}


def test_the_state_is_unchanged_and_the_reason_is_served():
    from hub_mcp.tools.sector_strength import hub_get_sector_strength, STATE_RULE
    with patch("hub_mcp.tools.sector_strength.get_sector_rotation",
               new=AsyncMock(return_value=_raw())):
        r = asyncio.run(hub_get_sector_strength())
    xlk = [s for s in r["data"]["sectors"] if s["etf"] == "XLK"][0]
    assert xlk["state"] == "ROTATING_IN" and xlk["rank_20d"] == 11
    assert (xlk["rs_5d"], xlk["rotation_momentum"]) == (1.2, 9.55)
    assert r["data"]["state_rule"] == STATE_RULE and "can be ranked last" in STATE_RULE
    assert "XLK reads ROTATING_IN from rank 11/11 on 20d RS" in r["summary"]
    # the computed values the signal join reads are untouched
    assert r["data"]["rotation_regime"] == "CONCENTRATED_LEADERSHIP"
    assert r["data"]["leadership_breadth_score"] == 0.09
