"""Platform controllers for simulation."""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class Controller(ABC):
    """Abstract base class for controllers."""

    @abstractmethod
    def compute(self, state: dict[str, Any], target: dict[str, Any]) -> np.ndarray:
        """Compute control output."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset controller state."""
        pass


class PIDController(Controller):
    """PID controller implementation."""

    def __init__(
        self,
        kp: float = 1.0,
        ki: float = 0.0,
        kd: float = 0.0,
        output_limits: tuple[float, float] | None = None,
    ) -> None:
        """Initialize PID controller."""
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limits = output_limits or (-float("inf"), float("inf"))

        self._integral = 0.0
        self._prev_error = 0.0

    def compute(self, state: dict[str, Any], target: dict[str, Any]) -> np.ndarray:
        """Compute PID control output."""
        current = np.array(state.get("position", [0, 0, 0]))
        setpoint = np.array(target.get("position", [0, 0, 0]))

        error = setpoint - current
        error_magnitude = float(np.linalg.norm(error))

        # Proportional
        p_term = self.kp * error_magnitude

        # Integral
        self._integral += error_magnitude
        i_term = self.ki * self._integral

        # Derivative
        d_term = self.kd * (error_magnitude - self._prev_error)
        self._prev_error = error_magnitude

        # Total output
        output = p_term + i_term + d_term
        output = np.clip(output, *self.output_limits)

        # Direction vector
        if error_magnitude > 0:
            direction = error / error_magnitude
        else:
            direction = np.zeros(3)

        return direction * output

    def reset(self) -> None:
        """Reset controller state."""
        self._integral = 0.0
        self._prev_error = 0.0


class PositionController:
    """High-level position controller for platforms."""

    def __init__(self) -> None:
        """Initialize position controller."""
        self.pid = PIDController(kp=2.0, ki=0.1, kd=0.5, output_limits=(-10.0, 10.0))

    def compute_velocity(
        self, current_position: list[float], target_position: list[float]
    ) -> list[float]:
        """Compute velocity to reach target position."""
        state = {"position": current_position}
        target = {"position": target_position}
        velocity = self.pid.compute(state, target)
        return velocity.tolist()

    def reset(self) -> None:
        """Reset controller."""
        self.pid.reset()
