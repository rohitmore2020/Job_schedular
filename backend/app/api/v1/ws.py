import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.core.ws_manager import ws_manager

logger = logging.getLogger("scheduler.ws_router")

router = APIRouter(tags=["WebSocket Live Updates"])


@router.websocket("/ws")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """
    Real-time streaming WebSocket connection for browser dashboards.
    Pushes queue metrics, job completions, and worker telemetry in real-time.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "event": "connected",
            "message": "Connected to Job Scheduler real-time streaming feed",
        })

        while True:
            # Keep-alive receive loop
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        ws_manager.disconnect(websocket)
