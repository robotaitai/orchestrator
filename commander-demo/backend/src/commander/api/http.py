"""HTTP API endpoints."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from commander.core.models import Command
from commander.core.orchestrator import get_orchestrator, TaskStatus
from commander.llm.agent import (
    AgentClarificationResponse,
    AgentCommandsResponse,
    AgentErrorResponse,
    AgentInfoResponse,
    CommanderAgent,
)
from commander.settings import settings, SimMode

router = APIRouter()
logger = logging.getLogger("commander.api.http")

# ──────────────────────────────────────────────────────────────────────────────
# Shared State
# ──────────────────────────────────────────────────────────────────────────────

_agent: CommanderAgent | None = None


def get_agent() -> CommanderAgent:
    """Get or create the shared agent instance."""
    global _agent
    orchestrator = get_orchestrator()
    if _agent is None:
        _agent = CommanderAgent(fleet_state=orchestrator.fleet_state)
    else:
        _agent.fleet_state = orchestrator.fleet_state
    return _agent


# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    message: str


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    type: str
    content: dict[str, Any]
    trace_id: str | None = None


class CommandRequest(BaseModel):
    """Request body for direct command execution."""
    command: str
    target: str
    params: dict[str, Any] = {}


class RunCommandRequest(BaseModel):
    """Request for /command endpoint (natural language)."""
    text: str
    execute: bool = True  # If True, execute commands; if False, just parse


# ──────────────────────────────────────────────────────────────────────────────
# Health & Status
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, Any]:
    """Version and build information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gemini_configured": bool(settings.gemini_api_key),
        "sim_mode": settings.sim_mode.value,
    }


@router.get("/sim/mode")
async def get_sim_mode() -> dict[str, Any]:
    """Get current simulation mode."""
    orchestrator = get_orchestrator()
    
    # Check if MuJoCo is available
    mujoco_available = False
    try:
        from commander.sim.mujoco_world import MUJOCO_AVAILABLE
        mujoco_available = MUJOCO_AVAILABLE
    except ImportError:
        pass
    
    return {
        "mode": orchestrator.sim_mode.value,
        "mujoco_available": mujoco_available,
        "tick_rate": settings.sim_tick_rate,
        "realtime": settings.sim_realtime,
    }


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Get full orchestrator status."""
    orchestrator = get_orchestrator()
    return orchestrator.get_status()


# ──────────────────────────────────────────────────────────────────────────────
# Command Endpoint (Natural Language)
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/command")
async def run_command(request: RunCommandRequest) -> dict[str, Any]:
    """
    Process a natural language command.
    
    Returns a trace_id that can be used to track the command's execution.
    Subscribe to WebSocket for real-time updates.
    """
    agent = get_agent()
    orchestrator = get_orchestrator()
    trace_id = f"run_{uuid.uuid4().hex[:12]}"

    logger.info(f"[{trace_id}] Command: {request.text[:100]}...")

    try:
        response = await agent.process_message(request.text)

        result: dict[str, Any] = {
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if isinstance(response, AgentCommandsResponse):
            result["type"] = "commands"
            result["commands"] = [
                {"command": cmd.command, "target": cmd.target, "params": cmd.params}
                for cmd in response.commands
            ]
            result["explanation"] = response.explanation

            # Execute if requested
            if request.execute:
                tasks = await orchestrator.execute_commands(result["commands"])
                result["tasks"] = [
                    {"id": t.id, "status": t.status.value, "error": t.error}
                    for t in tasks
                ]

        elif isinstance(response, AgentClarificationResponse):
            result["type"] = "clarification"
            result["question"] = response.question
            result["options"] = response.options

        elif isinstance(response, AgentInfoResponse):
            result["type"] = "response"
            result["message"] = response.message

        elif isinstance(response, AgentErrorResponse):
            result["type"] = "error"
            result["error"] = response.error
            result["details"] = response.details

        return result

    except Exception as e:
        logger.exception(f"[{trace_id}] Command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{trace_id}")
async def get_run(trace_id: str) -> dict[str, Any]:
    """Get details of a command run by trace ID."""
    agent = get_agent()
    orchestrator = get_orchestrator()

    # Find matching traces
    matching_traces = [
        t for t in agent.traces
        if t.trace_id == trace_id or trace_id in t.trace_id
    ]

    if not matching_traces:
        raise HTTPException(status_code=404, detail=f"Run {trace_id} not found")

    trace = matching_traces[-1]

    # Find related tasks
    related_tasks = [
        t.to_dict() for t in orchestrator.tasks.values()
        if trace.timestamp <= t.created_at
    ][:10]

    return {
        "trace_id": trace.trace_id,
        "session_id": trace.session_id,
        "timestamp": trace.timestamp.isoformat(),
        "user_input": trace.user_input,
        "response_type": trace.parsed_response.type.value if trace.parsed_response else "error",
        "duration_ms": trace.duration_ms,
        "related_tasks": related_tasks,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Chat (LLM Agent) - Legacy endpoint
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a chat message through the LLM agent."""
    result = await run_command(RunCommandRequest(text=request.message, execute=True))

    return ChatResponse(
        type=result.get("type", "error"),
        content={k: v for k, v in result.items() if k not in ("type", "trace_id", "timestamp")},
        trace_id=result.get("trace_id"),
    )


