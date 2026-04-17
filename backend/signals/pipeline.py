"""
Unified Signal Processing Pipeline (Phase 4)

Single entry point for ALL signal sources. Each webhook handler normalizes
its payload into a standard signal dict, then calls process_signal_unified().
This replaces the duplicated log/score/cache/broadcast logic across handlers.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from database.postgres_client import log_signal, update_signal_with_score
from database.redis_client import cache_signal
from scoring.trade_ideas_scorer import calculate_signal_score, get_score_tier
from websocket.broadcaster import manager
from utils.bias_snapshot import get_bias_snapshot

logger = logging.getLogger(__name__)

COMMITTEE_SCORE_THRESHOLD = 75.0  # Minimum score_v2 to trigger committee

# ── Cross-asset flow alignment map (ZEUS Phase 1A.1) ──
# Component → list of related ETFs/tickers to check for sentiment confirmation
COMPONENT_TO_ETF = {
    "NVDA": ["XLK", "QQQ", "SMH"],
    "AAPL": ["XLK", "QQQ"],
    "MSFT": ["XLK", "QQQ"],
    "GOOGL": ["XLC", "QQQ"],
    "AMZN": ["XLC", "QQQ"],
    "META": ["XLC", "QQQ"],
    "TSLA": ["XLY", "QQQ"],
    "AMD":  ["XLK", "SMH"],
    "AVGO": ["XLK", "SMH"],
    "JPM":  ["XLF"],
    "BAC":  ["XLF"],
    "GS":   ["XLF"],
    "XOM":  ["XLE"],
    "CVX":  ["XLE"],
    # Reverse: ETF → representative components
    "XLK":  ["NVDA", "MSFT"],
    "XLF":  ["JPM", "BAC"],
    "XLE":  ["XOM", "CVX"],
    "SMH":  ["NVDA", "AVGO"],
}


async def _check_cross_asset_flow_alignment(
    conn, ticker: str, sentiment: str, is_long: bool, is_short: bool,
) -> int:
    """
    Returns +4 if the signal direction sentiment aligns on BOTH the signal ticker
    AND a related ETF/component within the last 4 hours. Returns 0 otherwise.
    """
    related = COMPONENT_TO_ETF.get(ticker.upper(), [])
    if not related or not sentiment:
        return 0

    want_sentiment = "BULLISH" if is_long else ("BEARISH" if is_short else None)
    if not want_sentiment or sentiment != want_sentiment:
        return 0

    try:
        related_row = await conn.fetchrow(
            "SELECT ticker FROM flow_events "
            "WHERE ticker = ANY($1::text[]) "
            "AND flow_sentiment = $2 "
            "AND captured_at > NOW() - INTERVAL '4 hours' "
            "LIMIT 1",
            related, sentiment,
        )
        return 4 if related_row else 0
    except Exception:
        return 0


# ── Nemesis Countertrend Lane ──
# Tickers always allowed through the countertrend gate (e.g. inverse ETFs)
COUNTERTREND_WHITELIST = {"SQQQ", "SPXS", "TZA", "SDOW", "UVXY", "VXX", "SH", "SDS"}

# Composite bias thresholds that qualify as "extreme" (unlock countertrend)
BIAS_EXTREME_BULLISH = 75   # composite >= this = extreme bull -> allow counter-SHORT
BIAS_EXTREME_BEARISH = 25   # composite <= this = extreme bear -> allow counter-LONG

# Committee score floor for countertrend signals
COUNTERTREND_COMMITTEE_THRESHOLD = 90


async def _maybe_flag_for_committee(signal_data: Dict[str, Any]) -> None:
    """
    Flag signal for display in #signals channel with Analyze button.
    Sets status=PENDING_REVIEW — committee does NOT run automatically.
    Skips Scout alerts and signals that already have committee data.
    """
    # Skip scouts and manual signals
    if signal_data.get("signal_type") in ("SCOUT_ALERT", "MANUAL"):
        return

    # Skip if already has committee data
    if signal_data.get("committee_data") or signal_data.get("committee_run_id"):
        return

    # Check score threshold (prefer score_v2, fall back to score)
    score = signal_data.get("score_v2") or signal_data.get("score") or 0
    is_countertrend = signal_data.get("countertrend") or "wrr" in (signal_data.get("strategy") or "").lower()
    threshold = COUNTERTREND_COMMITTEE_THRESHOLD if is_countertrend else COMMITTEE_SCORE_THRESHOLD
    if score < threshold:
        return

    signal_id = signal_data.get("signal_id")
    if not signal_id:
        return

    # Auto-promote high-score signals directly to COMMITTEE_REVIEW
    # so the VPS bridge picks them up automatically (no manual click needed)
    AUTO_PROMOTE_THRESHOLD = 80.0
    new_status = "COMMITTEE_REVIEW" if score >= AUTO_PROMOTE_THRESHOLD else "PENDING_REVIEW"

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE signals
                SET status = $2,
                    committee_requested_at = NOW()
                WHERE signal_id = $1
                AND status = 'ACTIVE'
                """,
                signal_id,
                new_status,
            )
        signal_data["status"] = new_status
        if new_status == "COMMITTEE_REVIEW":
            logger.info(f"🤖 Auto-promoted to committee: {signal_data.get('ticker')} (score={score})")
        else:
            logger.info(f"📡 Flagged for signals channel: {signal_data.get('ticker')} (score={score})")
    except Exception as e:
        logger.warning(f"Failed to flag {signal_id} for committee: {e}")


