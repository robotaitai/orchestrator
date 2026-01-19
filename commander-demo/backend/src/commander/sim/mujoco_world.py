"""
MuJoCo World Simulation

Wraps MuJoCo physics simulation for the Commander demo.
Manages the simulation loop, platform state updates, and pose streaming.
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

import numpy as np

# MuJoCo is optional - may not be available on all systems
try:
    import mujoco
    MUJOCO_AVAILABLE = True
except ImportError as e:
    mujoco = None  # type: ignore
    MUJOCO_AVAILABLE = False
    logging.warning(f"MuJoCo not available: {e}")

from commander.core.models import Platform, PlatformStatus, PlatformType, Position, Velocity
from commander.settings import settings

logger = logging.getLogger("commander.sim.mujoco")

# Path to world XML
WORLD_XML = Path(__file__).parent / "assets" / "world.xml"


@dataclass
class PlatformState:
    """Runtime state for a platform in the simulation."""
    
    id: str
    type: PlatformType
    body_id: int  # MuJoCo body ID
    
    # Current state (from MuJoCo)
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    orientation: float = 0.0  # Heading in radians (for UGV)
    
    # Target state (from controllers)
    target_position: np.ndarray | None = None
    target_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    
    # Controller mode
    mode: str = "idle"  # idle, go_to, hold, orbit, follow, formation
    mode_params: dict[str, Any] = field(default_factory=dict)
    
    # Status
    status: PlatformStatus = PlatformStatus.IDLE


class MuJoCoWorld:
    """
    MuJoCo physics simulation world.
    
    Manages:
    - Loading and stepping the MuJoCo model
    - Platform state tracking
    - Control input application
    - Pose streaming via callbacks
    """
    
    def __init__(self) -> None:
        """Initialize the MuJoCo world."""
        self.model: mujoco.MjModel | None = None
        self.data: mujoco.MjData | None = None
        
        # Platform states
        self.platforms: dict[str, PlatformState] = {}
        
        # Simulation parameters
        self.dt = settings.sim_tick_rate
        self.realtime = settings.sim_realtime
        
        # Control parameters
        self.ugv_max_speed = 5.0  # m/s
        self.ugv_max_accel = 2.0  # m/s²
        self.uav_max_speed = 15.0  # m/s
        self.uav_max_accel = 5.0  # m/s²
        
        # Callbacks for state updates
        self._pose_callbacks: list[Callable[[dict[str, dict]], Coroutine]] = []
        
        # Simulation loop task
        self._sim_task: asyncio.Task | None = None
        self._running = False
        
        logger.info("MuJoCoWorld initialized")
    
    def load(self) -> None:
        """Load the MuJoCo model from XML."""
        if not MUJOCO_AVAILABLE:
            logger.warning("MuJoCo not available - using kinematic-only simulation")
            self._init_platforms_kinematic()
            return
        
        if not WORLD_XML.exists():
            raise FileNotFoundError(f"World XML not found: {WORLD_XML}")
        
        logger.info(f"Loading MuJoCo model from {WORLD_XML}")
        self.model = mujoco.MjModel.from_xml_path(str(WORLD_XML))
        self.data = mujoco.MjData(self.model)
        
        # Initialize platform states
        self._init_platforms()
        
        logger.info(f"MuJoCo model loaded: {len(self.platforms)} platforms")
    
    def _init_platforms_kinematic(self) -> None:
        """Initialize platforms for kinematic-only mode (no MuJoCo)."""
        platform_configs = [
            ("ugv1", PlatformType.UGV, np.array([0.0, 0.0, 0.25])),
            ("ugv2", PlatformType.UGV, np.array([5.0, 0.0, 0.25])),
            ("ugv3", PlatformType.UGV, np.array([10.0, 0.0, 0.25])),
            ("uav1", PlatformType.UAV, np.array([0.0, 0.0, 15.0])),
            ("uav2", PlatformType.UAV, np.array([5.0, 0.0, 20.0])),
        ]
        
        for name, ptype, pos in platform_configs:
            self.platforms[name] = PlatformState(
                id=name,
                type=ptype,
                body_id=-1,  # No MuJoCo body
                position=pos,
            )
            logger.debug(f"Platform {name} initialized (kinematic) at {pos}")
    
    def _init_platforms(self) -> None:
        """Initialize platform state from the loaded model."""
        platform_configs = [
            ("ugv1", PlatformType.UGV),
            ("ugv2", PlatformType.UGV),
            ("ugv3", PlatformType.UGV),
            ("uav1", PlatformType.UAV),
            ("uav2", PlatformType.UAV),
        ]
        
        for name, ptype in platform_configs:
            try:
                body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
                if body_id == -1:
                    logger.warning(f"Platform body not found: {name}")
                    continue
                
                # Get initial position from model
                pos = self.data.xpos[body_id].copy()
                
                self.platforms[name] = PlatformState(
                    id=name,
                    type=ptype,
                    body_id=body_id,
                    position=pos,
                )
                logger.debug(f"Platform {name} initialized at {pos}")
                
            except Exception as e:
                logger.error(f"Failed to init platform {name}: {e}")
    
    def get_platform_pose(self, platform_id: str) -> dict[str, Any] | None:
        """Get current pose of a platform."""
        state = self.platforms.get(platform_id)
        if not state:
            return None
        
        return {
            "x": float(state.position[0]),
            "y": float(state.position[1]),
            "z": float(state.position[2]),
            "heading": float(state.orientation),
            "status": state.status.value,
            "mode": state.mode,
        }
    
    def get_all_poses(self) -> dict[str, dict[str, Any]]:
        """Get poses of all platforms."""
        return {
            pid: self.get_platform_pose(pid)
            for pid in self.platforms
        }
    
    # ──────────────────────────────────────────────────────────────────────────
    # Controller Commands
    # ──────────────────────────────────────────────────────────────────────────
    
    def command_go_to(self, platform_id: str, x: float, y: float, z: float | None = None) -> bool:
        """Command a platform to move to a target position."""
        state = self.platforms.get(platform_id)
        if not state:
            return False
        
        # Set target
        target_z = z if z is not None else (state.position[2] if state.type == PlatformType.UAV else 0.25)
        state.target_position = np.array([x, y, target_z])
        state.mode = "go_to"
        state.mode_params = {"target": (x, y, target_z)}
        state.status = PlatformStatus.MOVING
        
        logger.info(f"Platform {platform_id} commanded to go to ({x}, {y}, {target_z})")
        return True
    
    def command_hold(self, platform_id: str) -> bool:
        """Command a platform to hold its current position."""
        state = self.platforms.get(platform_id)
        if not state:
            return False
        
        state.target_position = state.position.copy()
        state.target_velocity = np.zeros(3)
        state.mode = "hold"
        state.mode_params = {}
        state.status = PlatformStatus.HOLDING
        
        logger.info(f"Platform {platform_id} commanded to hold at {state.position}")
        return True
    
    def command_orbit(
        self, 
        platform_id: str, 
        center_x: float, 
        center_y: float, 
        radius: float, 
        altitude: float,
        angular_speed: float = 0.2,  # rad/s
    ) -> bool:
        """Command a UAV to orbit around a point."""
        state = self.platforms.get(platform_id)
        if not state or state.type != PlatformType.UAV:
            return False
        
        state.mode = "orbit"
        state.mode_params = {
            "center": np.array([center_x, center_y, altitude]),
            "radius": radius,
            "angular_speed": angular_speed,
            "phase": 0.0,  # Will be updated in control loop
        }
        state.status = PlatformStatus.EXECUTING
        
        logger.info(f"UAV {platform_id} commanded to orbit ({center_x}, {center_y}) r={radius}m alt={altitude}m")
        return True
    
    def command_follow(
        self, 
        platform_id: str, 
        leader_id: str, 
        gap: float,
    ) -> bool:
        """Command a platform to follow another platform."""
        state = self.platforms.get(platform_id)
        leader = self.platforms.get(leader_id)
        if not state or not leader:
            return False
        
        state.mode = "follow"
        state.mode_params = {
            "leader": leader_id,
            "gap": gap,
        }
        state.status = PlatformStatus.EXECUTING
        
        logger.info(f"Platform {platform_id} commanded to follow {leader_id} with gap {gap}m")
        return True
    
    def command_formation(
        self,
        platform_id: str,
        leader_id: str,
        offset: tuple[float, float, float],
    ) -> bool:
        """Command a platform to maintain formation offset from leader."""
        state = self.platforms.get(platform_id)
        leader = self.platforms.get(leader_id)
        if not state or not leader:
            return False
        
        state.mode = "formation"
        state.mode_params = {
            "leader": leader_id,
            "offset": np.array(offset),
        }
        state.status = PlatformStatus.EXECUTING
        
        logger.info(f"Platform {platform_id} in formation with {leader_id}, offset {offset}")
        return True
    
    def command_stop(self, platform_id: str) -> bool:
        """Immediately stop a platform."""
        state = self.platforms.get(platform_id)
        if not state:
            return False
        
        state.target_position = None
        state.target_velocity = np.zeros(3)
        state.mode = "idle"
        state.mode_params = {}
        state.status = PlatformStatus.IDLE
        
        logger.info(f"Platform {platform_id} stopped")
        return True
    
    # ──────────────────────────────────────────────────────────────────────────
    # Simulation Loop
    # ──────────────────────────────────────────────────────────────────────────
    
    async def start(self) -> None:
        """Start the simulation loop."""
        if self._sim_task is not None:
            return
        
        if self.model is None:
            self.load()
        
        self._running = True
        self._sim_task = asyncio.create_task(self._simulation_loop())
        logger.info("MuJoCo simulation loop started")
        
        # Start renderer if MuJoCo is available
        if MUJOCO_AVAILABLE and self.model is not None and self.data is not None:
            try:
                from commander.sim.renderer import get_renderer
                renderer = get_renderer()
                if renderer.attach(self.model, self.data):
                    await renderer.start()
                    logger.info("MuJoCo renderer started")
            except Exception as e:
                logger.warning(f"Could not start renderer: {e}")
    
    async def stop(self) -> None:
        """Stop the simulation loop and renderer."""
        self._running = False
        
        # Stop renderer
        if MUJOCO_AVAILABLE:
            try:
                from commander.sim.renderer import get_renderer
                renderer = get_renderer()
                await renderer.stop()
            except Exception:
                pass
        
        if self._sim_task:
            self._sim_task.cancel()
            try:
                await self._sim_task
            except asyncio.CancelledError:
                pass
            self._sim_task = None
        logger.info("MuJoCo simulation loop stopped")
    
    async def _simulation_loop(self) -> None:
        """Main simulation loop."""
        last_time = time.time()
        broadcast_interval = 0.1  # Send updates every 100ms
        last_broadcast = 0.0
        
        while self._running:
            try:
                current_time = time.time()
                last_time = current_time
                
                # Run controller update for each platform
                self._update_controllers(self.dt)
                
                # Step MuJoCo physics (if available)
                if MUJOCO_AVAILABLE and self.model is not None and self.data is not None:
                    mujoco.mj_step(self.model, self.data)
                    # Sync platform states from MuJoCo
                    self._sync_platform_states()
                
                # Broadcast poses periodically
                if current_time - last_broadcast >= broadcast_interval:
                    await self._broadcast_poses()
                    last_broadcast = current_time
                
                # Sleep to maintain tick rate
                if self.realtime:
                    elapsed = time.time() - current_time
                    sleep_time = max(0, self.dt - elapsed)
                    await asyncio.sleep(sleep_time)
                else:
                    await asyncio.sleep(0)  # Yield to event loop
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Simulation loop error: {e}")
                await asyncio.sleep(0.1)
    
    def _update_controllers(self, dt: float) -> None:
        """Update all platform controllers."""
        for state in self.platforms.values():
            if state.mode == "idle":
                continue
            elif state.mode == "go_to":
                self._control_go_to(state, dt)
            elif state.mode == "hold":
                self._control_hold(state, dt)
            elif state.mode == "orbit":
                self._control_orbit(state, dt)
            elif state.mode == "follow":
                self._control_follow(state, dt)
            elif state.mode == "formation":
                self._control_formation(state, dt)
    
    def _control_go_to(self, state: PlatformState, dt: float) -> None:
        """Go-to controller: move towards target position."""
        if state.target_position is None:
            state.mode = "idle"
            state.status = PlatformStatus.IDLE
            return
        
        # Calculate direction to target
        diff = state.target_position - state.position
        distance = np.linalg.norm(diff)
        
        # Check if arrived
        arrival_threshold = 0.5 if state.type == PlatformType.UGV else 1.0
        if distance < arrival_threshold:
            state.mode = "idle"
            state.status = PlatformStatus.IDLE
            state.target_position = None
            logger.info(f"Platform {state.id} arrived at target")
            return
        
        # Calculate desired velocity (towards target)
        max_speed = self.ugv_max_speed if state.type == PlatformType.UGV else self.uav_max_speed
        
        # Slow down near target
        speed = min(max_speed, distance * 1.0)  # P-controller
        direction = diff / distance
        desired_velocity = direction * speed
        
        # Apply acceleration limits
        max_accel = self.ugv_max_accel if state.type == PlatformType.UGV else self.uav_max_accel
        velocity_diff = desired_velocity - state.velocity
        accel_magnitude = np.linalg.norm(velocity_diff)
        if accel_magnitude > max_accel * dt:
            velocity_diff = velocity_diff / accel_magnitude * max_accel * dt
        
        state.target_velocity = state.velocity + velocity_diff
        
        # For UGV, update heading
        if state.type == PlatformType.UGV and distance > 0.1:
            state.orientation = math.atan2(diff[1], diff[0])
        
        # Apply velocity to position (kinematics, not full dynamics)
        self._apply_velocity(state, dt)
    
    def _control_hold(self, state: PlatformState, dt: float) -> None:
        """Hold controller: maintain current position."""
        # Simple P-controller to return to hold position
        if state.target_position is not None:
            diff = state.target_position - state.position
            state.target_velocity = diff * 2.0  # P-gain
            
            # Clamp velocity
            max_speed = 1.0  # Slow corrections
            speed = np.linalg.norm(state.target_velocity)
            if speed > max_speed:
                state.target_velocity = state.target_velocity / speed * max_speed
        else:
            state.target_velocity = np.zeros(3)
        
        self._apply_velocity(state, dt)
    
    def _control_orbit(self, state: PlatformState, dt: float) -> None:
        """Orbit controller: UAV circles around a point."""
        params = state.mode_params
        center = params["center"]
        radius = params["radius"]
        angular_speed = params["angular_speed"]
        
        # Update phase
        params["phase"] += angular_speed * dt
        phase = params["phase"]
        
        # Calculate target position on circle
        target_x = center[0] + radius * math.cos(phase)
        target_y = center[1] + radius * math.sin(phase)
        target_z = center[2]
        
        target = np.array([target_x, target_y, target_z])
        diff = target - state.position
        
        # Move towards orbit position
        max_speed = self.uav_max_speed * 0.5  # Slower for smooth orbit
        distance = np.linalg.norm(diff)
        if distance > 0.1:
            state.target_velocity = diff / distance * min(max_speed, distance * 2.0)
        else:
            # On orbit path, maintain tangential velocity
            tangent = np.array([-math.sin(phase), math.cos(phase), 0])
            state.target_velocity = tangent * angular_speed * radius
        
        self._apply_velocity(state, dt)
    
    def _control_follow(self, state: PlatformState, dt: float) -> None:
        """Follow controller: maintain gap behind leader."""
        leader_id = state.mode_params.get("leader")
        gap = state.mode_params.get("gap", 3.0)
        
        leader = self.platforms.get(leader_id)
        if not leader:
            return
        
        # Calculate follow position (behind leader based on leader's heading)
        leader_heading = leader.orientation
        offset = np.array([
            -gap * math.cos(leader_heading),
            -gap * math.sin(leader_heading),
            0,
        ])
        target = leader.position + offset
        
        # Move towards follow position
        diff = target - state.position
        distance = np.linalg.norm(diff)
        
        max_speed = self.ugv_max_speed
        if distance > 0.1:
            state.target_velocity = diff / distance * min(max_speed, distance * 1.5)
        else:
            state.target_velocity = leader.velocity.copy()
        
        self._apply_velocity(state, dt)
    
    def _control_formation(self, state: PlatformState, dt: float) -> None:
        """Formation controller: maintain offset from leader."""
        leader_id = state.mode_params.get("leader")
        offset = state.mode_params.get("offset", np.zeros(3))
        
        leader = self.platforms.get(leader_id)
        if not leader:
            return
        
        # Calculate formation position
        target = leader.position + offset
        diff = target - state.position
        distance = np.linalg.norm(diff)
        
        max_speed = self.ugv_max_speed if state.type == PlatformType.UGV else self.uav_max_speed
        if distance > 0.1:
            state.target_velocity = diff / distance * min(max_speed, distance * 1.5)
        else:
            state.target_velocity = leader.velocity.copy()
        
        self._apply_velocity(state, dt)
    
    def _apply_velocity(self, state: PlatformState, dt: float) -> None:
        """Apply velocity to update position and sync with MuJoCo."""
        state.velocity = state.target_velocity.copy()
        state.position = state.position + state.velocity * dt
        
        # For UGV, clamp to ground
        if state.type == PlatformType.UGV:
            state.position[2] = 0.25  # UGV height
        
        # Update MuJoCo body position
        self._set_body_position(state.id, state.position)
    
    def _set_body_position(self, body_name: str, position: np.ndarray) -> None:
        """Set a body's position in MuJoCo."""
        state = self.platforms.get(body_name)
        if not state:
            return
        
        # If MuJoCo not available, position is already set in state
        if not MUJOCO_AVAILABLE or self.model is None or self.data is None:
            return
        
        # Find the joint for this body
        joint_name = f"{body_name}_joint"
        try:
            joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id == -1:
                return
            
            # Get qpos address for this joint
            qpos_adr = self.model.jnt_qposadr[joint_id]
            
            # Set position (first 3 components of freejoint qpos)
            self.data.qpos[qpos_adr:qpos_adr + 3] = position
            
            # Set orientation (quaternion, next 4 components)
            # For UGV, set based on heading
            if state.type == PlatformType.UGV:
                # Convert heading to quaternion (rotation around Z)
                half_angle = state.orientation / 2
                self.data.qpos[qpos_adr + 3] = math.cos(half_angle)  # w
                self.data.qpos[qpos_adr + 4] = 0  # x
                self.data.qpos[qpos_adr + 5] = 0  # y
                self.data.qpos[qpos_adr + 6] = math.sin(half_angle)  # z
            
        except Exception as e:
            logger.debug(f"Could not set body position for {body_name}: {e}")
    
    def _sync_platform_states(self) -> None:
        """Sync platform states from MuJoCo data."""
        if self.model is None or self.data is None:
            return
        
        for state in self.platforms.values():
            try:
                # Read position from MuJoCo
                pos = self.data.xpos[state.body_id].copy()
                state.position = pos
            except Exception:
                pass
    
    async def _broadcast_poses(self) -> None:
        """Broadcast current poses to all registered callbacks."""
        poses = self.get_all_poses()
        for callback in self._pose_callbacks:
            try:
                await callback(poses)
            except Exception as e:
                logger.error(f"Pose callback error: {e}")
    
    def on_poses(self, callback: Callable[[dict[str, dict]], Coroutine]) -> None:
        """Register a callback for pose updates."""
        self._pose_callbacks.append(callback)
    
    # ──────────────────────────────────────────────────────────────────────────
    # Export to Platform objects
    # ──────────────────────────────────────────────────────────────────────────
    
    def get_platform_models(self) -> list[Platform]:
        """Get Platform model objects for all platforms."""
        from datetime import datetime, timezone
        
        platforms = []
        for state in self.platforms.values():
            platforms.append(Platform(
                id=state.id,
                name=_platform_names.get(state.id, state.id),
                type=state.type,
                status=state.status,
                position=Position(
                    x=float(state.position[0]),
                    y=float(state.position[1]),
                    z=float(state.position[2]),
                ),
                velocity=Velocity(
                    x=float(state.velocity[0]),
                    y=float(state.velocity[1]),
                    z=float(state.velocity[2]),
                ),
                battery_pct=100.0,
                health_ok=True,
                last_heartbeat=datetime.now(timezone.utc),
            ))
        return platforms


# Platform display names
_platform_names = {
    "ugv1": "UGV Alpha",
    "ugv2": "UGV Bravo",
    "ugv3": "UGV Charlie",
    "uav1": "UAV Delta",
    "uav2": "UAV Echo",
}


# Global instance
_world: MuJoCoWorld | None = None


def get_mujoco_world() -> MuJoCoWorld:
    """Get or create the global MuJoCo world instance."""
    global _world
    if _world is None:
        _world = MuJoCoWorld()
    return _world
