"""
Unusual Whales Integration API
Receives parsed data from Pandora Bridge Discord bot

Endpoints:
- POST /bias/uw/market_tide - Receive market tide data for Daily Bias
- POST /bias/uw/sectorflow - Receive sector flow data for Weekly Bias  
- GET /bias/uw/latest - Get latest UW data
- GET /bias/uw/status - Check UW integration status
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bias/uw", tags=["Unusual Whales"])

# ================================
# DATA MODELS
# ================================

class MarketTideData(BaseModel):
    """Market Tide data from UW"""
    source: str = "uw_market_tide"
    sentiment: str  # BULLISH, BEARISH, NEUTRAL, STRONGLY_BULLISH, STRONGLY_BEARISH
    bullish_pct: Optional[float] = None
    bearish_pct: Optional[float] = None
    call_premium: Optional[int] = None
    put_premium: Optional[int] = None
    timestamp: Optional[str] = None


class SectorFlowData(BaseModel):
    """Sector Flow data from UW"""
    source: str = "uw_sectorflow"
    sectors: Dict[str, str] = {}  # {XLK: "BULLISH", XLF: "BEARISH", ...}
    bullish_sectors: List[str] = []
    bearish_sectors: List[str] = []
    timestamp: Optional[str] = None


class EconomicCalendarData(BaseModel):
    """Economic Calendar data from UW"""
    source: str = "uw_economic_calendar"
    events: List[Dict[str, Any]] = []
    high_impact_today: bool = False
    timestamp: Optional[str] = None


class HighestVolumeContract(BaseModel):
    """Single contract in highest volume table."""
    ticker: str
    strike: Optional[float] = None
    option_type: Optional[str] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    premium_pct: Optional[float] = None
    dte: Optional[str] = None
    contract: Optional[str] = None

    model_config = {"extra": "allow"}


class HighestVolumeData(BaseModel):
    """Highest Volume Contracts data from UW."""
    data_type: Optional[str] = "highest_volume_contracts"
    contracts: List[HighestVolumeContract] = []
    total_calls: Optional[int] = None
    total_puts: Optional[int] = None
    sentiment: Optional[str] = None
    timestamp: Optional[str] = None
    source: Optional[str] = None

    model_config = {"extra": "allow"}


class FlowAlertsData(BaseModel):
    """Flow alert batch from UW vision."""
    data_type: Optional[str] = "flow_alerts"
    alerts: List[Dict[str, Any]] = []
    dominant_sentiment: Optional[str] = None
    timestamp: Optional[str] = None
    source: Optional[str] = None

    model_config = {"extra": "allow"}


# ================================
# IN-MEMORY STORAGE
# ================================

# Store latest UW data (will persist until server restart)
# In production, you'd want to store this in Redis
_uw_data = {
    "market_tide": None,
    "sectorflow": None,
    "economic_calendar": None,
    "highest_volume": None,
    "flow_alerts": None,
    "generic": None,
    "last_updated": None
}


def get_uw_data() -> Dict[str, Any]:
    """Get all stored UW data"""
    return _uw_data.copy()


def get_market_tide_sentiment() -> Optional[str]:
    """Get current market tide sentiment for Daily Bias calculation"""
    if _uw_data["market_tide"]:
        return _uw_data["market_tide"].get("sentiment")
    return None


def get_sector_rotation_signal() -> Dict[str, Any]:
    """Get sector flow signal for Weekly Bias calculation"""
    if _uw_data["sectorflow"]:
        data = _uw_data["sectorflow"]
        bullish_count = len(data.get("bullish_sectors", []))
        bearish_count = len(data.get("bearish_sectors", []))
        
        # Determine overall sector sentiment
        if bullish_count > bearish_count + 2:
            signal = "BULLISH"
        elif bearish_count > bullish_count + 2:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"
        
        return {
            "signal": signal,
            "bullish_sectors": data.get("bullish_sectors", []),
            "bearish_sectors": data.get("bearish_sectors", []),
            "bullish_count": bullish_count,
            "bearish_count": bearish_count
        }
    
    return {"signal": "UNKNOWN", "bullish_sectors": [], "bearish_sectors": []}


def has_high_impact_event() -> bool:
    """Check if there's a high impact economic event today"""
    if _uw_data["economic_calendar"]:
        return _uw_data["economic_calendar"].get("high_impact_today", False)
    return False


