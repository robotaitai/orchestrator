"""
WebSocket API for real-time updates.

Streams:
- Platform poses and states
- Task lifecycle events
- Timeline events
- Simulation camera frames (when MuJoCo is available)
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from commander.core.orchestrator import TimelineEvent, get_orchestrator
from commander.settings import SimMode, settings

router = APIRouter()
logger = logging.getLogger("commander.api.ws")


class ConnectionManager:
    """Manage WebSocket connections and broadcasting."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._running = False
        self._frame_enabled = False  # Whether to stream sim frames

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
        await self._send_initial_state(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        message_json = json.dumps(message, default=str)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_event(self, event: TimelineEvent) -> None:
        """Broadcast a timeline event."""
        await self.broadcast({
            "type": "timeline_event",
            "event": event.to_dict(),
        })
    
    async def broadcast_frame(self, frame_b64: str) -> None:
        """Broadcast a rendered frame to clients requesting it."""
        if not self._frame_enabled or not self.active_connections:
            return
        
        await self.broadcast({
            "type": "frame",
            "data": frame_b64,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _send_initial_state(self, websocket: WebSocket) -> None:
        """Send initial state to a newly connected client."""
        orchestrator = get_orchestrator()

        state_msg = {
            "type": "state_sync",
            "platforms": {
                pid: {
                    "id": p.id,
                    "name": p.name,
                    "type": p.type.value,
                    "status": p.status.value,
                    "position": {"x": p.position.x, "y": p.position.y, "z": p.position.z},
                    "battery_pct": p.battery_pct,
                    "health_ok": p.health_ok,
                }
                for pid, p in orchestrator.fleet_state.platforms.items()
            },
            "tasks": {
                tid: t.to_dict()
                for tid, t in list(orchestrator.tasks.items())[-20:]
            },
            "timeline": orchestrator.get_timeline(limit=50),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await websocket.send_json(state_msg)
        except Exception as e:
            logger.error(f"Failed to send initial state: {e}")

    async def start_broadcast_loop(self, interval: float = 0.1) -> None:
        """Start periodic state broadcast loop."""
        self._running = True
        orchestrator = get_orchestrator()
        orchestrator.on_event(self.broadcast_event)

        while self._running:
            if self.active_connections:
                await self.broadcast({
                    "type": "poses",
                    "platforms": {
                        pid: {
                            "x": p.position.x,
                            "y": p.position.y,
                            "z": p.position.z,
                            "status": p.status.value,
                        }
                        for pid, p in orchestrator.fleet_state.platforms.items()
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            await asyncio.sleep(interval)

    def stop_broadcast_loop(self) -> None:
        """Stop the broadcast loop."""
        self._running = False


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Main WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            await handle_client_message(websocket, data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def handle_client_message(websocket: WebSocket, data: dict[str, Any]) -> None:
    """Handle incoming WebSocket messages from clients."""
    import uuid
    from commander.core.models import Command

    msg_type = data.get("type", "")
    orchestrator = get_orchestrator()

    if msg_type == "ping":
        await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})

    elif msg_type == "command":
        command = Command(
            id=f"ws_cmd_{uuid.uuid4().hex[:8]}",
            type=data.get("command", ""),
            target=data.get("target", ""),
            params=data.get("params", {}),
        )
        task = await orchestrator.execute_command(command)
        await websocket.send_json({
            "type": "command_result",
            "task_id": task.id,
            "status": task.status.value,
            "error": task.error,
        })

    elif msg_type == "get_state":
        await manager._send_initial_state(websocket)
    
    elif msg_type == "enable_frames":
        manager._frame_enabled = data.get("enabled", True)
        await websocket.send_json({
            "type": "frames_enabled",
            "enabled": manager._frame_enabled,
        })
        logger.info(f"Frame streaming {'enabled' if manager._frame_enabled else 'disabled'}")


async def start_ws_broadcast() -> None:
    """Start WebSocket broadcast loop and optional frame streaming."""
    asyncio.create_task(manager.start_broadcast_loop(interval=0.1))
    logger.info("WebSocket broadcast loop started")
    
    # Start frame streaming if MuJoCo mode is enabled
    if settings.sim_mode == SimMode.MUJOCO:
        try:
            from commander.sim.renderer import get_renderer, RENDERING_AVAILABLE
            if RENDERING_AVAILABLE:
                renderer = get_renderer()
                renderer.on_frame(manager.broadcast_frame)
                # Renderer will be started when attached to model
                logger.info("Frame streaming callback registered")
        except Exception as e:
            logger.warning(f"Could not set up frame streaming: {e}")


def stop_ws_broadcast() -> None:
    """Stop WebSocket broadcast loop."""
    manager.stop_broadcast_loop()
    logger.info("WebSocket broadcast loop stopped")
