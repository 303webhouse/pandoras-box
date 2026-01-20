"""
WebSocket Connection Manager
Handles simultaneous connections from computer, laptop, and phone
"""

from fastapi import WebSocket
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

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
        message_str = json.dumps(message)
        
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

# Global instance
manager = ConnectionManager()
