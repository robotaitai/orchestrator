"""Command validation."""

from typing import Any

from commander.core.models import Command


class ValidationError(Exception):
    """Validation error."""

    def __init__(self, message: str, field: str | None = None) -> None:
        """Initialize the error."""
        self.message = message
        self.field = field
        super().__init__(message)


class CommandValidator:
    """Validate commands before execution."""

    VALID_COMMAND_TYPES = {"move", "rotate", "stop", "set_speed"}

    def validate(self, command: Command) -> tuple[bool, str | None]:
        """
        Validate a command.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check command type
        if command.type not in self.VALID_COMMAND_TYPES:
            return False, f"Invalid command type: {command.type}"

        # Check target
        if not command.target:
            return False, "Command target is required"

        # Type-specific validation
        validation_method = getattr(self, f"_validate_{command.type}", None)
        if validation_method:
            return validation_method(command.params)

        return True, None

    def _validate_move(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate move command parameters."""
        if "x" not in params and "y" not in params and "z" not in params:
            return False, "Move command requires at least one coordinate (x, y, or z)"
        return True, None

    def _validate_rotate(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate rotate command parameters."""
        if "degrees" not in params and "radians" not in params:
            return False, "Rotate command requires degrees or radians"
        return True, None

    def _validate_stop(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate stop command parameters."""
        return True, None

    def _validate_set_speed(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate set_speed command parameters."""
        if "speed" not in params:
            return False, "set_speed command requires speed parameter"
        return True, None