# ================================
# API ENDPOINTS
# ================================

@router.post("/market_tide")
async def receive_market_tide(data: MarketTideData):
    """
    Receive market tide data from Pandora Bridge
    
    This updates the Daily Bias with UW market sentiment.
    """
    try:
        _uw_data["market_tide"] = {
            "sentiment": data.sentiment,
            "bullish_pct": data.bullish_pct,
            "bearish_pct": data.bearish_pct,
            "call_premium": data.call_premium,
            "put_premium": data.put_premium,
            "timestamp": data.timestamp or datetime.now().isoformat(),
            "received_at": datetime.now().isoformat()
        }
        _uw_data["last_updated"] = datetime.now().isoformat()
        
        logger.info(f"📊 Market Tide updated: {data.sentiment}")
        
        # Calculate bias contribution
        bias_contribution = "NEUTRAL"
        if data.sentiment in ["BULLISH", "STRONGLY_BULLISH"]:
            bias_contribution = "TORO"
        elif data.sentiment in ["BEARISH", "STRONGLY_BEARISH"]:
            bias_contribution = "URSA"
        
        return {
            "status": "success",
            "message": f"Market Tide received: {data.sentiment}",
            "bias_contribution": bias_contribution,
            "data": _uw_data["market_tide"]
        }
        
    except Exception as e:
        logger.error(f"Error processing market tide: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sectorflow")
async def receive_sectorflow(data: SectorFlowData):
    """
    Receive sector flow data from Pandora Bridge
    
    This updates the Weekly Bias with sector rotation signals.
    """
    try:
        _uw_data["sectorflow"] = {
            "sectors": data.sectors,
            "bullish_sectors": data.bullish_sectors,
            "bearish_sectors": data.bearish_sectors,
            "timestamp": data.timestamp or datetime.now().isoformat(),
            "received_at": datetime.now().isoformat()
        }
        _uw_data["last_updated"] = datetime.now().isoformat()
        
        logger.info(f"📈 Sector Flow updated: {len(data.bullish_sectors)} bullish, {len(data.bearish_sectors)} bearish")
        
        # Calculate sector rotation signal
        rotation_signal = get_sector_rotation_signal()
        
        return {
            "status": "success",
            "message": f"Sector Flow received: {len(data.sectors)} sectors",
            "rotation_signal": rotation_signal["signal"],
            "data": _uw_data["sectorflow"]
        }
        
    except Exception as e:
        logger.error(f"Error processing sector flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/economic_calendar")
async def receive_economic_calendar(data: EconomicCalendarData):
    """
    Receive economic calendar data from Pandora Bridge
    
    This updates the Black Swan alerts with event awareness.
    """
    try:
        _uw_data["economic_calendar"] = {
            "events": data.events,
            "high_impact_today": data.high_impact_today,
            "timestamp": data.timestamp or datetime.now().isoformat(),
            "received_at": datetime.now().isoformat()
        }
        _uw_data["last_updated"] = datetime.now().isoformat()
        
        logger.info(f"📅 Economic Calendar updated: {len(data.events)} events, high_impact={data.high_impact_today}")
        
        return {
            "status": "success",
            "message": f"Economic Calendar received: {len(data.events)} events",
            "high_impact_today": data.high_impact_today,
            "data": _uw_data["economic_calendar"]
        }
        
    except Exception as e:
        logger.error(f"Error processing economic calendar: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/highest_volume")
