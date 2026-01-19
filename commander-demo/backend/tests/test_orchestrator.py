"""Tests for the orchestrator."""

import asyncio

import pytest

from commander.core.models import Command, Platform, PlatformType, Position
from commander.core.orchestrator import (
    EventType,
    Orchestrator,
    Task,
    TaskStatus,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def orchestrator() -> Orchestrator:
    """Create a test orchestrator."""
    orch = Orchestrator()
    # Register test platforms
    orch.register_platform(Platform(
        id="ugv1", name="UGV Alpha", type=PlatformType.UGV,
        position=Position(x=0, y=0, z=0),
    ))
    orch.register_platform(Platform(
        id="ugv2", name="UGV Bravo", type=PlatformType.UGV,
        position=Position(x=5, y=0, z=0),
    ))
    orch.register_platform(Platform(
        id="uav1", name="UAV Delta", type=PlatformType.UAV,
        position=Position(x=0, y=0, z=15),
    ))
    return orch


# ──────────────────────────────────────────────────────────────────────────────
# Platform Management Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPlatformManagement:
    """Tests for platform management."""

    def test_register_platform(self, orchestrator: Orchestrator):
        """Test registering a platform."""
        platform = Platform(
            id="new_platform",
            name="New Platform",
            type=PlatformType.UGV,
        )
        orchestrator.register_platform(platform)

        assert "new_platform" in orchestrator.fleet_state.platforms
        assert orchestrator.get_platform("new_platform") == platform

    def test_get_platform(self, orchestrator: Orchestrator):
        """Test getting a platform."""
        platform = orchestrator.get_platform("ugv1")
        assert platform is not None
        assert platform.name == "UGV Alpha"

    def test_get_unknown_platform(self, orchestrator: Orchestrator):
        """Test getting unknown platform returns None."""
        platform = orchestrator.get_platform("nonexistent")
        assert platform is None

    def test_resolve_all_targets(self, orchestrator: Orchestrator):
        """Test resolving 'all' target."""
        targets = orchestrator._resolve_targets("all")
        assert len(targets) == 3
        assert "ugv1" in targets
        assert "ugv2" in targets
        assert "uav1" in targets

    def test_resolve_ugv_pod(self, orchestrator: Orchestrator):
        """Test resolving 'ugv_pod' target."""
        targets = orchestrator._resolve_targets("ugv_pod")
        assert len(targets) == 2
        assert "ugv1" in targets
        assert "ugv2" in targets
        assert "uav1" not in targets

    def test_resolve_uav_pod(self, orchestrator: Orchestrator):
        """Test resolving 'uav_pod' target."""
        targets = orchestrator._resolve_targets("uav_pod")
        assert len(targets) == 1
        assert "uav1" in targets


# ──────────────────────────────────────────────────────────────────────────────
# Task Lifecycle Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTaskLifecycle:
    """Tests for task lifecycle."""

    @pytest.mark.asyncio
    async def test_create_task_from_command(self, orchestrator: Orchestrator):
        """Test creating a task from a command."""
        command = Command(
            id="cmd1",
            type="go_to",
            target="ugv1",
            params={"x": 10, "y": 20},
        )

        task = await orchestrator.execute_command(command)

        assert task.id.startswith("task_")
        assert task.command == "go_to"
        assert task.target == "ugv1"
        assert task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.SUCCEEDED)

    @pytest.mark.asyncio
    async def test_task_execution(self, orchestrator: Orchestrator):
        """Test task execution updates platform state."""
        await orchestrator.start()

        command = Command(
            id="cmd1",
            type="go_to",
            target="ugv1",
            params={"x": 25, "y": 35},
        )

        task = await orchestrator.execute_command(command)

        # Wait for task to complete
        await asyncio.sleep(0.5)

        await orchestrator.stop()

        # Check task completed
        assert task.status == TaskStatus.SUCCEEDED

        # Check platform moved
        platform = orchestrator.get_platform("ugv1")
        assert platform.position.x == 25
        assert platform.position.y == 35

    @pytest.mark.asyncio
    async def test_constraint_violation_fails_task(self, orchestrator: Orchestrator):
        """Test that constraint violation creates failed task."""
        # Try to move outside bounds
        command = Command(
            id="cmd1",
            type="go_to",
            target="ugv1",
            params={"x": 500, "y": 500},  # Way outside bounds
        )

        task = await orchestrator.execute_command(command)

        assert task.status == TaskStatus.FAILED
        assert "out of bounds" in task.error.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Command Handler Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCommandHandlers:
    """Tests for command handlers."""

    @pytest.mark.asyncio
    async def test_stop_command(self, orchestrator: Orchestrator):
        """Test stop command."""
        await orchestrator.start()

        command = Command(id="cmd1", type="stop", target="all", params={})
        task = await orchestrator.execute_command(command)

        await asyncio.sleep(0.3)
        await orchestrator.stop()

        assert task.status == TaskStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_hold_position_command(self, orchestrator: Orchestrator):
        """Test hold_position command."""
        await orchestrator.start()

        command = Command(
            id="cmd1",
            type="hold_position",
            target="ugv1",
            params={"duration_s": 0.1},
        )
        task = await orchestrator.execute_command(command)

        await asyncio.sleep(0.5)
        await orchestrator.stop()

        assert task.status == TaskStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_report_status_command(self, orchestrator: Orchestrator):
        """Test report_status command."""
        await orchestrator.start()

        command = Command(
            id="cmd1",
            type="report_status",
            target="all",
            params={},
        )
        task = await orchestrator.execute_command(command)

        await asyncio.sleep(0.3)
        await orchestrator.stop()

        assert task.status == TaskStatus.SUCCEEDED
        assert "status_report" in task.params
        assert "ugv1" in task.params["status_report"]

    @pytest.mark.asyncio
    async def test_form_formation_command(self, orchestrator: Orchestrator):
        """Test form_formation command."""
        await orchestrator.start()

        command = Command(
            id="cmd1",
            type="form_formation",
            target="ugv_pod",
            params={"formation": "line", "spacing_m": 5, "leader": "ugv1"},
        )
        task = await orchestrator.execute_command(command)

        await asyncio.sleep(0.3)
        await orchestrator.stop()

        assert task.status == TaskStatus.SUCCEEDED

        # Check formation (ugv2 should be behind ugv1)
        ugv1 = orchestrator.get_platform("ugv1")
        ugv2 = orchestrator.get_platform("ugv2")
        assert ugv2.position.x < ugv1.position.x  # Behind leader

    @pytest.mark.asyncio
    async def test_orbit_command_uav_only(self, orchestrator: Orchestrator):
        """Test orbit command only works for UAV."""
        await orchestrator.start()

        # Should succeed for UAV
        command = Command(
            id="cmd1",
            type="orbit",
            target="uav1",
            params={"center_x": 10, "center_y": 10, "radius_m": 5, "altitude_m": 20},
        )
        task = await orchestrator.execute_command(command)

        await asyncio.sleep(0.3)
        await orchestrator.stop()

        assert task.status == TaskStatus.SUCCEEDED


