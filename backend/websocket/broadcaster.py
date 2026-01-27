"""
WebSocket Connection Manager
Handles simultaneous connections from computer, laptop, and phone
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
        # Check for numpy types by checking module and class name
        # This avoids import issues while still handling numpy types
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
    """Manages WebSocket connections and broadcasts signals to all devices"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket"""
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to a specific connection"""
        await websocket.send_text(message)
    
    async def broadcast(self, message: Dict[Any, Any]):
        """
        Broadcast message to all connected devices
        Critical for multi-device sync (computer + laptop + phone)
        """
        # Sanitize message to ensure all numpy types are converted
        sanitized_message = sanitize_for_json(message)
        message_str = json.dumps(sanitized_message)
        
        # Send to all connections simultaneously
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Error sending to connection: {e}")
                disconnected.append(connection)
        
        # Clean up any failed connections
        for connection in disconnected:
            self.disconnect(connection)
    
    async def broadcast_signal(self, signal_data: Dict[Any, Any]):
        """
        Broadcast a new trading signal to all devices
        Optimized for speed - runs in <5ms
        """
        message = {
            "type": "NEW_SIGNAL",
            "data": signal_data
        }
        await self.broadcast(message)
        logger.info(f"Signal broadcast to {len(self.active_connections)} devices")
    
    async def broadcast_bias_update(self, bias_data: Dict[Any, Any]):
        """Broadcast bias indicator changes"""
        message = {
            "type": "BIAS_UPDATE",
            "data": bias_data
        }
        await self.broadcast(message)
    
    async def broadcast_position_update(self, position_data: Dict[Any, Any]):
        """Broadcast open position updates"""
        message = {
            "type": "POSITION_UPDATE",
            "data": position_data
        }
        await self.broadcast(message)
    
    async def broadcast_priority_signal(self, signal_data: Dict[Any, Any]):
        """
        Broadcast a high-priority signal that should jump to the top.
        Used when a new signal scores higher than existing displayed signals.
        """
        message = {
            "type": "SIGNAL_PRIORITY_UPDATE",
            "data": signal_data
        }
        await self.broadcast(message)
        logger.info(f"🔥 Priority signal broadcast: {signal_data.get('ticker', 'UNKNOWN')} (score: {signal_data.get('score', 0)})")
    
    async def broadcast_signal_smart(self, signal_data: Dict[Any, Any], priority_threshold: float = 75.0):
        """
        Smart broadcast - sends priority update if signal scores above threshold.
        Otherwise sends as regular signal.
        """
        score = signal_data.get('score', 0)
        
        if score >= priority_threshold:
            await self.broadcast_priority_signal(signal_data)
        else:
            await self.broadcast_signal(signal_data)

# Global instance
manager = ConnectionManager()
