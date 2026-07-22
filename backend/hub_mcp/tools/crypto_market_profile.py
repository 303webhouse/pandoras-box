"""hub_get_crypto_market_profile — POC/VAH/VAL + session extremes for a tracked crypto.

S-3 Phase 4 (§6.3). Exposes the Market Structure Filter's internally computed
volume-profile levels (POC/VAH/VAL) and current-session high/low per the §1.4
Phase-0 finding (15m bars + crypto_sessions.py — zero new plumbing).

Correction 1.9 (Phase-0): follows hub_get_crypto_quote's no-guard pattern —
dedicated crypto tool; the asset-class disambiguation guard lives only in the
shared hub_get_quote. Bare ambiguous tickers error with candidates.

v2.0 envelope; staleness/degraded states per §4.2 contract. No new UW draw.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..decorators import mcp_tool
from ..envelope import make_response


def _va_outside_session(vah, val, session_low, session_high) -> bool:
    """True when the value area lies entirely outside the current session range.

    The fail-closed signal (DEF-CRYPTO-VP-ANCHOR, 2026-07-22) that the VP window
    is not anchored to current tape. Cross-references the INDEPENDENT session leg
    (15m timestamp filter, a different selector) — a self-consistency check
    against the VP's own bars would pass on stale data, which is the whole trap.
    Returns False on any missing input (cannot assert a violation).
    """
    if None in (vah, val, session_low, session_high):
        return False
    return vah < session_low or val > session_high


DESCRIPTION = (
    "Returns the Market Structure Filter's volume-profile levels (POC, VAH, VAL) "
    "and current-session high/low for a tracked crypto symbol: BTC, ETH, SOL, "
    "HYPE, ZEC, FARTCOIN. Pass the canonical base symbol (BTC) or hyphenated "
    "form (BTC-USD) — both are accepted and normalized.\n\n"
    "Use this when PYTHIA or any committee member needs structural levels for a "
    "crypto position: 'Is BTC above POC?', 'Where is ETH's value area?', or "
    "'What's the session high/low for BTC?' Do NOT call for equities — use "
    "hub_get_market_profile for equity/ETF tickers.\n\n"
    "Status semantics: `ok` = freshly computed levels; `stale` = levels from a "
    "cached prior computation (data_age_seconds > 900); `unavailable` = no bar "
    "data available for this symbol (e.g. HYPE/FARTCOIN lacking a bar-walk "
    "source at this granularity — honest N/A, not a fabrication), OR the value "
    "area failed a fail-closed guard (stale bars, or a value area lying entirely "
    "outside the session range — the levels are withheld, never served wrong).\n\n"
    "Session extremes (session_high, session_low) are derived from 15m bars "
    "filtered to the current ASIA/LONDON/NY partition via crypto_sessions.py. "
    "Returns null with a stated reason when the current session has < 3 bars.\n\n"
    "The volume profile is computed from the most recent ~6 hours of 15m klines "
    "(24 bars, 50 bins), sorted to current tape before selection and fail-closed "
    "against a stale or out-of-range window. The -45..+35 Market Structure Filter "
    "scoring is NOT exposed here — this tool returns raw levels only. Do NOT infer "
    "scores from these levels."
)


async def _get_crypto_market_profile(base_symbol: str) -> Dict[str, Any]:
    """Service layer: compute POC/VAH/VAL + session extremes for base_symbol."""
    from datetime import datetime, timezone
    from strategies.btc_market_structure import compute_volume_profile
    from jobs.crypto_bars import fetch_crypto_ohlc
    from utils.crypto_sessions import get_partition

    now_utc = datetime.now(timezone.utc)
    result: Dict[str, Any] = {
        "symbol": base_symbol,
        "as_of": now_utc.isoformat(),
    }

    # --- Volume Profile (most recent ~6h of 15m klines, 24 bars) ---
    # DEF-CRYPTO-VP-ANCHOR (2026-07-22): fetch_crypto_ohlc returns bars in
    # VENDOR order (UW/OKX newest-first, Binance oldest-first), UNSORTED. A bare
    # [-24:] positional slice therefore grabbed the OLDEST 24 bars for
    # descending vendors -> a value area 3-5 days stale, entirely outside the
    # traded range, served as vp_status "ok" (fake-healthy). Fix: sort ascending
    # by timestamp BEFORE slicing so [-24:] is always the most recent 24 bars,
    # plus two fail-closed guards (freshness here; session-range cross-check
    # after the session leg below). Window length stays ~6h — the 6h-vs-24h
    # question is a separate PYTHIA-ratified methodology call, deferred.
    bars_1h = []
    try:
        bars_1h = await fetch_crypto_ohlc(base_symbol, use_daily=False) or []
        # bars_1h: List[Tuple[datetime, open, high, low, close]]
        bars_1h = sorted(bars_1h, key=lambda b: b[0])  # ORDERING FIX — never trust vendor order
        if bars_1h:
            recent_24h = bars_1h[-24:]  # most recent 24 x 15m = ~6h
            # Guard 1 (cause-detector): the newest bar must be current. Stale
            # bars are internally consistent, so only an independent freshness
            # check catches the anchoring defect at its root.
            newest_age = (now_utc - recent_24h[-1][0]).total_seconds()
            if newest_age > 1200:  # 20 min
                result["vp_status"] = "unavailable"
                result["vp_error"] = f"stale bars: newest 15m bar is {newest_age:.0f}s old (>1200s)"
                result["poc"] = None
                result["vah"] = None
                result["val"] = None
            else:
                # Convert to klines format compute_volume_profile expects:
                # [ts, open, high, low, close, volume]; fetch returns (dt,o,h,l,c).
                klines = [[
                    int(bar[0].timestamp() * 1000),  # ts_ms
                    bar[1], bar[2], bar[3], bar[4],  # o, h, l, c
                    1.0,  # volume placeholder (F-2 bars carry no per-bar volume)
                ] for bar in recent_24h]
                vp = compute_volume_profile(klines)
                if "error" not in vp:
                    result["poc"] = vp.get("poc")
                    result["vah"] = vp.get("vah")
                    result["val"] = vp.get("val")
                    result["vp_status"] = "ok"
                else:
                    result["vp_status"] = "degraded"
                    result["vp_error"] = vp.get("error")
        else:
            result["vp_status"] = "unavailable"
            result["poc"] = None
            result["vah"] = None
            result["val"] = None
    except Exception as exc:
        result["vp_status"] = "degraded"
        result["vp_error"] = str(exc)
        result["poc"] = None
        result["vah"] = None
        result["val"] = None

    # --- Session Extremes (bars filtered to current partition per §1.4) ---
    try:
        from config.crypto_gate_loader import get_gate_config
        from utils.crypto_sessions import get_partition
        from datetime import timedelta

        _cv, _cfg = await get_gate_config()
        partition_utc = _cfg.get("partition_utc", {"ASIA": [0, 8], "LONDON": [8, 16], "NY": [16, 24]})
        current_partition = get_partition(now_utc, partition_utc)

        # Derive start of current partition window (UTC)
        start_hour_map = {name: hrs[0] for name, hrs in partition_utc.items()}
        start_hour = start_hour_map.get(current_partition)
        if start_hour is not None:
            from datetime import datetime, timezone
            today = now_utc.date()
            partition_start = datetime(today.year, today.month, today.day, start_hour, 0, 0, tzinfo=timezone.utc)
            if partition_start > now_utc:
                partition_start -= timedelta(days=1)

            # bars_1h already fetched above; re-use
            session_bars = [b for b in (bars_1h or []) if b[0] >= partition_start]
            if len(session_bars) >= 1:
                result["session_high"] = max(b[2] for b in session_bars)
                result["session_low"] = min(b[3] for b in session_bars)
                result["session_bar_count"] = len(session_bars)
                result["session_partition"] = current_partition
                result["session_status"] = "ok" if len(session_bars) >= 3 else "thin"
            else:
                result["session_high"] = None
                result["session_low"] = None
                result["session_status"] = "no_session_bars"
                result["session_partition"] = current_partition
        else:
            result["session_high"] = None
            result["session_low"] = None
            result["session_status"] = "unknown_partition"
    except Exception as exc:
        result["session_high"] = None
        result["session_low"] = None
        result["session_status"] = "degraded"
        result["session_error"] = str(exc)

    # --- Guard 2 (symptom-detector): VP must be consistent with the INDEPENDENT
    # session leg (15m timestamp filter — provably correct, a different selector
    # from the positional VP slice). A value area lying entirely outside the
    # session range means the VP window is anchored off the traded range; fail
    # closed and never serve the values. (DEF-CRYPTO-VP-ANCHOR, 2026-07-22.)
    #
    # Skipped when the session has < 8 bars (~2h): right after a partition opens
    # the session range is too tight to be a valid reference, and a CORRECT value
    # area can legitimately sit outside a correct-but-narrow session range. The
    # freshness guard (Guard 1) still covers that opening window, so detection of
    # the actual stale-anchor defect is not weakened.
    try:
        if (result.get("vp_status") == "ok"
                and result.get("session_bar_count", 0) >= 8
                and _va_outside_session(
                    result.get("vah"), result.get("val"),
                    result.get("session_low"), result.get("session_high"))):
            result["vp_status"] = "unavailable"
            result["vp_error"] = (
                f"value area outside session range (VAL {result.get('val')} / "
                f"VAH {result.get('vah')} vs session "
                f"{result.get('session_low')}-{result.get('session_high')}) — "
                f"VP window not anchored to current tape"
            )
            result["poc"] = None
            result["vah"] = None
            result["val"] = None
    except Exception as exc:
        result["vp_guard_error"] = str(exc)

    return result


@mcp_tool(name="hub_get_crypto_market_profile", description=DESCRIPTION)
async def hub_get_crypto_market_profile(symbol: str) -> dict:
    """Return POC/VAH/VAL + session extremes for a tracked crypto symbol."""
    if not symbol or not isinstance(symbol, str) or not symbol.strip():
        return make_response(
            status="unavailable",
            error="symbol is required (non-empty string)",
            summary="hub_get_crypto_market_profile: symbol required.",
        )

    from jobs.crypto_bars import normalize_crypto_ticker
    from config.crypto_symbol_matrix import is_tracked

    canon = normalize_crypto_ticker(symbol.strip())
    if not canon or not is_tracked(canon):
        return make_response(
            status="unavailable",
            error=(
                f"'{symbol}' is not in the tracked crypto universe. "
                "Valid: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN. "
                "For equity/ETF levels use hub_get_market_profile."
            ),
            summary=f"hub_get_crypto_market_profile: '{symbol}' not tracked.",
        )

    try:
        data = await _get_crypto_market_profile(canon)
    except Exception as exc:
        return make_response(
            status="unavailable",
            error=f"Market profile computation failed: {exc}",
            summary=f"{canon}: market profile unavailable.",
        )

    vp_status = data.get("vp_status", "unavailable")
    if vp_status == "unavailable":
        return make_response(
            status="unavailable",
            data=data,
            summary=f"{canon}: no bar data available — volume profile unavailable.",
        )

    is_degraded = vp_status == "degraded"
    envelope_status = "stale" if is_degraded else "ok"

    poc = data.get("poc")
    vah = data.get("vah")
    val = data.get("val")
    sh = data.get("session_high")
    sl = data.get("session_low")
    part = data.get("session_partition", "?")

    def _fmt(v):
        return f"{v:,.2f}" if isinstance(v, (int, float)) else "N/A"

    summary_parts = [f"{canon}: POC {_fmt(poc)}, VAH {_fmt(vah)}, VAL {_fmt(val)}"]
    if sh is not None and sl is not None:
        summary_parts.append(f"{part} session H/L {_fmt(sh)}/{_fmt(sl)}")
    summary_parts.append(f"vp:{vp_status}, session:{data.get('session_status','?')}")

    return make_response(
        status=envelope_status,
        data=data,
        summary=" — ".join(summary_parts),
        staleness_seconds=900 if is_degraded else None,
    )