def calculate_expiry(signal_data: Dict[str, Any]) -> Optional[datetime]:
    """
    Calculate signal expiry based on timeframe and asset class.
    Returns None for signals that shouldn't auto-expire.
    """
    timeframe = (signal_data.get("timeframe") or "1H").upper()

    # Intraday signals expire in 4 hours
    if timeframe in ("1", "3", "5", "15", "30", "1M", "3M", "5M", "15M", "30M", "1H"):
        return datetime.utcnow() + timedelta(hours=4)
    # Swing signals expire in 24 hours
    elif timeframe in ("4H", "D", "1D", "DAILY"):
        return datetime.utcnow() + timedelta(hours=24)
    # Weekly/monthly signals expire in 7 days
    elif timeframe in ("W", "1W", "WEEKLY", "M", "MONTHLY"):
        return datetime.utcnow() + timedelta(days=7)
    # Default: 4 hours
    return datetime.utcnow() + timedelta(hours=4)


async def write_signal_outcome(signal_data: Dict[str, Any]) -> None:
    """
    Write a PENDING outcome record for outcome tracking.
    Extracted from tradingview.py._write_signal_outcome() for shared use.
    """
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO signal_outcomes
                    (signal_id, symbol, signal_type, direction, cta_zone,
                     entry, stop, t1, t2, invalidation_level, created_at, outcome)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), 'PENDING')
                ON CONFLICT (signal_id) DO NOTHING
                """,
                signal_data.get("signal_id"),
                signal_data.get("ticker"),
                signal_data.get("signal_type"),
                signal_data.get("direction"),
                signal_data.get("cta_zone"),
                signal_data.get("entry_price"),
                signal_data.get("stop_loss"),
                signal_data.get("target_1"),
                signal_data.get("target_2"),
                signal_data.get("invalidation_level"),
            )
    except Exception as e:
        logger.warning(f"Failed to record signal outcome: {e}")


async def apply_scoring(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply Trade Ideas Scorer to a signal.

    Extracted from tradingview.py.apply_signal_scoring() for shared use.
    Includes composite bias lookup, contrarian qualification, and sector rotation.
    """
    try:
        # Get composite bias score
        composite_score = None
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached:
                composite_score = cached.composite_score
        except Exception as comp_err:
            logger.warning(f"Composite bias unavailable: {comp_err}")

        # Build bias data
        if composite_score is not None:
            current_bias = {"composite_score": composite_score}
        else:
            from scheduler.bias_scheduler import get_bias_status
            bias_status = get_bias_status()
            current_bias = {
                "daily": bias_status.get("daily", {}),
                "weekly": bias_status.get("weekly", {}),
                "cyclical": bias_status.get("cyclical", {}),
            }

        # Fetch sector strength from Redis (refreshed every 15s by sector_refresh_loop)
        sector_strength = None
        try:
            from database.redis_client import get_redis_client
            import json as _json
            redis = await get_redis_client()
            if redis:
                raw = await redis.get("sector:strength")
                if raw:
                    sector_strength = _json.loads(raw)
        except Exception as sect_err:
            logger.debug(f"Sector strength unavailable for scoring: {sect_err}")

        # Fetch regime context for catalyst-alignment + reversal mode scoring
        regime_context = None
        try:
            from database.redis_client import get_redis_client as _get_rc
            _rc = await _get_rc()
            if _rc:
                regime_raw = await _rc.get("regime:current_override")
                if regime_raw:
                    import json as _rj
                    regime_context = _rj.loads(regime_raw)
        except Exception:
            pass

        # P1A hotfix: fetch 10-day price range for freshness penalty
        try:
            from signals.price_enrichment import enrich_price_range
            signal_data = await enrich_price_range(signal_data)
        except Exception as enrich_err:
            logger.debug("Price range enrichment skipped: %s", enrich_err)

        # P2: Flow enrichment — yfinance options chain for P/C ratio + premium direction
        try:
            from signals.flow_enrichment import enrich_flow_data
            signal_data = await enrich_flow_data(signal_data)
        except Exception as flow_err:
            logger.debug("Flow enrichment skipped: %s", flow_err)

        # Fetch SPY ADX regime data for chop penalty
        regime_data = {}
        try:
            from database.redis_client import get_redis_client as _get_regime_rc
            import json as _regime_json
            _rrc = await _get_regime_rc()
            if _rrc:
                _regime_raw = await _rrc.get("regime:spy_adx")
                if _regime_raw:
                    regime_data = _regime_json.loads(_regime_raw)
        except Exception:
            pass

        # Calculate score (with sector strength + regime context + regime data)
        score, bias_alignment, triggering_factors = calculate_signal_score(
            signal_data, current_bias, sector_strength=sector_strength,
            regime_context=regime_context, regime_data=regime_data
        )

        # Contrarian qualification
        if bias_alignment in ("COUNTER_BIAS", "STRONG_COUNTER") and composite_score is not None:
            try:
                from scoring.contrarian_qualifier import qualify_contrarian
                direction = signal_data.get("direction", "").upper()
                cq = await qualify_contrarian(signal_data, composite_score, direction)
                if cq["qualified"]:
                    original_multiplier = triggering_factors.get("bias_alignment", {}).get("multiplier", 1.0)
                    if original_multiplier < 1.0:
                        raw_score = triggering_factors.get("calculation", {}).get("raw_score", score)
                        score = min(100, max(0, raw_score * 1.0))
                        score = round(score, 2)
                    signal_data["contrarian_qualified"] = True
                    signal_data["contrarian_reasons"] = cq["reasons"]
                    triggering_factors["contrarian"] = {
                        "qualified": True,
                        "reasons": cq["reasons"],
                        "original_multiplier": original_multiplier,
                        "restored_multiplier": 1.0,
                    }
                    bias_alignment = "CONTRARIAN_QUALIFIED"
            except Exception as cq_err:
                logger.warning(f"Contrarian check failed: {cq_err}")

        # Sector rotation bonus: REMOVED (Brief 6D)
        # Sector scoring is now handled inside calculate_signal_score() via the
        # sector_strength parameter. The old sector_rotation_bonus.py path was
        # a separate module that caused double-counting. All sector effects now
        # flow through SECTOR_PRIORITY_BONUS in trade_ideas_scorer.py.

        # P2B: Squeeze score cross-reference (post-score bonus)
        try:
            from database.postgres_client import get_postgres_client
            pool = await get_postgres_client()
            sq_ticker = (signal_data.get("ticker") or "").upper()
            async with pool.acquire() as conn:
                sq_row = await conn.fetchrow(
                    "SELECT composite_score, squeeze_tier, short_pct_float, "
                    "days_to_cover FROM squeeze_scores WHERE ticker = $1",
                    sq_ticker,
                )
            if sq_row and (sq_row["composite_score"] or 0) >= 20:
                cs = float(sq_row["composite_score"] or 0)
                squeeze_bonus = 8 if cs >= 30 else 4
                score = min(100, score + squeeze_bonus)
                triggering_factors["squeeze"] = {
                    "bonus": squeeze_bonus,
                    "composite_score": cs,
                    "squeeze_tier": sq_row["squeeze_tier"],
                    "short_float": float(sq_row["short_pct_float"]) if sq_row["short_pct_float"] else None,
                    "days_to_cover": float(sq_row["days_to_cover"]) if sq_row["days_to_cover"] else None,
                }
                logger.info("Squeeze confluence for %s: +%d (score %.0f, tier %s)",
                            sq_ticker, squeeze_bonus, cs, sq_row["squeeze_tier"])
        except Exception as sq_err:
            logger.debug("Squeeze cross-reference skipped: %s", sq_err)

        # P2C / P4A: UW flow cross-reference — directional + premium-tiered (ZEUS 1A.1)
        try:
            from database.postgres_client import get_postgres_client as _gpc
            _pool = await _gpc()
            fl_ticker = (signal_data.get("ticker") or "").upper()
            async with _pool.acquire() as conn:
                fl_row = await conn.fetchrow(
                    "SELECT total_premium, call_premium, put_premium, "
                    "flow_sentiment, pc_ratio "
                    "FROM flow_events WHERE ticker = $1 "
                    "AND captured_at > NOW() - INTERVAL '4 hours' "
                    "ORDER BY captured_at DESC LIMIT 1",
                    fl_ticker,
                )

                if fl_row:
                    call_prem = float(fl_row["call_premium"] or 0)
                    put_prem  = float(fl_row["put_premium"] or 0)
                    total     = float(fl_row["total_premium"] or 0)
                    sentiment = (fl_row["flow_sentiment"] or "").upper()
                    pc_ratio  = float(fl_row["pc_ratio"] or 0) if fl_row["pc_ratio"] else None

                    direction = (signal_data.get("direction") or "").upper()
                    is_long   = direction in ("LONG", "BUY", "BULLISH")
                    is_short  = direction in ("SHORT", "SELL", "BEARISH")

                    flow_bonus  = 0
                    flow_reason = []

                    # Premium-tiered directional scoring
                    if call_prem > 2_000_000 and sentiment == "BULLISH":
                        if is_long:
                            flow_bonus += 6
                            flow_reason.append(f"bullish flow ${call_prem/1e6:.1f}M calls")
                        elif is_short:
                            flow_bonus -= 3
                            flow_reason.append(f"WARN: short vs bullish flow ${call_prem/1e6:.1f}M calls")

                    if put_prem > 2_000_000 and sentiment == "BEARISH":
                        if is_short:
                            flow_bonus += 6
                            flow_reason.append(f"bearish flow ${put_prem/1e6:.1f}M puts")
                        elif is_long:
                            flow_bonus -= 3
                            flow_reason.append(f"WARN: long vs bearish flow ${put_prem/1e6:.1f}M puts")

                    # Legacy small-premium bonus (backward compat, downgraded +5→+2)
                    if total > 1_000_000 and flow_bonus == 0:
                        flow_bonus = 2
                        flow_reason.append(f"flow ${total/1e6:.1f}M total, direction-neutral")

                    # Cross-asset alignment bonus
                    ca_bonus = await _check_cross_asset_flow_alignment(
                        conn, fl_ticker, sentiment, is_long, is_short,
                    )
                    if ca_bonus:
                        flow_bonus += ca_bonus
                        flow_reason.append(f"cross-asset align +{ca_bonus}")

                    if flow_bonus != 0:
                        score = max(0, min(100, score + flow_bonus))
                        triggering_factors["flow"] = {
                            "bonus": flow_bonus,
                            "sentiment": sentiment,
                            "total_premium": total,
                            "call_premium": call_prem,
                            "put_premium": put_prem,
                            "pc_ratio": pc_ratio,
                            "reasons": flow_reason,
                        }
                        logger.info(
                            "Flow enrichment %s %s: %+d (%s)",
                            fl_ticker, direction, flow_bonus, "; ".join(flow_reason),
                        )
        except Exception as _fe:
            logger.debug("P4A flow enrichment skipped: %s", _fe)

        # WH-CONFLUENCE enrichment: check for WH-ACC backing + fresh darkpool blocks
        # Must run BEFORE apply_tier3_confluence_bonus so the wh_confluence key is present.
        try:
            from enrichment.wh_confluence import check_wh_confluence
            wh_ticker = (signal_data.get("ticker") or "").upper()
            wh_dir    = (signal_data.get("direction") or "").upper()
            wh_conf = await check_wh_confluence(wh_ticker, wh_dir)
            if wh_conf.get("confluence_found"):
                wh_acc_bonus = wh_conf.get("bonus", 0)
                if wh_acc_bonus:
                    score = min(100, max(0, score + wh_acc_bonus))
                triggering_factors["wh_confluence"] = wh_conf
                logger.info(
                    "WH confluence: %s %s — acc_bonus=%+d ta_signals=%s",
                    wh_ticker, wh_dir, wh_acc_bonus, wh_conf.get("ta_signals", []),
                )
        except Exception as _wc:
            logger.debug("WH confluence enrichment skipped: %s", _wc)

        # Tier 3 confluence cap: stack TA signal bonuses up to +20 for Tier 1 signals
        try:
            from scoring.trade_ideas_scorer import apply_tier3_confluence_bonus
            score, triggering_factors = apply_tier3_confluence_bonus(
                signal_data, score, triggering_factors
            )
        except Exception as _t3:
            logger.debug("Tier 3 confluence bonus skipped: %s", _t3)

        # P4B: Pythia market profile position cross-reference
        # Phase 0.3.2 — Option B: no Pythia coverage = watchlist ceiling (never top_feed)
        try:
            from webhooks.pythia_events import get_pythia_profile_position
            pp_ticker = (signal_data.get("ticker") or "").upper()
            pp_price = signal_data.get("entry_price")
            pp_dir = (signal_data.get("direction") or "").upper()
            if pp_ticker and pp_price and float(pp_price) > 0:
                pp = await get_pythia_profile_position(pp_ticker, float(pp_price), pp_dir)
                pp_total = pp.get("total_pythia_adjustment", pp.get("profile_bonus", 0))
                if pp_total != 0:
                    score = min(100, max(0, score + pp_total))
                triggering_factors["profile_position"] = pp
                logger.info(
                    "Pythia profile for %s: coverage=%s zone=%s adj=%+d",
                    pp_ticker, pp.get("pythia_coverage"), pp.get("zone", "?"), pp_total,
                )

                # Option B gate: ticker not on Pythia watchlist → watchlist ceiling
                if not pp.get("pythia_coverage", False):
                    signal_data["feed_tier_ceiling"] = "watchlist"
                    signal_data.setdefault("enrichment_data", {})["needs_structural_review"] = True
                    logger.info(
                        "Signal %s on %s has no Pythia coverage — watchlist ceiling applied",
                        signal_data.get("signal_id", "?"), pp_ticker,
                    )
        except Exception as pp_err:
            logger.debug("Pythia profile check skipped: %s", pp_err)

        # Update signal
        signal_data["score"] = score
        signal_data["bias_alignment"] = bias_alignment
        signal_data["triggering_factors"] = triggering_factors
        signal_data["scoreTier"] = get_score_tier(score)

        # ── Nemesis countertrend gate ──
        # Reject countertrend signals unless bias is at an extreme
        strategy_lower = (signal_data.get("strategy") or "").lower()
        ticker = (signal_data.get("ticker") or "").upper()
        is_countertrend = signal_data.get("countertrend") or "nemesis" in strategy_lower or "wrr" in strategy_lower
        if is_countertrend and ticker not in COUNTERTREND_WHITELIST:
            direction_ct = signal_data.get("direction", "").upper()
            extreme_ok = False
            if composite_score is not None:
                if direction_ct in ("SHORT", "SELL") and composite_score >= BIAS_EXTREME_BULLISH:
                    extreme_ok = True  # Extreme bull -> counter-short allowed
                elif direction_ct in ("LONG", "BUY") and composite_score <= BIAS_EXTREME_BEARISH:
                    extreme_ok = True  # Extreme bear -> counter-long allowed
            if not extreme_ok:
                signal_data["countertrend_rejected"] = True
                signal_data["countertrend_reason"] = (
                    f"Bias not extreme (composite={composite_score}). "
                    f"Need >= {BIAS_EXTREME_BULLISH} for counter-short or <= {BIAS_EXTREME_BEARISH} for counter-long."
                )
                logger.info(
                    f"Nemesis REJECTED: {ticker} {direction_ct} — {signal_data['countertrend_reason']}"
                )
            else:
                signal_data["countertrend"] = True
                signal_data["half_size"] = True
                logger.info(
                    f"Nemesis APPROVED: {ticker} {direction_ct} — extreme bias ({composite_score}), half-size"
                )

        # Set confidence/priority based on score
        direction = signal_data.get("direction", "").upper()
        if score >= 85:
            signal_data["confidence"] = "HIGH"
            signal_data["priority"] = "HIGH"
            if direction in ("LONG", "BUY"):
                signal_data["signal_type"] = "APIS_CALL"
                logger.info(f"🐝 APIS CALL: {signal_data.get('ticker')} (score: {score})")
            elif direction in ("SHORT", "SELL"):
                signal_data["signal_type"] = "KODIAK_CALL"
                logger.info(f"🐻 KODIAK CALL: {signal_data.get('ticker')} (score: {score})")
        elif score >= 75:
            signal_data["confidence"] = "HIGH"
            signal_data["priority"] = "HIGH"
        elif score >= 55:
            signal_data["confidence"] = "MEDIUM"
            signal_data["priority"] = "MEDIUM"
        else:
            signal_data["confidence"] = "LOW"
            signal_data["priority"] = "LOW"

        logger.info(f"📊 Scored: {signal_data.get('ticker')} = {score} ({bias_alignment})")
        return signal_data

    except Exception as e:
        logger.warning(f"Scoring failed: {e}")
        signal_data["score"] = 50
        signal_data["bias_alignment"] = "NEUTRAL"
        signal_data["confidence"] = "MEDIUM"
        return signal_data


