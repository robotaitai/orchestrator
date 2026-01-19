"""
Command Orchestrator

Manages platform state, task queue, and command execution.
Converts validated commands into executable tasks and tracks their lifecycle.

Supports two simulation modes:
- STATE: Simple state-based (instant position updates)
- MUJOCO: Full physics simulation with smooth motion
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from commander.core.constraints import ConstraintsEngine, create_demo_engine
from commander.core.models import (
    Command,
    FleetState,
    Platform,
    PlatformStatus,
    PlatformType,
    Position,
    Velocity,
)
from commander.settings import AvoidPolicy, SimMode, settings

if TYPE_CHECKING:
    from commander.sim.mujoco_world import MuJoCoWorld

logger = logging.getLogger("commander.orchestrator")


# ──────────────────────────────────────────────────────────────────────────────
# Task Model
# ──────────────────────────────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    """Task lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A task to be executed by a platform."""

    id: str
    command: str
    target: str  # Platform ID
    params: dict[str, Any]
    status: TaskStatus = TaskStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    progress: float = 0.0  # 0.0 to 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "command": self.command,
            "target": self.target,
            "params": self.params,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "progress": self.progress,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Timeline Events
# ──────────────────────────────────────────────────────────────────────────────


class EventType(str, Enum):
    """Types of timeline events."""

    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_SUCCEEDED = "task_succeeded"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    PLATFORM_STATE_CHANGED = "platform_state_changed"
    CONSTRAINT_VIOLATION = "constraint_violation"
    SYSTEM = "system"


@dataclass
class TimelineEvent:
    """An event in the orchestrator timeline."""

    id: str
    type: EventType
    timestamp: datetime
    data: dict[str, Any]
    task_id: str | None = None
    platform_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "task_id": self.task_id,
            "platform_id": self.platform_id,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────


class Orchestrator:
    """
    Central orchestrator for command execution.

    Responsibilities:
    - Maintain fleet state
    - Convert commands to tasks
    - Execute tasks via handlers
    - Track task lifecycle
    - Emit timeline events
    """

    def __init__(
        self,
        constraints: ConstraintsEngine | None = None,
        sim_mode: SimMode | None = None,
    ) -> None:
        """Initialize the orchestrator."""
        self.fleet_state = FleetState()
        self.constraints = constraints or create_demo_engine()
        
        # Simulation mode
        self.sim_mode = sim_mode or settings.sim_mode
        self._mujoco_world: "MuJoCoWorld | None" = None

        # Task management
        self.tasks: dict[str, Task] = {}
        self.task_queue: asyncio.Queue[str] = asyncio.Queue()

        # Timeline
        self.timeline: list[TimelineEvent] = []
        self.max_timeline_events = 1000

        # Event callbacks (for WebSocket broadcasting)
        self._event_callbacks: list[Callable[[TimelineEvent], Coroutine]] = []

        # Command handlers
        self._handlers: dict[str, Callable] = {
            "go_to": self._handle_go_to,
            "hold_position": self._handle_hold_position,
            "stop": self._handle_stop,
            "report_status": self._handle_report_status,
            "form_formation": self._handle_form_formation,
            "follow_leader": self._handle_follow_leader,
            "orbit": self._handle_orbit,
            "return_home": self._handle_return_home,
            "spotlight": self._handle_spotlight,
            "point_laser": self._handle_point_laser,
            "patrol": self._handle_patrol,
        }

        # Background task runners
        self._runner_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._mujoco_sync_task: asyncio.Task | None = None

        logger.info(f"Orchestrator initialized (sim_mode={self.sim_mode.value})")

    # ──────────────────────────────────────────────────────────────────────────
    # Platform Management
    # ──────────────────────────────────────────────────────────────────────────

    def register_platform(self, platform: Platform) -> None:
        """Register a platform with the orchestrator."""
        # Ensure heartbeat is fresh
        platform.last_heartbeat = datetime.now(timezone.utc)
        self.fleet_state.platforms[platform.id] = platform
        self._emit_event(
            EventType.SYSTEM,
            {"message": f"Platform {platform.id} registered"},
            platform_id=platform.id,
        )
        logger.info(f"Registered platform: {platform.id}")

    def refresh_heartbeats(self) -> None:
        """Refresh all platform heartbeats (call periodically in sim loop)."""
        now = datetime.now(timezone.utc)
        for platform in self.fleet_state.platforms.values():
            platform.last_heartbeat = now

    def get_platform(self, platform_id: str) -> Platform | None:
        """Get a platform by ID."""
        return self.fleet_state.get_platform(platform_id)

    def update_platform_state(
        self,
        platform_id: str,
        position: Position | None = None,
        velocity: Velocity | None = None,
        status: PlatformStatus | None = None,
    ) -> None:
        """Update platform state."""
        platform = self.get_platform(platform_id)
        if not platform:
            return

        changed = False
        if position and position != platform.position:
            platform.position = position
            changed = True
        if velocity and velocity != platform.velocity:
            platform.velocity = velocity
            changed = True
        if status and status != platform.status:
            platform.status = status
            changed = True

        if changed:
            platform.last_heartbeat = datetime.now(timezone.utc)
            self._emit_event(
                EventType.PLATFORM_STATE_CHANGED,
                {
                    "position": {"x": platform.position.x, "y": platform.position.y, "z": platform.position.z},
                    "status": platform.status.value,
                },
                platform_id=platform_id,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Command Processing
    # ──────────────────────────────────────────────────────────────────────────

    async def execute_command(self, command: Command) -> Task:
        """
        Execute a command by creating and queuing a task.

        Args:
            command: Validated command to execute

        Returns:
            Created task
        """
        # Check constraints
        result = self.constraints.check_command(command, self.fleet_state)
        if not result.is_approved:
            self._emit_event(
                EventType.CONSTRAINT_VIOLATION,
                {"violations": result.violations, "command": command.type},
            )
            # Create failed task
            task = Task(
                id=f"task_{uuid.uuid4().hex[:8]}",
                command=command.type,
                target=command.target,
                params=command.params,
                status=TaskStatus.FAILED,
                error=result.rejection_message(),
            )
            self.tasks[task.id] = task
            return task

        # Create task
        task = Task(
            id=f"task_{uuid.uuid4().hex[:8]}",
            command=command.type,
            target=command.target,
            params=command.params,
        )
        self.tasks[task.id] = task

        self._emit_event(
            EventType.TASK_CREATED,
            {"command": command.type, "target": command.target},
            task_id=task.id,
            platform_id=command.target if command.target not in ("all", "ugv_pod", "uav_pod") else None,
        )

        # Queue for execution
        await self.task_queue.put(task.id)
        logger.info(f"Task {task.id} created for command {command.type}")

        return task

    async def execute_commands(self, commands: list[dict[str, Any]]) -> list[Task]:
        """Execute multiple commands (from agent output)."""
        tasks = []
        for cmd_dict in commands:
            command = Command(
                id=f"cmd_{uuid.uuid4().hex[:8]}",
                type=cmd_dict.get("command", ""),
                target=cmd_dict.get("target", ""),
                params=cmd_dict.get("params", {}),
            )
            task = await self.execute_command(command)
            tasks.append(task)
        return tasks

    # ──────────────────────────────────────────────────────────────────────────
    # Task Execution
    # ──────────────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the task runner and simulation loops."""
        if self._runner_task is None:
            self._runner_task = asyncio.create_task(self._run_task_loop())
            logger.info("Orchestrator task runner started")
        
        # Start simulation based on mode
        if self.sim_mode == SimMode.MUJOCO:
            await self._start_mujoco()
        else:
            # State mode: just run heartbeat loop
            if self._heartbeat_task is None:
                self._heartbeat_task = asyncio.create_task(self._run_heartbeat_loop())
                logger.info("Orchestrator heartbeat loop started")
    
    async def _start_mujoco(self) -> None:
        """Start MuJoCo simulation."""
        from commander.sim.mujoco_world import get_mujoco_world
        
        self._mujoco_world = get_mujoco_world()
        self._mujoco_world.load()
        
        # Register platforms from MuJoCo world
        for platform in self._mujoco_world.get_platform_models():
            self.register_platform(platform)
        
        # Start MuJoCo simulation
        await self._mujoco_world.start()
        
        # Start sync loop to update fleet state from MuJoCo
        if self._mujoco_sync_task is None:
            self._mujoco_sync_task = asyncio.create_task(self._run_mujoco_sync_loop())
        
        logger.info("MuJoCo simulation started")

    async def stop(self) -> None:
        """Stop the task runner and simulation loops."""
        # Stop MuJoCo sync
        if self._mujoco_sync_task:
            self._mujoco_sync_task.cancel()
            try:
                await self._mujoco_sync_task
            except asyncio.CancelledError:
                pass
            self._mujoco_sync_task = None
        
        # Stop MuJoCo world
        if self._mujoco_world:
            await self._mujoco_world.stop()
            self._mujoco_world = None
        
        # Stop heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        # Stop task runner
        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
            self._runner_task = None
        
        logger.info("Orchestrator stopped")

    async def _run_task_loop(self) -> None:
        """Main task execution loop."""
        while True:
            try:
                task_id = await self.task_queue.get()
                task = self.tasks.get(task_id)
                if task and task.status == TaskStatus.QUEUED:
                    await self._execute_task(task)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in task loop: {e}")

    async def _run_heartbeat_loop(self) -> None:
        """Periodically refresh heartbeats for state mode (no real sim)."""
        while True:
            try:
                self.refresh_heartbeats()
                await asyncio.sleep(1.0)  # Refresh every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in heartbeat loop: {e}")
    
    async def _run_mujoco_sync_loop(self) -> None:
        """Sync fleet state from MuJoCo simulation."""
        while True:
            try:
                if self._mujoco_world:
                    poses = self._mujoco_world.get_all_poses()
                    now = datetime.now(timezone.utc)
                    
                    for platform_id, pose in poses.items():
                        platform = self.get_platform(platform_id)
                        if platform and pose:
                            platform.position = Position(
                                x=pose["x"],
                                y=pose["y"],
                                z=pose["z"],
                            )
                            platform.last_heartbeat = now
                            
                            # Update status from MuJoCo
                            mode = pose.get("mode", "idle")
                            if mode == "idle":
                                platform.status = PlatformStatus.IDLE
                            elif mode in ("go_to", "orbit", "follow", "formation"):
                                platform.status = PlatformStatus.MOVING
                            elif mode == "hold":
                                platform.status = PlatformStatus.HOLDING
                
                await asyncio.sleep(0.05)  # 20Hz sync
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in MuJoCo sync loop: {e}")
                await asyncio.sleep(0.1)

    async def _execute_task(self, task: Task) -> None:
        """Execute a single task."""
        # Start task
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        self._emit_event(
            EventType.TASK_STARTED,
            {"command": task.command},
            task_id=task.id,
            platform_id=task.target if task.target not in ("all", "ugv_pod", "uav_pod") else None,
        )

        # Get handler
        handler = self._handlers.get(task.command)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error = f"Unknown command: {task.command}"
            task.completed_at = datetime.now(timezone.utc)
            self._emit_event(
                EventType.TASK_FAILED,
                {"error": task.error},
                task_id=task.id,
            )
            return

        # Execute
        try:
            await handler(task)
            task.status = TaskStatus.SUCCEEDED
            task.progress = 1.0
            task.completed_at = datetime.now(timezone.utc)
            self._emit_event(
                EventType.TASK_SUCCEEDED,
                {"command": task.command},
                task_id=task.id,
            )
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now(timezone.utc)
            self._emit_event(
                EventType.TASK_FAILED,
                {"error": str(e)},
                task_id=task.id,
            )
            logger.exception(f"Task {task.id} failed: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Command Handlers
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_go_to(self, task: Task) -> None:
        """Handle go_to command with path safety checking."""
        targets = self._resolve_targets(task.target)
        x = task.params.get("x", 0)
        y = task.params.get("y", 0)
        z = task.params.get("z")

        for platform_id in targets:
            platform = self.get_platform(platform_id)
            if not platform:
                continue

            target_z = z if z is not None else platform.position.z
            target_pos = Position(x=x, y=y, z=target_z)
            
            # Check path for no-go zone intersections
            waypoints, error = self.constraints.get_safe_path(
                platform.position,
                target_pos,
                avoid_policy=settings.avoid_policy.value,
            )
            
            if error:
                # Path crosses no-go zone
                self._emit_event(
                    EventType.CONSTRAINT_VIOLATION,
                    {
                        "message": error,
                        "platform": platform_id,
                        "policy": settings.avoid_policy.value,
                    },
                    task_id=task.id,
                    platform_id=platform_id,
                )
                raise ValueError(error)
            
            # Update status
            platform.status = PlatformStatus.MOVING
            
            # Execute path (may include detour waypoints)
            if self.sim_mode == SimMode.MUJOCO and self._mujoco_world:
                # MuJoCo mode: command smooth motion through waypoints
                for i, wp in enumerate(waypoints):
                    if i == 0:
                        self._mujoco_world.command_go_to(platform_id, wp.x, wp.y, wp.z)
                    else:
                        # Queue subsequent waypoints (simplified - in full impl, wait for arrival)
                        logger.info(f"Platform {platform_id} waypoint {i+1}: ({wp.x:.1f}, {wp.y:.1f})")
                
                if len(waypoints) > 1:
                    logger.info(f"Platform {platform_id} following detour path with {len(waypoints)} waypoints")
                else:
                    logger.info(f"Platform {platform_id} moving to ({x}, {y}, {target_z})")
            else:
                # State mode: instant teleport to final position
                final_pos = waypoints[-1] if waypoints else target_pos
                await asyncio.sleep(0.1)  # Brief delay
                platform.position = final_pos
                platform.status = PlatformStatus.IDLE
                
                if len(waypoints) > 1:
                    logger.info(f"Platform {platform_id} teleported via detour to ({final_pos.x}, {final_pos.y})")
                else:
                    logger.info(f"Platform {platform_id} moved to ({x}, {y}, {target_z})")

    async def _handle_hold_position(self, task: Task) -> None:
        """Handle hold_position command."""
        targets = self._resolve_targets(task.target)
        duration = task.params.get("duration_s")

        for platform_id in targets:
            platform = self.get_platform(platform_id)
            if not platform:
                continue

            platform.status = PlatformStatus.HOLDING
            platform.velocity = Velocity(vx=0, vy=0, vz=0)
            
            if self.sim_mode == SimMode.MUJOCO and self._mujoco_world:
                self._mujoco_world.command_hold(platform_id)

        if duration:
            await asyncio.sleep(min(duration, 5.0))  # Cap at 5s for demo

        for platform_id in targets:
            platform = self.get_platform(platform_id)
            if platform:
                platform.status = PlatformStatus.IDLE

    async def _handle_stop(self, task: Task) -> None:
        """Handle stop command (emergency stop)."""
        targets = self._resolve_targets(task.target)

        for platform_id in targets:
            platform = self.get_platform(platform_id)
            if not platform:
                continue

            platform.status = PlatformStatus.IDLE
            platform.velocity = Velocity(vx=0, vy=0, vz=0)
            
            if self.sim_mode == SimMode.MUJOCO and self._mujoco_world:
                self._mujoco_world.command_stop(platform_id)
            
            logger.info(f"Platform {platform_id} stopped")

    async def _handle_report_status(self, task: Task) -> None:
        """Handle report_status command."""
        targets = self._resolve_targets(task.target)

        status_report = {}
        for platform_id in targets:
            platform = self.get_platform(platform_id)
            if platform:
                status_report[platform_id] = {
                    "name": platform.name,
                    "type": platform.type.value,
                    "status": platform.status.value,
                    "position": {
                        "x": platform.position.x,
                        "y": platform.position.y,
                        "z": platform.position.z,
                    },
                    "battery_pct": platform.battery_pct,
                    "health_ok": platform.health_ok,
                }

        # Store report in task params for retrieval
        task.params["status_report"] = status_report

    async def _handle_form_formation(self, task: Task) -> None:
        """Handle form_formation command (simple leader/follower)."""
        targets = self._resolve_targets(task.target)
        formation = task.params.get("formation", "line")
        spacing = task.params.get("spacing_m", 3.0)
        leader_id = task.params.get("leader")

        if not targets:
            return

        # Determine leader
        if leader_id and leader_id in targets:
            leader = self.get_platform(leader_id)
        else:
            leader = self.get_platform(targets[0])
            leader_id = targets[0]

        if not leader:
            return

        # Position followers based on formation
        followers = [t for t in targets if t != leader_id]
        leader_pos = leader.position

        for i, follower_id in enumerate(followers):
            follower = self.get_platform(follower_id)
            if not follower:
                continue

            # Calculate offset based on formation
            if formation == "line":
                # Line behind leader
                offset_x = -spacing * (i + 1)
                offset_y = 0.0
            elif formation == "wedge":
                # V-shape behind leader
                side = 1 if i % 2 == 0 else -1
                row = (i // 2) + 1
                offset_x = -spacing * row
                offset_y = float(side) * spacing * row * 0.5
            elif formation == "column":
                # Column to the side
                offset_x = 0.0
                offset_y = spacing * (i + 1)
            else:
                offset_x = -spacing * (i + 1)
                offset_y = 0.0

            offset_z = 0.0
            
            if self.sim_mode == SimMode.MUJOCO and self._mujoco_world:
                # MuJoCo mode: command formation offset behavior
                self._mujoco_world.command_formation(
                    follower_id, leader_id, (offset_x, offset_y, offset_z)
                )
                follower.status = PlatformStatus.MOVING
            else:
                # State mode: instant position
                new_pos = Position(
                    x=leader_pos.x + offset_x,
                    y=leader_pos.y + offset_y,
                    z=follower.position.z,
                )
                follower.position = new_pos
                follower.status = PlatformStatus.IDLE

        logger.info(f"Formation {formation} formed with leader {leader_id}")

    async def _handle_follow_leader(self, task: Task) -> None:
        """Handle follow_leader (convoy) command."""
        targets = self._resolve_targets(task.target)
        leader_id = task.params.get("leader")
        gap = task.params.get("gap_m", 3.0)

        if not leader_id or leader_id not in self.fleet_state.platforms:
            raise ValueError(f"Leader {leader_id} not found")

        leader = self.get_platform(leader_id)
        if not leader:
            return

        # Position followers in a line behind leader
        followers = [t for t in targets if t != leader_id]
        leader_pos = leader.position

        for i, follower_id in enumerate(followers):
            follower = self.get_platform(follower_id)
            if not follower:
                continue

            follower.status = PlatformStatus.MOVING
            
            if self.sim_mode == SimMode.MUJOCO and self._mujoco_world:
                # MuJoCo mode: command follow behavior
                effective_gap = gap * (i + 1)
                self._mujoco_world.command_follow(follower_id, leader_id, effective_gap)
            else:
                # State mode: instant position
                new_pos = Position(
                    x=leader_pos.x - gap * (i + 1),
                    y=leader_pos.y,
                    z=follower.position.z,
                )
                follower.position = new_pos

        logger.info(f"Convoy formed following {leader_id} with {gap}m gap")

    async def _handle_orbit(self, task: Task) -> None:
        """Handle orbit command (UAV only)."""
        platform = self.get_platform(task.target)
        if not platform:
            raise ValueError(f"Platform {task.target} not found")

        if platform.type != PlatformType.UAV:
            raise ValueError(f"Orbit command only valid for UAVs, got {platform.type}")

        center_x = task.params.get("center_x", 0)
        center_y = task.params.get("center_y", 0)
        radius = task.params.get("radius_m", 10)
        altitude = task.params.get("altitude_m", 20)

        platform.status = PlatformStatus.EXECUTING

        if self.sim_mode == SimMode.MUJOCO and self._mujoco_world:
            # MuJoCo mode: command orbit motion
            self._mujoco_world.command_orbit(task.target, center_x, center_y, radius, altitude)
        else:
            # State mode: instant position to orbit start
            platform.position = Position(
                x=center_x + radius,
                y=center_y,
                z=altitude,
            )

        logger.info(f"UAV {task.target} orbiting ({center_x}, {center_y}) at {altitude}m")

    async def _handle_return_home(self, task: Task) -> None:
        """Handle return_home command."""
        targets = self._resolve_targets(task.target)

        for platform_id in targets:
            platform = self.get_platform(platform_id)
            if not platform:
                continue

            platform.status = PlatformStatus.MOVING
            await asyncio.sleep(0.1)
            platform.position = Position(x=0, y=0, z=platform.position.z)
            platform.status = PlatformStatus.IDLE

        logger.info(f"Platforms {targets} returned home")

    async def _handle_spotlight(self, task: Task) -> None:
        """Handle spotlight command (UAV only)."""
        platform = self.get_platform(task.target)
        if not platform:
            raise ValueError(f"Platform {task.target} not found")

        target_x = task.params.get("target_x", 0)
        target_y = task.params.get("target_y", 0)
        duration = task.params.get("duration_s", 5)

        platform.status = PlatformStatus.EXECUTING
        logger.info(f"UAV {task.target} spotlight on ({target_x}, {target_y}) for {duration}s")

        # Simulate spotlight duration
        await asyncio.sleep(min(duration, 2.0))
        platform.status = PlatformStatus.IDLE

    async def _handle_point_laser(self, task: Task) -> None:
        """Handle point_laser command (UAV only)."""
        platform = self.get_platform(task.target)
        if not platform:
            raise ValueError(f"Platform {task.target} not found")

        target_x = task.params.get("target_x", 0)
        target_y = task.params.get("target_y", 0)
        duration = task.params.get("duration_s", 5)

        platform.status = PlatformStatus.EXECUTING
        logger.info(f"UAV {task.target} laser on ({target_x}, {target_y}) for {duration}s")

        await asyncio.sleep(min(duration, 2.0))
        platform.status = PlatformStatus.IDLE

    async def _handle_patrol(self, task: Task) -> None:
        """Handle patrol command."""
        platform = self.get_platform(task.target)
        if not platform:
            raise ValueError(f"Platform {task.target} not found")

        waypoints = task.params.get("waypoints", [])
        loop = task.params.get("loop", False)

        if not waypoints:
            raise ValueError("Patrol requires waypoints")

        platform.status = PlatformStatus.MOVING

        # Visit first waypoint (stub)
        wp = waypoints[0]
        platform.position = Position(x=wp.get("x", 0), y=wp.get("y", 0), z=wp.get("z", platform.position.z))

        logger.info(f"Platform {task.target} patrolling {len(waypoints)} waypoints")

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_targets(self, target: str) -> list[str]:
        """Resolve target to list of platform IDs."""
        if target == "all":
            return list(self.fleet_state.platforms.keys())
        elif target == "ugv_pod":
            return [
                pid for pid, p in self.fleet_state.platforms.items()
                if p.type in (PlatformType.UGV, PlatformType.GROUND)
            ]
        elif target == "uav_pod":
            return [
                pid for pid, p in self.fleet_state.platforms.items()
                if p.type in (PlatformType.UAV, PlatformType.AERIAL)
            ]
        elif target in self.fleet_state.platforms:
            return [target]
        else:
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # Timeline Events
    # ──────────────────────────────────────────────────────────────────────────

    def _emit_event(
        self,
        event_type: EventType,
        data: dict[str, Any],
        task_id: str | None = None,
        platform_id: str | None = None,
    ) -> None:
        """Emit a timeline event."""
        event = TimelineEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            type=event_type,
            timestamp=datetime.now(timezone.utc),
            data=data,
            task_id=task_id,
            platform_id=platform_id,
        )

        self.timeline.append(event)

        # Trim timeline
        if len(self.timeline) > self.max_timeline_events:
            self.timeline = self.timeline[-self.max_timeline_events:]

        # Notify callbacks
        for callback in self._event_callbacks:
            asyncio.create_task(callback(event))

        logger.debug(f"Event: {event_type.value} - {data}")

    def on_event(self, callback: Callable[[TimelineEvent], Coroutine]) -> None:
        """Register an event callback."""
        self._event_callbacks.append(callback)

    def get_timeline(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent timeline events."""
        return [e.to_dict() for e in self.timeline[-limit:]]

    # ──────────────────────────────────────────────────────────────────────────
    # Status
    # ──────────────────────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get full orchestrator status."""
        return {
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
                for pid, p in self.fleet_state.platforms.items()
            },
            "tasks": {
                "total": len(self.tasks),
                "queued": len([t for t in self.tasks.values() if t.status == TaskStatus.QUEUED]),
                "running": len([t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]),
                "succeeded": len([t for t in self.tasks.values() if t.status == TaskStatus.SUCCEEDED]),
                "failed": len([t for t in self.tasks.values() if t.status == TaskStatus.FAILED]),
            },
            "recent_tasks": [
                t.to_dict() for t in list(self.tasks.values())[-10:]
            ],
            "timeline_count": len(self.timeline),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────────────

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
        # Register demo platforms
        _orchestrator.register_platform(Platform(
            id="ugv1", name="UGV Alpha", type=PlatformType.UGV,
            position=Position(x=0, y=0, z=0),
        ))
        _orchestrator.register_platform(Platform(
            id="ugv2", name="UGV Bravo", type=PlatformType.UGV,
            position=Position(x=5, y=0, z=0),
        ))
        _orchestrator.register_platform(Platform(
            id="ugv3", name="UGV Charlie", type=PlatformType.UGV,
            position=Position(x=10, y=0, z=0),
        ))
        _orchestrator.register_platform(Platform(
            id="uav1", name="UAV Delta", type=PlatformType.UAV,
            position=Position(x=0, y=0, z=15),
        ))
        _orchestrator.register_platform(Platform(
            id="uav2", name="UAV Echo", type=PlatformType.UAV,
            position=Position(x=5, y=0, z=20),
        ))
    return _orchestrator
