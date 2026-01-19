"""Tests for command validator."""

import pytest

from commander.core.models import Command
from commander.core.validator import CommandValidator


class TestCommandValidator:
    """Tests for CommandValidator."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.validator = CommandValidator()

    def test_valid_move_command(self) -> None:
        """Test validation of valid move command."""
        command = Command(
            id="cmd-1",
            type="move",
            target="platform-alpha",
            params={"x": 10, "y": 20},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is True
        assert error is None

    def test_invalid_command_type(self) -> None:
        """Test validation rejects invalid command type."""
        command = Command(
            id="cmd-1",
            type="invalid_type",
            target="platform-alpha",
            params={},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is False
        assert "Invalid command type" in error

    def test_missing_target(self) -> None:
        """Test validation rejects missing target."""
        command = Command(
            id="cmd-1",
            type="move",
            target="",
            params={"x": 10},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is False
        assert "target" in error.lower()

    def test_move_requires_coordinates(self) -> None:
        """Test move command requires at least one coordinate."""
        command = Command(
            id="cmd-1",
            type="move",
            target="platform-alpha",
            params={},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is False
        assert "coordinate" in error.lower()

    def test_valid_stop_command(self) -> None:
        """Test validation of stop command."""
        command = Command(
            id="cmd-1",
            type="stop",
            target="platform-alpha",
            params={},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is True

    def test_rotate_requires_angle(self) -> None:
        """Test rotate command requires angle."""
        command = Command(
            id="cmd-1",
            type="rotate",
            target="platform-alpha",
            params={},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is False

    def test_valid_rotate_with_degrees(self) -> None:
        """Test rotate command with degrees."""
        command = Command(
            id="cmd-1",
            type="rotate",
            target="platform-alpha",
            params={"degrees": 90},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is True

    def test_set_speed_requires_speed(self) -> None:
        """Test set_speed command requires speed parameter."""
        command = Command(
            id="cmd-1",
            type="set_speed",
            target="platform-alpha",
            params={},
        )
        is_valid, error = self.validator.validate(command)
        assert is_valid is False
        assert "speed" in error.lower()
