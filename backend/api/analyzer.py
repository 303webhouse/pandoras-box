"""
Unified Single-Ticker Analyzer.
Runs CTA + trapped trader + TradingView + fundamentals in one call.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, Query
from utils.pivot_auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


async def _fetch_history(ticker: str):
    import yfinance as yf

    def _sync_fetch():
        stock = yf.Ticker(ticker)
        return stock.history(period="1y")

    return await asyncio.to_thread(_sync_fetch)


async def _fetch_tv_and_fundamentals(ticker: str, interval: str):
    def _sync_fetch():
        from scanners.hybrid_scanner import get_scanner

        scanner = get_scanner()
        tech = scanner.get_technical_analysis(ticker, interval)
        fund = scanner.get_fundamental_analysis(ticker)
        return tech, fund

    return await asyncio.to_thread(_sync_fetch)


@router.get("/analyze/{ticker}")
async def analyze_ticker(
    ticker: str,
    interval: str = Query("1d", description="TradingView technical analysis timeframe"),
):
    """
    Comprehensive single-ticker analysis combining all scanner engines.
    Returns CTA zones, CTA signals, trapped trader breakdown, TradingView technicals,
    analyst fundamentals, and a unified recommendation.
    """
    ticker = ticker.upper().strip()

    result: Dict[str, Any] = {
        "ticker": ticker,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "cta": {},
        "trapped_traders": {},
        "technicals": {},
        "fundamentals": {},
        "combined": {},
    }

    df = None
    try:
        from scanners.cta_scanner import calculate_cta_indicators

        df = await _fetch_history(ticker)
        if df is not None and not df.empty:
            df = calculate_cta_indicators(df)
    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")

    try:
        from scanners.cta_scanner import analyze_ticker_cta_from_df

        if df is not None and not df.empty:
            result["cta"] = await analyze_ticker_cta_from_df(ticker, df)
        else:
            result["cta"] = {"error": "No data available"}
    except Exception as e:
        result["cta"] = {"error": str(e)}

    try:
        from scanners.cta_scanner import get_trapped_trader_breakdown_from_df

        if df is not None and not df.empty:
            result["trapped_traders"] = get_trapped_trader_breakdown_from_df(ticker, df)
        else:
            result["trapped_traders"] = {"verdict": "NO_DATA"}
    except Exception as e:
        result["trapped_traders"] = {"error": str(e)}

    try:
        tech, fund = await asyncio.wait_for(
            _fetch_tv_and_fundamentals(ticker, interval),
            timeout=10.0,
        )
        result["technicals"] = {
            "signal": tech.get("signal") if isinstance(tech, dict) else None,
            "score": tech.get("signal_score") if isinstance(tech, dict) else None,
            "oscillators": tech.get("oscillators") if isinstance(tech, dict) else None,
            "moving_averages": tech.get("moving_averages") if isinstance(tech, dict) else None,
            "price": tech.get("price") if isinstance(tech, dict) else None,
        }
        result["fundamentals"] = {
            "analyst": fund.get("analyst") if isinstance(fund, dict) else None,
            "price_target": fund.get("price_target") if isinstance(fund, dict) else None,
            "metadata": fund.get("metadata") if isinstance(fund, dict) else None,
        }
    except asyncio.TimeoutError:
        result["technicals"] = {"error": "timeout"}
        result["fundamentals"] = {"error": "timeout"}
    except Exception as e:
        result["technicals"] = {"error": str(e)}
        result["fundamentals"] = {"error": str(e)}

    result["combined"] = _build_combined_recommendation(result)

    return {"status": "success", "analysis": result}


def _build_combined_recommendation(analysis: Dict[str, Any]) -> Dict[str, Any]:
    cta = analysis.get("cta", {}) or {}
    trapped = analysis.get("trapped_traders", {}) or {}
    tech = analysis.get("technicals", {}) or {}
    fund = analysis.get("fundamentals", {}) or {}

    cta_signals = cta.get("signals", [])
    if cta_signals:
        best = max(cta_signals, key=lambda s: s.get("priority", 0))
        return {
            "action": best.get("direction", "LONG"),
            "source": "CTA Scanner",
            "signal_type": best.get("signal_type"),
            "entry": best.get("setup", {}).get("entry"),
            "stop": best.get("setup", {}).get("stop"),
            "target": best.get("setup", {}).get("t2"),
            "confidence": best.get("confidence"),
            "note": best.get("description"),
        }

    trapped_verdict = trapped.get("verdict", "NO_SIGNAL")
    if trapped_verdict == "TRAPPED_LONGS":
        return {
            "action": "SHORT",
            "source": "Trapped Trader Detection",
            "signal_type": "TRAPPED_LONGS",
            "confidence": "MEDIUM",
            "note": "Trapped longs — price below 200 SMA and VWAP with institutional volume",
        }
    if trapped_verdict == "TRAPPED_SHORTS":
        return {
            "action": "LONG",
            "source": "Trapped Trader Detection",
            "signal_type": "TRAPPED_SHORTS",
            "confidence": "MEDIUM",
            "note": "Trapped shorts — price above 200 SMA and VWAP with institutional volume",
        }

    tv_signal = tech.get("signal", "NEUTRAL")
    price_target = fund.get("price_target") if isinstance(fund, dict) else None
    analyst_upside = price_target.get("upside_pct") if isinstance(price_target, dict) else None
    cta_zone = cta.get("cta_analysis", {}).get("cta_zone", "UNKNOWN")
    cta_rec = cta.get("recommendation", {})

    return {
        "action": cta_rec.get("action", "MONITOR"),
        "source": "Combined Analysis",
        "signal_type": None,
        "confidence": "LOW",
        "tv_signal": tv_signal,
        "analyst_upside_pct": analyst_upside,
        "cta_zone": cta_zone,
        "note": cta_rec.get("note", "No actionable setup. Continue monitoring."),
    }


@router.get("/signals/hit-rates")
async def get_signal_hit_rates():
    """Return historical hit rates by signal type and zone."""
    from jobs.score_signals import get_hit_rates

    rates = await get_hit_rates()
    return {"status": "success", "hit_rates": rates}


@router.get("/analyze/{ticker}/signals")
async def get_ticker_signals(ticker: str, days: int = Query(14, ge=1, le=90)):
    """Recent signals for a specific ticker from the signals table."""
    from database.postgres_client import get_postgres_client

    ticker = ticker.upper().strip()
    signals = []
    try:
        pool = await get_postgres_client()
        if pool:
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT signal_id, strategy, direction, score, score_v2,
                           signal_type, signal_category, status, created_at, metadata
                    FROM signals
                    WHERE ticker = $1
                      AND created_at > NOW() - INTERVAL '1 day' * $2
                    ORDER BY created_at DESC
                    LIMIT 20
                """, ticker, days)
                for row in rows:
                    signals.append({
                        "signal_id": row["signal_id"],
                        "strategy": row.get("strategy"),
                        "direction": row.get("direction"),
                        "score": row.get("score"),
                        "signal_category": row.get("signal_category"),
                        "status": row.get("status"),
                        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    })
    except Exception as e:
        logger.warning("Ticker signals query failed for %s: %s", ticker, e)

    return {"ticker": ticker, "signals": signals, "count": len(signals), "days": days}


