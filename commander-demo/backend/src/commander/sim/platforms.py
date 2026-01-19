"""Platform definitions for simulation."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PlatformModel(str, Enum):
    """Available platform models."""

    QUADROTOR = "quadrotor"
    GROUND_ROBOT = "ground_robot"
    BOAT = "boat"


@dataclass
class PlatformConfig:
    """Configuration for a simulated platform."""

    model: PlatformModel
    name: str
    initial_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    initial_orientation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mass: float = 1.0
    max_speed: float = 5.0


class SimulatedPlatform:
    """A platform in the simulation."""

    def __init__(self, config: PlatformConfig) -> None:
        """Initialize the simulated platform."""
        self.config = config
        self.position = list(config.initial_position)
        self.orientation = list(config.initial_orientation)
        self.velocity = [0.0, 0.0, 0.0]
        self.is_active = True

    def update(self, dt: float) -> None:
        """Update platform state."""
        # TODO: Implement physics update
        for i in range(3):
            self.position[i] += self.velocity[i] * dt

    def set_target(self, x: float, y: float, z: float) -> None:
        """Set target position."""
        # TODO: Implement path planning
        pass

    def stop(self) -> None:
        """Stop the platform."""
        self.velocity = [0.0, 0.0, 0.0]

    def get_state(self) -> dict[str, Any]:
        """Get current platform state."""
        return {
            "name": self.config.name,
            "model": self.config.model.value,
            "position": self.position,
            "orientation": self.orientation,
            "velocity": self.velocity,
            "is_active": self.is_active,
        }
