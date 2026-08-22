import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("scheduler.ws")


class ConnectionManager:
    """
    Manages active WebSocket dashboard client connections and broadcasts
    live events (job status transitions, queue depth updates, worker heartbeats).
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔌 WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"🔌 WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast a structured event payload to all connected clients."""
        if not self.active_connections:
            return

        message = json.dumps({"event": event_type, "data": data})
        dead_connections = []

        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                dead_connections.append(conn)

        for dead in dead_connections:
            self.disconnect(dead)


# Global WebSocket Manager
ws_manager = ConnectionManager()
