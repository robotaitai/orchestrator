"""Core data models for Commander."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────


class PlatformType(str, Enum):
    """Types of platforms (from PRD: 3 UGV + 2 UAV)."""

    UGV = "ugv"  # Ground robot
    UAV = "uav"  # Drone
    # Legacy aliases
    GROUND = "ugv"
    AERIAL = "uav"


class PlatformStatus(str, Enum):
    """Platform operational status."""

    IDLE = "idle"
    MOVING = "moving"
    EXECUTING = "executing"  # Running a command
    HOLDING = "holding"  # Hold position
    ERROR = "error"
    OFFLINE = "offline"  # Comms timeout


# ──────────────────────────────────────────────────────────────────────────────
# Geometry
# ──────────────────────────────────────────────────────────────────────────────


class Position(BaseModel):
    """3D position in meters."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def distance_to(self, other: "Position") -> float:
        """Calculate Euclidean distance to another position."""
        return (
            (self.x - other.x) ** 2
            + (self.y - other.y) ** 2
            + (self.z - other.z) ** 2
        ) ** 0.5

    def distance_2d(self, other: "Position") -> float:
        """Calculate 2D distance (ignoring z) to another position."""
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


class Velocity(BaseModel):
    """3D velocity in m/s."""

    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

    @property
    def speed(self) -> float:
        """Calculate scalar speed."""
        return (self.vx**2 + self.vy**2 + self.vz**2) ** 0.5


class Orientation(BaseModel):
    """3D orientation (Euler angles in degrees)."""

    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Platform
# ──────────────────────────────────────────────────────────────────────────────


class Platform(BaseModel):
    """A robotic platform (UGV or UAV)."""

    id: str
    name: str
    type: PlatformType
    position: Position = Field(default_factory=Position)
    velocity: Velocity = Field(default_factory=Velocity)
    orientation: Orientation = Field(default_factory=Orientation)
    status: PlatformStatus = PlatformStatus.IDLE

    # Comms tracking
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Simulated health
    battery_pct: float = 100.0
    health_ok: bool = True

    def seconds_since_heartbeat(self) -> float:
        """Calculate seconds since last heartbeat."""
        now = datetime.now(timezone.utc)
        return (now - self.last_heartbeat).total_seconds()


# ──────────────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────────────


class Command(BaseModel):
    """A command to be executed."""

    id: str
    type: str
    target: str  # Platform ID or pod ID
    params: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommandResult(BaseModel):
    """Result of command execution."""

    command_id: str
    success: bool
    message: str
    data: dict[str, Any] | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Fleet State
# ──────────────────────────────────────────────────────────────────────────────


class FleetState(BaseModel):
    """Current state of the entire fleet."""

    platforms: dict[str, Platform] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_platform(self, platform_id: str) -> Platform | None:
        """Get a platform by ID."""
        return self.platforms.get(platform_id)

    def get_all_positions(self) -> dict[str, Position]:
        """Get positions of all platforms."""
        return {pid: p.position for pid, p in self.platforms.items()}