async def receive_highest_volume(data: HighestVolumeData):
    """
    Receive highest volume contracts data from Pandora Bridge.
    """
    try:
        contracts = [c.model_dump() for c in data.contracts]
        _uw_data["highest_volume"] = {
            "contracts": contracts,
            "total_calls": data.total_calls,
            "total_puts": data.total_puts,
            "sentiment": data.sentiment,
            "timestamp": data.timestamp or datetime.now().isoformat(),
            "received_at": datetime.now().isoformat()
        }
        _uw_data["last_updated"] = datetime.now().isoformat()

        # Store in UW module for downstream use
        from bias_filters.unusual_whales import process_highest_volume
        await process_highest_volume(contracts, data.total_calls, data.total_puts)

        logger.info(f"📊 Highest Volume updated: {len(contracts)} contracts")

        return {
            "status": "success",
            "message": f"Highest Volume received: {len(contracts)} contracts",
            "contracts_parsed": len(contracts),
            "data": _uw_data["highest_volume"]
        }
    except Exception as e:
        logger.error(f"Error processing highest volume: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flow_alerts")
async def receive_flow_alerts(data: FlowAlertsData):
    """
    Receive flow alerts extracted via vision.
    """
    try:
        _uw_data["flow_alerts"] = {
            "alerts": data.alerts,
            "dominant_sentiment": data.dominant_sentiment,
            "timestamp": data.timestamp or datetime.now().isoformat(),
            "received_at": datetime.now().isoformat()
        }
        _uw_data["last_updated"] = datetime.now().isoformat()

        logger.info(f"🐋 Flow alerts updated: {len(data.alerts)} alerts")

        return {
            "status": "success",
            "message": f"Flow alerts received: {len(data.alerts)} alerts",
            "data": _uw_data["flow_alerts"]
        }
    except Exception as e:
        logger.error(f"Error processing flow alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generic")