async def _check_and_clear_conflicting_signals(signal_data: Dict[str, Any]) -> bool:
    """
    Check if there are active signals for this ticker going the opposite direction.
    If so, dismiss ALL of them (old conflicting + the new incoming signal) with a
    descriptive note for backtesting.

    Returns True if a conflict was detected and signals were cleared.
    Both the old and new signals are fully persisted to PostgreSQL before dismissal,
    so backtesting data is preserved.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    new_direction = (signal_data.get("direction") or "").upper()
    new_signal_id = signal_data.get("signal_id")
    if not ticker or not new_direction or not new_signal_id:
        return False

    bullish = {"LONG", "BUY", "BULLISH"}
    bearish = {"SHORT", "SELL", "BEARISH"}
    new_is_bull = new_direction in bullish
    new_is_bear = new_direction in bearish
    if not new_is_bull and not new_is_bear:
        return False

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # Find active signals for same ticker with opposite direction
            opposite_dirs = list(bearish) if new_is_bull else list(bullish)
            rows = await conn.fetch(
                """
                SELECT signal_id, strategy, direction
                FROM signals
                WHERE UPPER(ticker) = $1
                  AND UPPER(direction) = ANY($2::text[])
                  AND status IN ('ACTIVE', 'PENDING_REVIEW')
                  AND created_at > NOW() - INTERVAL '24 hours'
                """,
                ticker,
                [d.upper() for d in opposite_dirs],
            )

            if not rows:
                return False

            # Build conflict note
            old_strategies = ", ".join(
                f"{r['strategy']}({r['direction']})" for r in rows
            )
            new_strategy = signal_data.get("strategy", "?")
            conflict_note = (
                f"Auto-dismissed: conflicting signals on {ticker}. "
                f"New {new_strategy}({new_direction}) vs active {old_strategies}. "
                f"Both sides logged for backtesting."
            )

            # Dismiss all old conflicting signals
            old_ids = [r["signal_id"] for r in rows]
            await conn.execute(
                """
                UPDATE signals
                SET status = 'DISMISSED',
                    notes = COALESCE(notes, '') || $1
                WHERE signal_id = ANY($2::text[])
                """,
                f" | {conflict_note}",
                old_ids,
            )

            # Dismiss the new signal too
            await conn.execute(
                """
                UPDATE signals
                SET status = 'DISMISSED',
                    notes = COALESCE(notes, '') || $1
                WHERE signal_id = $2
                """,
                f" | {conflict_note}",
                new_signal_id,
            )

            # Clear Redis cache for dismissed signals
            try:
                from database.redis_client import get_redis_client
                redis = await get_redis_client()
                if redis:
                    for sid in old_ids:
                        await redis.delete(f"signal:{sid}")
                    await redis.delete(f"signal:{new_signal_id}")
            except Exception:
                pass  # Redis cleanup is best-effort

            signal_data["status"] = "DISMISSED"
            signal_data["conflict_note"] = conflict_note
            logger.info(
                f"⚔️ Conflict cleared: {ticker} — dismissed {len(old_ids)} old + 1 new signal. "
                f"{conflict_note}"
            )
            return True

    except Exception as e:
        logger.warning(f"Conflict check failed for {ticker}: {e}")
        return False


async def _maybe_tag_position_signal(signal_data: Dict[str, Any]) -> None:
    """
    If the signal's ticker has an open position, store it in Redis as either
    confirming_signal:{TICKER} or counter_signal:{TICKER} based on direction
    alignment.  Non-blocking — failures here never break the pipeline.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT direction FROM unified_positions
                WHERE UPPER(ticker) = $1 AND status = 'OPEN'
                LIMIT 1
                """,
                ticker,
            )
        if not row:
            return  # No open position for this ticker

        pos_direction = (row["direction"] or "").upper()
        sig_direction = (signal_data.get("direction") or "").upper()

        bullish = {"LONG", "BUY", "BULLISH"}
        bearish = {"SHORT", "SELL", "BEARISH"}
        aligned = (
            (pos_direction in bullish and sig_direction in bullish) or
            (pos_direction in bearish and sig_direction in bearish)
        )

        import json as _json
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return

        payload = _json.dumps({
            "signal_id": signal_data.get("signal_id"),
            "ticker": ticker,
            "strategy": signal_data.get("strategy"),
            "direction": sig_direction,
            "score": signal_data.get("score_v2") or signal_data.get("score"),
            "timestamp": signal_data.get("timestamp") or datetime.utcnow().isoformat(),
        })

        if aligned:
            await redis.set(f"confirming_signal:{ticker}", payload, ex=14400)  # 4h TTL
            logger.info(f"✅ Confirming signal tagged: {ticker} {sig_direction}")
        else:
            await redis.set(f"counter_signal:{ticker}", payload, ex=14400)  # 4h TTL
            logger.info(f"⚠️ Counter signal tagged: {ticker} {sig_direction}")

    except Exception as e:
        logger.warning(f"Position signal tagging error for {ticker}: {e}")


async def process_signal_unified(
    signal_data: Dict[str, Any],
    source: str = "tradingview",
    skip_scoring: bool = False,
    cache_ttl: int = 3600,
    priority_threshold: float = 75.0,
) -> Dict[str, Any]:
    """
    Unified signal processing pipeline. Every signal source calls this
    after normalizing its payload into the standard signal_data dict.

    Pipeline steps:
    1. Set source and lifecycle fields
    2. Attach bias snapshot
    3. Score signal (unless skip_scoring=True, e.g. for Scout alerts)
    4. Persist to PostgreSQL (signals table + signal_outcomes table)
    5. Cache in Redis
    6. Broadcast via WebSocket
    7. Return enriched signal_data

    Args:
        signal_data: Normalized signal dict (must have signal_id, ticker, direction, etc.)
        source: Signal origin ('tradingview', 'whale', 'cta_scanner', 'manual')
        skip_scoring: True for signals that handle their own scoring (Scout alerts)
        cache_ttl: Redis cache TTL in seconds (default 1 hour)
        priority_threshold: Min score for priority WebSocket broadcast

    Returns:
        Enriched signal_data dict with score, bias, status, etc.
    """
    start = datetime.utcnow()

    # 1. Set lifecycle fields
    signal_data["source"] = source
    signal_data["status"] = signal_data.get("status", "ACTIVE")
    signal_data["expires_at"] = signal_data.get("expires_at") or calculate_expiry(signal_data)

    # 2. Attach bias snapshot
    if not signal_data.get("bias_at_signal"):
        try:
            signal_data["bias_at_signal"] = await get_bias_snapshot()
        except Exception as err:
            logger.warning(f"Bias snapshot failed: {err}")

    # 3. Score signal
    if not skip_scoring:
        signal_data = await apply_scoring(signal_data)

    # 3a. Classify feed tier (ZEUS Phase 2)
    try:
        from scoring.feed_tier_classifier import classify_signal_tier
        signal_data["feed_tier"] = classify_signal_tier(
            signal_data, float(signal_data.get("score") or 0)
        )
        logger.debug("Feed tier: %s → %s", signal_data.get("ticker"), signal_data["feed_tier"])
    except Exception as _ft_err:
        logger.warning("Feed tier classification failed: %s", _ft_err)
        signal_data.setdefault("feed_tier", "research_log")

    # 3b. Bail out if countertrend was rejected by bias gate
    if signal_data.get("countertrend_rejected"):
        signal_data["status"] = "REJECTED"
        logger.info(
            f"Pipeline bail-out: {signal_data.get('ticker')} countertrend rejected — not persisting"
        )
        return signal_data

    # 3c. Lightning card dedup — if an active lightning card exists for this ticker,
    #     merge the signal as a confirmation instead of creating a separate card
    try:
        from api.hydra import check_lightning_card_match, add_lightning_confirmation
        lc_match = await check_lightning_card_match(signal_data.get("ticker", ""))
        if lc_match:
            await add_lightning_confirmation(lc_match, signal_data)
            logger.info(
                "Lightning dedup: %s signal merged into card %s",
                signal_data.get("ticker"), lc_match,
            )
            # Still persist the signal for history, but mark it as merged
            signal_data["lightning_merged"] = True
    except Exception as e:
        logger.debug("Lightning dedup check skipped: %s", e)

    # 4. Persist to PostgreSQL
    try:
        await log_signal(signal_data)
    except Exception as e:
        logger.error(f"Failed to log signal: {e}")

    # Write PENDING outcome record for accuracy tracking
    try:
        await write_signal_outcome(signal_data)
    except Exception as e:
        logger.warning(f"Failed to write signal outcome: {e}")

    # Update score in DB (log_signal may have written without score if scoring was async)
    if signal_data.get("score") and signal_data.get("signal_id"):
        try:
            await update_signal_with_score(
                signal_data["signal_id"],
                signal_data["score"],
                signal_data.get("bias_alignment", "NEUTRAL"),
                signal_data.get("triggering_factors", {}),
            )
        except Exception as e:
            logger.warning(f"Failed to update score in DB: {e}")

    # 4b. Calculate R:R if entry, stop, and target are available (H9)
    entry = signal_data.get("entry_price") or signal_data.get("entry")
    stop = signal_data.get("stop_loss") or signal_data.get("stop")
    target = signal_data.get("target_price") or signal_data.get("target") or signal_data.get("tp1")
    if entry and stop and target:
        try:
            risk = abs(float(entry) - float(stop))
            reward = abs(float(target) - float(entry))
            if risk > 0:
                signal_data["risk_reward"] = round(reward / risk, 2)
                signal_data["risk_reward_display"] = f"{signal_data['risk_reward']}:1"
            else:
                signal_data["risk_reward"] = None
        except (ValueError, TypeError):
            signal_data["risk_reward"] = None
    else:
        signal_data["risk_reward"] = signal_data.get("risk_reward")

    # 4c. Enrich signal with market context data
    try:
        from enrichment.signal_enricher import enrich_signal, persist_enrichment
        signal_data = await enrich_signal(signal_data)
        # Persist enrichment to DB (non-blocking — don't fail the pipeline)
        if signal_data.get("enrichment_data"):
            await persist_enrichment(signal_data["signal_id"], signal_data["enrichment_data"])
    except Exception as e:
        logger.warning(f"Enrichment failed (signal still processed): {e}")

    # 4d. Compute score v2 (full score with enrichment data)
    try:
        from scoring.score_v2 import compute_score_v2, persist_score_v2
        score_v2, v2_factors = compute_score_v2(signal_data)
        if score_v2 is not None:
            signal_data["score_v2"] = score_v2
            signal_data["score_v2_factors"] = v2_factors
            await persist_score_v2(signal_data["signal_id"], score_v2, v2_factors)
    except Exception as e:
        logger.warning(f"Score v2 computation failed (flash score still valid): {e}")

    # 4e. Contextual confidence modifier (Phase 4) — fire-and-forget
    try:
        import asyncio as _asyncio
        from enrichment.context_modifier import enrich_trade_idea
        _base = signal_data.get("score") or signal_data.get("score_v2") or 50
        _dir = signal_data.get("direction", "bearish").lower()
        if _dir not in ("bullish", "bearish"):
            _dir = "bearish" if _dir in ("short", "sell", "put") else "bullish"
        _asyncio.ensure_future(enrich_trade_idea(
            signal_id=signal_data["signal_id"],
            ticker=signal_data.get("ticker", ""),
            direction=_dir,
            base_score=int(float(_base)),
        ))
    except Exception as e:
        logger.warning(f"Context modifier launch failed (signal still processed): {e}")

    # 4f. Check for conflicting signals (opposite direction, same ticker)
    #     Both old + new are already in PostgreSQL with full scores/enrichment.
    #     If conflict detected, short-circuit — no broadcast, no committee, no Insight.
    try:
        conflict = await _check_and_clear_conflicting_signals(signal_data)
        if conflict:
            elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000
            logger.info(
                f"⚔️ Pipeline short-circuit: {signal_data.get('ticker')} conflicting signals "
                f"dismissed in {elapsed_ms:.1f}ms"
            )
            return signal_data
    except Exception as e:
        logger.warning(f"Conflict check error (continuing pipeline): {e}")

    # 5. Cache in Redis
    try:
        await cache_signal(signal_data["signal_id"], signal_data, ttl=cache_ttl)
    except Exception as e:
        logger.warning(f"Failed to cache signal: {e}")

    # 6. Broadcast via WebSocket
    try:
        await manager.broadcast_signal_smart(signal_data, priority_threshold=priority_threshold)
    except Exception as e:
        logger.warning(f"Failed to broadcast signal: {e}")

    # 6b. Tag position-linked signals (confirming / counter) in Redis
    try:
        await _maybe_tag_position_signal(signal_data)
    except Exception as e:
        logger.warning(f"Position signal tagging failed: {e}")

    # 7. Flag for committee review if score warrants it
    try:
        await _maybe_flag_for_committee(signal_data)
    except Exception as e:
        logger.warning(f"Committee flagging failed: {e}")

    elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000
    logger.info(
        f"✅ Pipeline complete: {signal_data.get('ticker')} "
        f"({source}, score={signal_data.get('score')}) in {elapsed_ms:.1f}ms"
    )

    return signal_data