# ──────────────────────────────────────────────────────────────────────────────
# Timeline Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTimeline:
    """Tests for timeline events."""

    def test_platform_registration_emits_event(self, orchestrator: Orchestrator):
        """Test that registering platform emits event."""
        # Clear existing events
        orchestrator.timeline.clear()

        platform = Platform(
            id="new_ugv",
            name="New UGV",
            type=PlatformType.UGV,
        )
        orchestrator.register_platform(platform)

        assert len(orchestrator.timeline) == 1
        assert orchestrator.timeline[0].type == EventType.SYSTEM

    @pytest.mark.asyncio
    async def test_task_lifecycle_events(self, orchestrator: Orchestrator):
        """Test task lifecycle emits events."""
        orchestrator.timeline.clear()
        await orchestrator.start()

        command = Command(
            id="cmd1",
            type="stop",
            target="ugv1",
            params={},
        )
        await orchestrator.execute_command(command)

        await asyncio.sleep(0.3)
        await orchestrator.stop()

        # Should have: TASK_CREATED, TASK_STARTED, TASK_SUCCEEDED
        event_types = [e.type for e in orchestrator.timeline]
        assert EventType.TASK_CREATED in event_types
        assert EventType.TASK_STARTED in event_types
        assert EventType.TASK_SUCCEEDED in event_types

    def test_get_timeline(self, orchestrator: Orchestrator):
        """Test getting timeline."""
        timeline = orchestrator.get_timeline(limit=10)
        assert isinstance(timeline, list)
        for event in timeline:
            assert "id" in event
            assert "type" in event
            assert "timestamp" in event


# ──────────────────────────────────────────────────────────────────────────────
# Status Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestStatus:
    """Tests for status endpoint."""

    def test_get_status(self, orchestrator: Orchestrator):
        """Test getting orchestrator status."""
        status = orchestrator.get_status()

        assert "platforms" in status
        assert "tasks" in status
        assert "recent_tasks" in status
        assert "timeline_count" in status

        assert len(status["platforms"]) == 3
        assert status["tasks"]["total"] >= 0

    @pytest.mark.asyncio
    async def test_status_includes_task_counts(self, orchestrator: Orchestrator):
        """Test status includes task counts."""
        await orchestrator.start()

        command = Command(id="cmd1", type="stop", target="ugv1", params={})
        await orchestrator.execute_command(command)

        await asyncio.sleep(0.3)
        await orchestrator.stop()

        status = orchestrator.get_status()
        assert status["tasks"]["total"] >= 1
        assert status["tasks"]["succeeded"] >= 1