@router.post("/analyze/{ticker}/olympus")
async def run_olympus_analysis(ticker: str, _=Depends(require_api_key)):
    """
    On-demand 4-agent committee analysis for a single ticker.
    Rate limited: 1 per ticker per 5 minutes. Results cached 30 min.
    Requires API key auth.
    """
    import json
    import os
    from fastapi import HTTPException as HTTPErr
    from database.redis_client import get_redis_client

    ticker = ticker.upper().strip()
    redis = await get_redis_client()

    # Check cache first
    cache_key = f"olympus:{ticker}:result"
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                result = json.loads(cached)
                result["cached"] = True
                return result
        except Exception:
            pass

    # Rate limit check
    rate_key = f"olympus:{ticker}:last_run"
    if redis:
        try:
            last_run = await redis.get(rate_key)
            if last_run:
                raise HTTPErr(status_code=429, detail="Rate limited — try again in a few minutes")
        except HTTPErr:
            raise
        except Exception:
            pass

    # Run analysis
    try:
        analysis_data = await _run_olympus_agents(ticker)
    except Exception as e:
        logger.error("Olympus analysis failed for %s: %s", ticker, e)
        return {"error": str(e), "ticker": ticker}

    result = {
        "ticker": ticker,
        "olympus": analysis_data,
        "cached": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache result and set rate limit
    if redis:
        try:
            await redis.set(cache_key, json.dumps(result), ex=1800)  # 30 min
            await redis.set(rate_key, "1", ex=300)  # 5 min
        except Exception:
            pass

    return result


async def _run_olympus_agents(ticker: str) -> dict:
    """Run 4-agent committee analysis using Anthropic API directly."""
    import os
    import httpx

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "toro": {"conviction": "N/A", "summary": "Anthropic API key not configured"},
            "ursa": {"conviction": "N/A", "summary": "Anthropic API key not configured"},
            "risk": {"entry": "-", "stop": "-", "target": "-", "size": "-"},
            "pivot": {"action": "PASS", "conviction": "N/A", "synthesis": "API key not configured"},
        }

    # Get context for the ticker
    context = ""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            bias_data = await redis.get("bias:composite:latest")
            if bias_data:
                import json
                bd = json.loads(bias_data)
                context += f"Current Market Bias: {bd.get('level', 'NEUTRAL')} (score: {bd.get('score', 0):.2f})\n"
    except Exception:
        pass

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async def call_agent(role: str, system_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={
                    "model": "claude-haiku-4-5-20251001" if role != "pivot" else "claude-sonnet-4-6",
                    "max_tokens": 300,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": f"Analyze {ticker} for a potential options swing trade.\n\n{context}"}],
                },
            )
            data = resp.json()
            return data.get("content", [{}])[0].get("text", "No response")

    toro_prompt = "You are TORO, a bullish analyst. Evaluate the bull case for this ticker. Respond with conviction level (HIGH/MEDIUM/LOW) on the first line, then a 2-3 sentence summary."
    ursa_prompt = "You are URSA, a bearish analyst. Evaluate the bear case and risks for this ticker. Respond with conviction level (HIGH/MEDIUM/LOW) on the first line, then a 2-3 sentence summary."
    risk_prompt = "You are a risk manager for options swing trades. For this ticker, provide: Entry price range, Stop loss level, Target price, and Position size recommendation (as % of portfolio). Format each on its own line starting with 'Entry:', 'Stop:', 'Target:', 'Size:'."
    pivot_prompt = "You are Pivot, the lead analyst synthesizing bull, bear, and risk views. Decide: TAKE, PASS, or WATCHING. Respond with action on line 1, conviction (HIGH/MEDIUM/LOW) on line 2, then a 2-3 sentence synthesis. If PASS or WATCHING, note what would change your mind (invalidation)."

    try:
        toro_text, ursa_text, risk_text, pivot_text = await asyncio.gather(
            call_agent("toro", toro_prompt),
            call_agent("ursa", ursa_prompt),
            call_agent("risk", risk_prompt),
            call_agent("pivot", pivot_prompt),
        )
    except Exception as e:
        logger.error("Olympus agent calls failed: %s", e)
        return {
            "toro": {"conviction": "ERROR", "summary": str(e)},
            "ursa": {"conviction": "ERROR", "summary": str(e)},
            "risk": {"entry": "-", "stop": "-", "target": "-", "size": "-"},
            "pivot": {"action": "PASS", "conviction": "ERROR", "synthesis": str(e)},
        }

    def parse_conviction_summary(text):
        lines = text.strip().split("\n", 1)
        conviction = lines[0].strip().upper() if lines else "MEDIUM"
        for level in ("HIGH", "MEDIUM", "LOW"):
            if level in conviction:
                conviction = level
                break
        else:
            conviction = "MEDIUM"
        summary = lines[1].strip() if len(lines) > 1 else text.strip()
        return {"conviction": conviction, "summary": summary}

    def parse_risk(text):
        result = {"entry": "-", "stop": "-", "target": "-", "size": "-"}
        for line in text.split("\n"):
            lower = line.lower().strip()
            if lower.startswith("entry"):
                result["entry"] = line.split(":", 1)[-1].strip()
            elif lower.startswith("stop"):
                result["stop"] = line.split(":", 1)[-1].strip()
            elif lower.startswith("target"):
                result["target"] = line.split(":", 1)[-1].strip()
            elif lower.startswith("size"):
                result["size"] = line.split(":", 1)[-1].strip()
        return result

    def parse_pivot(text):
        lines = text.strip().split("\n")
        action = "WATCHING"
        conviction = "MEDIUM"
        if lines:
            first = lines[0].strip().upper()
            for a in ("TAKE", "PASS", "WATCHING"):
                if a in first:
                    action = a
                    break
        if len(lines) > 1:
            second = lines[1].strip().upper()
            for level in ("HIGH", "MEDIUM", "LOW"):
                if level in second:
                    conviction = level
                    break
        synthesis = "\n".join(lines[2:]).strip() if len(lines) > 2 else text.strip()
        invalidation = None
        for line in lines:
            if "invalidat" in line.lower() or "change" in line.lower():
                invalidation = line.strip()
                break
        return {"action": action, "conviction": conviction, "synthesis": synthesis, "invalidation": invalidation}

    return {
        "toro": parse_conviction_summary(toro_text),
        "ursa": parse_conviction_summary(ursa_text),
        "risk": parse_risk(risk_text),
        "pivot": parse_pivot(pivot_text),
    }