@router.post("/chat/reset")
async def reset_chat() -> dict[str, str]:
    """Reset the conversation (clear memory)."""
    agent = get_agent()
    agent.reset_conversation()
    return {"status": "ok", "message": "Conversation reset"}


# ──────────────────────────────────────────────────────────────────────────────
# Direct Commands
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/commands")
async def execute_command(request: CommandRequest) -> dict[str, Any]:
    """Execute a command directly (bypassing LLM)."""
    orchestrator = get_orchestrator()

    command = Command(
        id=f"cmd_direct_{uuid.uuid4().hex[:8]}",
        type=request.command,
        target=request.target,
        params=request.params,
    )

    task = await orchestrator.execute_command(command)

    return {
        "task_id": task.id,
        "status": task.status.value,
        "error": task.error,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Demo Mode
# ──────────────────────────────────────────────────────────────────────────────


# Demo script: 5 scenes for the investor demo
# Each scene has a name, commands, and delay for pacing
DEMO_SCRIPT = [
    # Scene 1: Status Report
    {
        "scene": 1,
        "name": "Fleet Status Report",
        "commands": [
            {"text": "Report status of all platforms", "delay": 3.0},
        ],
    },
    # Scene 2: Convoy Formation to Alpha
    {
        "scene": 2,
        "name": "Convoy to Alpha",
        "commands": [
            {"text": "Form convoy with all ground robots, UGV1 leads, 3 meter gap", "delay": 4.0},
            {"text": "Move the convoy to checkpoint alpha", "delay": 8.0},
        ],
    },
    # Scene 3: Wedge Formation to Bravo
    {
        "scene": 3,
        "name": "Wedge to Bravo",
        "commands": [
            {"text": "Reform all ground robots into wedge formation", "delay": 4.0},
            {"text": "Move the formation to checkpoint bravo", "delay": 8.0},
        ],
    },
    # Scene 4: Aerial Support
    {
        "scene": 4,
        "name": "Aerial Support",
        "commands": [
            {"text": "UAV1 orbit above checkpoint bravo at 20 meters altitude, 8 meter radius", "delay": 5.0},
            {"text": "UAV2 spotlight checkpoint bravo", "delay": 3.0},
        ],
    },
    # Scene 5: Safety Constraints Demo
    {
        "scene": 5,
        "name": "Safety Constraints",
        "commands": [
            {"text": "Move UGV2 to position -15, -15", "delay": 4.0},  # Should fail (in no-go zone)
            {"text": "Move UGV2 to position -25, -5", "delay": 5.0},  # Safe path around R1
        ],
    },
    # Finale: Stop All
    {
        "scene": 6,
        "name": "Stop All",
        "commands": [
            {"text": "Stop all platforms", "delay": 2.0},
        ],
    },
]

# Flatten to legacy format for backward compatibility
DEMO_COMMANDS = []
for scene in DEMO_SCRIPT:
    for cmd in scene["commands"]:
        DEMO_COMMANDS.append({
            "text": cmd["text"],
            "delay": cmd["delay"],
            "scene": scene["scene"],
            "scene_name": scene["name"],
        })


# ──────────────────────────────────────────────────────────────────────────────
# Replay
# ──────────────────────────────────────────────────────────────────────────────


class ReplayEntry(BaseModel):
    """A single entry from a replay JSONL file."""
    timestamp: str
    event_type: str
    data: dict[str, Any]


@router.post("/replay/load")
async def load_replay(request: Request) -> dict[str, Any]:
    """
    Load a replay from JSONL content.
    
    Each line should be a JSON object with: timestamp, event_type, data
    Accepts text/plain or application/json content types.
    """
    import json
    
    # Get the body as text
    body = await request.body()
    file_content = body.decode('utf-8')
    
    # If it's a JSON string (wrapped in quotes), unwrap it
    if file_content.startswith('"') and file_content.endswith('"'):
        try:
            file_content = json.loads(file_content)
        except json.JSONDecodeError:
            pass
    
    events = []
    for line in file_content.strip().split('\n'):
        if line.strip():
            try:
                entry = json.loads(line)
                events.append(entry)
            except json.JSONDecodeError:
                continue
    
    return {
        "status": "ok",
        "event_count": len(events),
        "events": events[:100],  # Return first 100 for preview
    }


@router.get("/replay/export")
async def export_replay() -> dict[str, Any]:
    """Export current session as JSONL for replay."""
    orchestrator = get_orchestrator()
    agent = get_agent()
    
    # Collect all events
    timeline = orchestrator.timeline
    traces = agent.traces
    
    # Build JSONL content
    lines = []
    
    # Add trace events
    for trace in traces:
        lines.append({
            "timestamp": trace.timestamp.isoformat(),
            "event_type": "agent_trace",
            "data": {
                "trace_id": trace.trace_id,
                "user_input": trace.user_input,
                "response_type": trace.parsed_response.type.value if trace.parsed_response else "error",
            }
        })
    
    # Add timeline events
    for event in timeline:
        lines.append({
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.type.value,
            "data": event.data,
            "task_id": event.task_id,
            "platform_id": event.platform_id,
        })
    
    # Sort by timestamp
    lines.sort(key=lambda x: x["timestamp"])
    
    # Convert to JSONL
    import json
    jsonl_content = '\n'.join(json.dumps(line) for line in lines)
    
    return {
        "event_count": len(lines),
        "content": jsonl_content,
    }


@router.get("/demo/commands")
async def get_demo_commands() -> dict[str, Any]:
    """Get the list of demo commands."""
    return {"commands": DEMO_COMMANDS}


@router.get("/demo/script")
async def get_demo_script() -> dict[str, Any]:
    """Get the full demo script with scenes."""
    return {
        "scenes": DEMO_SCRIPT,
        "total_steps": len(DEMO_COMMANDS),
        "total_scenes": len(DEMO_SCRIPT),
    }


@router.post("/demo/run/{step}")
async def run_demo_step(step: int) -> dict[str, Any]:
    """Run a specific demo step."""
    if step < 0 or step >= len(DEMO_COMMANDS):
        raise HTTPException(status_code=400, detail=f"Invalid step {step}")

    demo_cmd = DEMO_COMMANDS[step]
    result = await run_command(RunCommandRequest(text=demo_cmd["text"], execute=True))

    return {
        "step": step,
        "scene": demo_cmd.get("scene", 0),
        "scene_name": demo_cmd.get("scene_name", ""),
        "text": demo_cmd["text"],
        "delay": demo_cmd["delay"],
        "result": result,
    }


@router.post("/demo/reset")
async def reset_demo() -> dict[str, str]:
    """Reset demo state (conversation + move platforms to origin)."""
    agent = get_agent()
    orchestrator = get_orchestrator()
    
    # Reset conversation
    agent.reset_conversation()
    
    # Reset platform positions to initial state
    initial_positions = {
        "ugv1": {"x": 0, "y": 0, "z": 0.25},
        "ugv2": {"x": 2, "y": 0, "z": 0.25},
        "ugv3": {"x": 4, "y": 0, "z": 0.25},
        "uav1": {"x": 0, "y": 0, "z": 15},
        "uav2": {"x": 3, "y": 0, "z": 15},
    }
    
    for pid, pos in initial_positions.items():
        platform = orchestrator.get_platform(pid)
        if platform:
            from commander.core.models import Position, PlatformStatus
            platform.position = Position(x=pos["x"], y=pos["y"], z=pos["z"])
            platform.status = PlatformStatus.IDLE
    
    return {"status": "ok", "message": "Demo reset complete"}


# ──────────────────────────────────────────────────────────────────────────────
# Platforms
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/platforms")
async def list_platforms() -> dict[str, Any]:
    """List all platforms."""
    orchestrator = get_orchestrator()
    platforms = orchestrator.fleet_state.platforms

    return {
        "platforms": [
            {
                "id": p.id,
                "name": p.name,
                "type": p.type.value,
                "position": {"x": p.position.x, "y": p.position.y, "z": p.position.z},
                "status": p.status.value,
                "battery_pct": p.battery_pct,
            }
            for p in platforms.values()
        ],
        "count": len(platforms),
    }


@router.get("/platforms/{platform_id}")
async def get_platform(platform_id: str) -> dict[str, Any]:
    """Get a specific platform."""
    orchestrator = get_orchestrator()
    platform = orchestrator.get_platform(platform_id)

    if not platform:
        raise HTTPException(status_code=404, detail=f"Platform {platform_id} not found")

    return {
        "id": platform.id,
        "name": platform.name,
        "type": platform.type.value,
        "position": {
            "x": platform.position.x,
            "y": platform.position.y,
            "z": platform.position.z,
        },
        "status": platform.status.value,
        "battery_pct": platform.battery_pct,
        "health_ok": platform.health_ok,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/tasks")
async def list_tasks(status: str | None = None, limit: int = 20) -> dict[str, Any]:
    """List tasks, optionally filtered by status."""
    orchestrator = get_orchestrator()

    tasks = list(orchestrator.tasks.values())

    if status:
        try:
            status_enum = TaskStatus(status)
            tasks = [t for t in tasks if t.status == status_enum]
        except ValueError:
            pass

    tasks = tasks[-limit:]

    return {
        "tasks": [t.to_dict() for t in tasks],
        "count": len(tasks),
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """Get a specific task."""
    orchestrator = get_orchestrator()
    task = orchestrator.tasks.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return task.to_dict()


# ──────────────────────────────────────────────────────────────────────────────
# Timeline
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/timeline")
async def get_timeline(limit: int = 50) -> dict[str, Any]:
    """Get recent timeline events."""
    orchestrator = get_orchestrator()
    events = orchestrator.get_timeline(limit=limit)

    return {
        "events": events,
        "count": len(events),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Playbook
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/playbook")
async def get_playbook() -> dict[str, Any]:
    """Get the available playbook commands."""
    return {
        "commands": [
            {"name": "go_to", "description": "Move platform to a position", "params": ["target", "x", "y", "z?", "speed?"]},
            {"name": "return_home", "description": "Return platform to home position", "params": ["target"]},
            {"name": "hold_position", "description": "Hold current position", "params": ["target", "duration_s?"]},
            {"name": "patrol", "description": "Patrol between waypoints", "params": ["target", "waypoints", "loop?"]},
            {"name": "form_formation", "description": "Form a formation", "params": ["target", "formation", "spacing_m", "leader?"]},
            {"name": "follow_leader", "description": "Follow a leader platform", "params": ["target", "leader", "gap_m"]},
            {"name": "orbit", "description": "UAV orbits a position", "params": ["target", "center_x", "center_y", "radius_m", "altitude_m"]},
            {"name": "spotlight", "description": "UAV shines spotlight", "params": ["target", "target_x", "target_y", "duration_s?"]},
            {"name": "point_laser", "description": "UAV points laser marker", "params": ["target", "target_x", "target_y", "duration_s?"]},
            {"name": "report_status", "description": "Get platform status", "params": ["target"]},
            {"name": "stop", "description": "Immediately stop platform", "params": ["target"]},
        ]
    }


# ──────────────────────────────────────────────────────────────────────────────
# Constraints / Config
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/constraints")
async def get_constraints() -> dict[str, Any]:
    """Get current safety constraints configuration."""
    orchestrator = get_orchestrator()
    config = orchestrator.constraints.config

    return {
        "min_separation_m": config.min_separation_m,
        "speed_limits": {
            "ugv": config.speed_limits.ugv,
            "uav": config.speed_limits.uav,
        },
        "world_bounds": {
            "x": [config.world_bounds.x_min, config.world_bounds.x_max],
            "y": [config.world_bounds.y_min, config.world_bounds.y_max],
            "z": [config.world_bounds.z_min, config.world_bounds.z_max],
        },
        "no_go_zones": [
            {"name": z.name, "vertices": z.vertices}
            for z in config.no_go_zones
        ],
        "comms_timeout_s": config.comms_timeout_s,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Traces
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/traces")
async def get_traces(limit: int = 10) -> dict[str, Any]:
    """Get recent agent traces for debugging."""
    agent = get_agent()
    traces = agent.get_traces(limit=limit)

    return {
        "traces": [
            {
                "trace_id": t.trace_id,
                "session_id": t.session_id,
                "timestamp": t.timestamp.isoformat(),
                "user_input": t.user_input[:100],
                "response_type": t.parsed_response.type.value if t.parsed_response else "error",
                "duration_ms": t.duration_ms,
            }
            for t in traces
        ],
        "count": len(traces),
    }