async def receive_generic(payload: Dict[str, Any]):
    """
    Receive generic UW vision payloads not mapped to a dedicated endpoint.
    """
    try:
        _uw_data["generic"] = {
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
        _uw_data["last_updated"] = datetime.now().isoformat()

        return {
            "status": "success",
            "message": "Generic payload received",
            "data": _uw_data["generic"]
        }
    except Exception as e:
        logger.error(f"Error processing generic payload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_uw_data():
    """
    Get all latest UW data
    
    Returns market tide, sector flow, and economic calendar data.
    """
    return {
        "status": "success",
        "last_updated": _uw_data["last_updated"],
        "market_tide": _uw_data["market_tide"],
        "sectorflow": _uw_data["sectorflow"],
        "economic_calendar": _uw_data["economic_calendar"],
        "highest_volume": _uw_data["highest_volume"],
        "flow_alerts": _uw_data["flow_alerts"],
        "generic": _uw_data["generic"]
    }


@router.get("/status")
async def get_uw_status():
    """
    Check UW integration status
    
    Returns whether each data source has recent data.
    """
    now = datetime.now()
    
    def is_stale(timestamp_str: Optional[str], max_age_hours: int = 24) -> bool:
        """Check if data is stale (older than max_age_hours)"""
        if not timestamp_str:
            return True
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            # Remove timezone for comparison if needed
            if timestamp.tzinfo:
                timestamp = timestamp.replace(tzinfo=None)
            age = (now - timestamp).total_seconds() / 3600
            return age > max_age_hours
        except:
            return True
    
    market_tide_ts = _uw_data["market_tide"].get("received_at") if _uw_data["market_tide"] else None
    sectorflow_ts = _uw_data["sectorflow"].get("received_at") if _uw_data["sectorflow"] else None
    calendar_ts = _uw_data["economic_calendar"].get("received_at") if _uw_data["economic_calendar"] else None
    highest_volume_ts = _uw_data["highest_volume"].get("received_at") if _uw_data["highest_volume"] else None
    flow_alerts_ts = _uw_data["flow_alerts"].get("received_at") if _uw_data["flow_alerts"] else None
    
    return {
        "status": "success",
        "integration_active": _uw_data["last_updated"] is not None,
        "last_updated": _uw_data["last_updated"],
        "data_sources": {
            "market_tide": {
                "has_data": _uw_data["market_tide"] is not None,
                "last_received": market_tide_ts,
                "is_stale": is_stale(market_tide_ts, max_age_hours=4),  # Market tide should refresh every few hours
                "current_sentiment": get_market_tide_sentiment()
            },
            "sectorflow": {
                "has_data": _uw_data["sectorflow"] is not None,
                "last_received": sectorflow_ts,
                "is_stale": is_stale(sectorflow_ts, max_age_hours=168),  # Sector flow refreshes weekly
                "current_signal": get_sector_rotation_signal()["signal"]
            },
            "economic_calendar": {
                "has_data": _uw_data["economic_calendar"] is not None,
                "last_received": calendar_ts,
                "is_stale": is_stale(calendar_ts, max_age_hours=24),  # Calendar refreshes daily
                "high_impact_today": has_high_impact_event()
            },
            "highest_volume": {
                "has_data": _uw_data["highest_volume"] is not None,
                "last_received": highest_volume_ts,
                "is_stale": is_stale(highest_volume_ts, max_age_hours=24)
            },
            "flow_alerts": {
                "has_data": _uw_data["flow_alerts"] is not None,
                "last_received": flow_alerts_ts,
                "is_stale": is_stale(flow_alerts_ts, max_age_hours=6)
            }
        }
    }


@router.get("/bias_contribution")
async def get_bias_contribution():
    """
    Get UW contribution to bias calculations
    
    Returns how UW data should influence Daily and Weekly bias.
    """
    # Market Tide → Daily Bias
    market_tide_contribution = {
        "factor": "uw_market_tide",
        "applies_to": "DAILY",
        "signal": "NEUTRAL",
        "vote": 0,
        "confidence": "NONE"
    }
    
    if _uw_data["market_tide"]:
        sentiment = _uw_data["market_tide"].get("sentiment", "NEUTRAL")
        if sentiment in ["STRONGLY_BULLISH"]:
            market_tide_contribution["signal"] = "TORO"
            market_tide_contribution["vote"] = 2
            market_tide_contribution["confidence"] = "HIGH"
        elif sentiment == "BULLISH":
            market_tide_contribution["signal"] = "TORO"
            market_tide_contribution["vote"] = 1
            market_tide_contribution["confidence"] = "MEDIUM"
        elif sentiment in ["STRONGLY_BEARISH"]:
            market_tide_contribution["signal"] = "URSA"
            market_tide_contribution["vote"] = -2
            market_tide_contribution["confidence"] = "HIGH"
        elif sentiment == "BEARISH":
            market_tide_contribution["signal"] = "URSA"
            market_tide_contribution["vote"] = -1
            market_tide_contribution["confidence"] = "MEDIUM"
    
    # Sector Flow → Weekly Bias
    sector_flow_contribution = {
        "factor": "uw_sectorflow",
        "applies_to": "WEEKLY",
        "signal": "NEUTRAL",
        "vote": 0,
        "confidence": "NONE"
    }
    
    rotation = get_sector_rotation_signal()
    if rotation["signal"] == "BULLISH":
        sector_flow_contribution["signal"] = "TORO"
        sector_flow_contribution["vote"] = 1
        sector_flow_contribution["confidence"] = "MEDIUM"
    elif rotation["signal"] == "BEARISH":
        sector_flow_contribution["signal"] = "URSA"
        sector_flow_contribution["vote"] = -1
        sector_flow_contribution["confidence"] = "MEDIUM"
    
    return {
        "status": "success",
        "contributions": {
            "daily": market_tide_contribution,
            "weekly": sector_flow_contribution
        },
        "high_impact_event_warning": has_high_impact_event()
    }
