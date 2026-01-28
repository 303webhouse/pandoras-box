"""
WebSocket Connection Manager for Crypto Scalper
Handles real-time broadcast of trading signals and market data
"""

from fastapi import WebSocket
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


def sanitize_for_json(obj):
    """Convert numpy types to native Python types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    else:
        type_name = type(obj).__module__ + '.' + type(obj).__name__
        if 'numpy' in type_name:
            if 'bool' in type_name.lower():
                return bool(obj)
            elif 'int' in type_name.lower():
                return int(obj)
            elif 'float' in type_name.lower():
                return float(obj)
            elif hasattr(obj, 'tolist'):
                return obj.tolist()
    return obj


class ConnectionManager:
    """Manages WebSocket connections and broadcasts to all connected clients"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.message_count = 0
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to a specific connection"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast(self, message: Dict[Any, Any]):
        """
        Broadcast message to all connected clients
        Used for price updates, signals, etc.
        """
        if not self.active_connections:
            return
        
        self.message_count += 1
        
        # Sanitize message
        sanitized = sanitize_for_json(message)
        message_str = json.dumps(sanitized)
        
        # Send to all connections
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.debug(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)
        
        # Clean up failed connections
        for connection in disconnected:
            self.disconnect(connection)
    
    async def broadcast_signal(self, signal_data: Dict[Any, Any]):
        """Broadcast a new trading signal"""
        message = {
            "type": "NEW_SIGNAL",
            "data": signal_data
        }
        await self.broadcast(message)
        logger.info(f"🚨 Signal broadcast: {signal_data.get('direction', 'UNKNOWN')} @ "
                   f"${signal_data.get('entry', 0):,.2f}")
    
    async def broadcast_price_update(self, price_data: Dict[Any, Any]):
        """Broadcast price update"""
        message = {
            "type": "PRICE_UPDATE",
            "data": price_data
        }
        await self.broadcast(message)
    
    async def broadcast_risk_warning(self, warning_data: Dict[Any, Any]):
        """Broadcast risk management warning"""
        message = {
            "type": "RISK_WARNING",
            "data": warning_data
        }
        await self.broadcast(message)
        logger.warning(f"⚠️ Risk warning broadcast: {warning_data.get('message', 'Unknown')}")
    
    async def broadcast_high_priority_signal(self, signal_data: Dict[Any, Any]):
        """Broadcast a high-priority signal that needs immediate attention"""
        message = {
            "type": "HIGH_PRIORITY_SIGNAL",
            "data": signal_data
        }
        await self.broadcast(message)
        logger.info(f"🔥 HIGH PRIORITY: {signal_data.get('direction', 'UNKNOWN')} "
                   f"{signal_data.get('strategy', 'UNKNOWN')} @ ${signal_data.get('entry', 0):,.2f}")


# Global instance
manager = ConnectionManager()
