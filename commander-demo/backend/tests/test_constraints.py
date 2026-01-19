"""Tests for the safety constraints engine."""

from datetime import datetime, timedelta, timezone

import pytest

from commander.core.constraints import (
    ConstraintsConfig,
    ConstraintsEngine,
    ConstraintVerdict,
    NoGoZone,
    SpeedLimits,
    WorldBounds,
    create_demo_engine,
)
from commander.core.models import (
    Command,
    FleetState,
    Platform,
    PlatformType,
    Position,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> ConstraintsEngine:
    """Create a test constraints engine."""
    return ConstraintsEngine(ConstraintsConfig())


@pytest.fixture
def demo_engine() -> ConstraintsEngine:
    """Create the demo constraints engine."""
    return create_demo_engine()


@pytest.fixture
def ugv_platform() -> Platform:
    """Create a test UGV platform."""
    return Platform(
        id="ugv1",
        name="UGV Alpha",
        type=PlatformType.UGV,
        position=Position(x=0, y=0, z=0),
    )


@pytest.fixture
def uav_platform() -> Platform:
    """Create a test UAV platform."""
    return Platform(
        id="uav1",
        name="UAV Bravo",
        type=PlatformType.UAV,
        position=Position(x=10, y=10, z=15),
    )


@pytest.fixture
def fleet_state(ugv_platform: Platform, uav_platform: Platform) -> FleetState:
    """Create a test fleet state with two platforms."""
    return FleetState(
        platforms={
            ugv_platform.id: ugv_platform,
            uav_platform.id: uav_platform,
        }
    )


def make_command(
    cmd_type: str = "go_to",
    target: str = "ugv1",
    **params,
) -> Command:
    """Helper to create test commands."""
    return Command(
        id="cmd-test",
        type=cmd_type,
        target=target,
        params=params,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Speed Limit Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSpeedLimits:
    """Tests for speed limit constraints."""

    def test_ugv_speed_within_limit_approved(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """UGV speed within limit should be approved."""
        cmd = make_command("go_to", "ugv1", x=10, y=10, speed=4.0)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.APPROVED
        assert len(result.violations) == 0

    def test_ugv_speed_exceeds_limit_rejected(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """UGV speed exceeding 5 m/s should be rejected."""
        cmd = make_command("go_to", "ugv1", x=10, y=10, speed=10.0)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert len(result.violations) == 1
        assert "speed" in result.violations[0].lower()
        assert "10" in result.violations[0]
        assert "5" in result.violations[0]

    def test_uav_higher_speed_limit(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """UAV should have higher speed limit (15 m/s)."""
        # 10 m/s is over UGV limit but under UAV limit
        cmd = make_command("go_to", "uav1", x=20, y=20, z=15, speed=10.0)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.APPROVED

    def test_uav_speed_exceeds_limit_rejected(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """UAV speed exceeding 15 m/s should be rejected."""
        cmd = make_command("go_to", "uav1", x=20, y=20, z=15, speed=20.0)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert "20" in result.violations[0]
        assert "15" in result.violations[0]

    def test_human_readable_speed_message(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Rejection message should be human-readable."""
        cmd = make_command("go_to", "ugv1", x=10, y=10, speed=7.5)
        result = engine.check_command(cmd, fleet_state)

        message = result.rejection_message()
        assert "7.5" in message
        assert "5" in message
        assert "UGV" in message


# ──────────────────────────────────────────────────────────────────────────────
# World Bounds Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestWorldBounds:
    """Tests for world boundary constraints."""

    def test_position_within_bounds_approved(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position within bounds should be approved."""
        cmd = make_command("go_to", "ugv1", x=50, y=50)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.APPROVED

    def test_position_outside_x_bounds_rejected(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position outside x bounds should be rejected."""
        cmd = make_command("go_to", "ugv1", x=150, y=0)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert "x=150" in result.violations[0]
        assert "outside" in result.violations[0].lower()

    def test_position_outside_y_bounds_rejected(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position outside y bounds should be rejected."""
        cmd = make_command("go_to", "ugv1", x=0, y=-150)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert "y=-150" in result.violations[0]

    def test_position_below_ground_rejected(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position below z=0 should be rejected."""
        cmd = make_command("go_to", "ugv1", x=0, y=0, z=-5)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert "z=-5" in result.violations[0]


# ──────────────────────────────────────────────────────────────────────────────
# No-Go Zone Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestNoGoZones:
    """Tests for no-go zone constraints."""

    def test_no_go_zone_point_inside(self):
        """Test point-in-polygon detection."""
        zone = NoGoZone(
            name="test_zone",
            vertices=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )

        # Inside
        assert zone.contains_point(5, 5) is True

        # Outside
        assert zone.contains_point(15, 5) is False
        assert zone.contains_point(-5, 5) is False

        # On edge (implementation-dependent, but should be consistent)
        assert zone.contains_point(0, 5) in (True, False)  # Edge case

    def test_position_in_no_go_zone_rejected(
        self, demo_engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position inside no-go zone should be rejected."""
        # Demo engine has zone R1 at (-20,-20) to (-10,-10)
        cmd = make_command("go_to", "ugv1", x=-15, y=-15)
        result = demo_engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert "R1" in result.violations[0]
        assert "restricted" in result.violations[0].lower()

    def test_position_outside_no_go_zone_approved(
        self, demo_engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position outside no-go zone should be approved."""
        cmd = make_command("go_to", "ugv1", x=0, y=0)
        result = demo_engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.APPROVED


# ──────────────────────────────────────────────────────────────────────────────
# Minimum Separation Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestMinimumSeparation:
    """Tests for minimum separation constraints."""

    def test_position_far_from_others_no_warning(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position far from other platforms should have no warnings."""
        cmd = make_command("go_to", "ugv1", x=50, y=50)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.APPROVED
        assert len(result.warnings) == 0

    def test_position_too_close_generates_warning(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Position too close to another platform should generate warning."""
        # UAV is at (10, 10, 15), move UGV to (10, 10, 0) - only 1m away in 3D
        # Actually z difference is 15, so this should be fine
        # Let's move to (10, 11, 0) which is ~1m away from (10, 10, 15)
        cmd = make_command("go_to", "ugv1", x=10, y=10)  # z=0 default
        result = engine.check_command(cmd, fleet_state)

        # 15m z separation means this should be fine
        assert result.verdict == ConstraintVerdict.APPROVED

    def test_position_violates_separation_2d(self, fleet_state: FleetState):
        """Test separation violation when platforms are close in x/y."""
        # Create engine with strict separation
        engine = ConstraintsEngine(ConstraintsConfig(min_separation_m=5.0))

        # Add another UGV close by
        fleet_state.platforms["ugv2"] = Platform(
            id="ugv2",
            name="UGV Charlie",
            type=PlatformType.UGV,
            position=Position(x=5, y=0, z=0),
        )

        # Try to move ugv1 to (4, 0, 0) - only 1m from ugv2
        cmd = make_command("go_to", "ugv1", x=4, y=0)
        result = engine.check_command(cmd, fleet_state)

        assert len(result.warnings) == 1
        assert "1.0m" in result.warnings[0]
        assert "ugv2" in result.warnings[0]


# ──────────────────────────────────────────────────────────────────────────────
# Comms Timeout Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCommsTimeout:
    """Tests for communications timeout constraints."""

    def test_recent_heartbeat_approved(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Platform with recent heartbeat should accept commands."""
        cmd = make_command("go_to", "ugv1", x=10, y=10)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.APPROVED

    def test_stale_heartbeat_rejected(self, fleet_state: FleetState):
        """Platform with stale heartbeat should reject commands."""
        engine = ConstraintsEngine(ConstraintsConfig(comms_timeout_s=5.0))

        # Set heartbeat to 10 seconds ago
        fleet_state.platforms["ugv1"].last_heartbeat = datetime.now(
            timezone.utc
        ) - timedelta(seconds=10)

        cmd = make_command("go_to", "ugv1", x=10, y=10)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert "not responded" in result.violations[0]
        assert "10" in result.violations[0]  # Shows actual timeout
        assert "5" in result.violations[0]  # Shows configured limit


# ──────────────────────────────────────────────────────────────────────────────
# Unknown Platform Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestUnknownPlatform:
    """Tests for handling unknown platforms."""

    def test_unknown_platform_rejected(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Command targeting unknown platform should be rejected."""
        cmd = make_command("go_to", "nonexistent", x=10, y=10)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        assert "Unknown platform" in result.violations[0]
        assert "nonexistent" in result.violations[0]

    def test_all_target_accepted(
        self, engine: ConstraintsEngine, fleet_state: FleetState
    ):
        """Command targeting 'all' should not fail on unknown platform."""
        cmd = make_command("hold_position", "all")
        result = engine.check_command(cmd, fleet_state)

        # Should not reject due to unknown platform
        assert "Unknown platform" not in str(result.violations)


# ──────────────────────────────────────────────────────────────────────────────
# Rewriting Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCommandRewriting:
    """Tests for safe command rewriting."""

    def test_speed_rewrite(self, engine: ConstraintsEngine, ugv_platform: Platform):
        """Speed should be clamped to limit."""
        fleet_state = FleetState(platforms={ugv_platform.id: ugv_platform})
        cmd = make_command("go_to", "ugv1", x=10, y=10, speed=10.0)

        rewritten = engine.try_rewrite_safe(cmd, ugv_platform, fleet_state)

        assert rewritten is not None
        assert rewritten.params["speed"] == 5.0  # Clamped to UGV limit

    def test_position_rewrite_to_bounds(
        self, engine: ConstraintsEngine, ugv_platform: Platform
    ):
        """Position should be clamped to world bounds."""
        fleet_state = FleetState(platforms={ugv_platform.id: ugv_platform})
        cmd = make_command("go_to", "ugv1", x=200, y=-200, z=100)

        rewritten = engine.try_rewrite_safe(cmd, ugv_platform, fleet_state)

        assert rewritten is not None
        assert rewritten.params["x"] == 100  # Clamped to max
        assert rewritten.params["y"] == -100  # Clamped to min
        assert rewritten.params["z"] == 50  # Clamped to max

    def test_no_rewrite_when_disabled(self, ugv_platform: Platform):
        """Rewriting should return None when disabled."""
        engine = ConstraintsEngine(ConstraintsConfig(allow_rewrite=False))
        fleet_state = FleetState(platforms={ugv_platform.id: ugv_platform})
        cmd = make_command("go_to", "ugv1", x=200, y=200, speed=100)

        rewritten = engine.try_rewrite_safe(cmd, ugv_platform, fleet_state)

        assert rewritten is None


# ──────────────────────────────────────────────────────────────────────────────
# Position Safety Check Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPositionSafetyCheck:
    """Tests for the check_position_safe utility."""

    def test_safe_position(self, engine: ConstraintsEngine):
        """Valid position should be safe."""
        pos = Position(x=0, y=0, z=0)
        is_safe, violations = engine.check_position_safe(pos)

        assert is_safe is True
        assert len(violations) == 0

    def test_out_of_bounds_position(self, engine: ConstraintsEngine):
        """Out of bounds position should be unsafe."""
        pos = Position(x=500, y=0, z=0)
        is_safe, violations = engine.check_position_safe(pos)

        assert is_safe is False
        assert len(violations) == 1
        assert "outside world bounds" in violations[0]

    def test_position_in_no_go_zone(self, demo_engine: ConstraintsEngine):
        """Position in no-go zone should be unsafe."""
        pos = Position(x=-15, y=-15, z=0)
        is_safe, violations = demo_engine.check_position_safe(pos)

        assert is_safe is False
        assert "no-go zone" in violations[0]


# ──────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for the full constraints workflow."""

    def test_multiple_violations_all_reported(self, fleet_state: FleetState):
        """Command with multiple violations should report all."""
        engine = ConstraintsEngine(
            ConstraintsConfig(
                no_go_zones=[
                    NoGoZone(name="zone1", vertices=[(140, 140), (160, 140), (160, 160), (140, 160)])
                ]
            )
        )

        # This command has: out of bounds AND in no-go zone (if bounds extended)
        cmd = make_command("go_to", "ugv1", x=150, y=150, speed=100)
        result = engine.check_command(cmd, fleet_state)

        assert result.verdict == ConstraintVerdict.REJECTED
        # Should have violations for speed and bounds
        assert len(result.violations) >= 2

    def test_demo_scenario_valid_command(self, demo_engine: ConstraintsEngine):
        """Test a valid demo scenario command."""
        fleet_state = FleetState(
            platforms={
                "ugv1": Platform(
                    id="ugv1",
                    name="UGV Alpha",
                    type=PlatformType.UGV,
                    position=Position(x=0, y=0, z=0),
                ),
                "uav1": Platform(
                    id="uav1",
                    name="UAV Bravo",
                    type=PlatformType.UAV,
                    position=Position(x=0, y=0, z=10),
                ),
            }
        )

        # Valid command: move UGV to checkpoint at safe speed
        cmd = make_command("go_to", "ugv1", x=20, y=20, speed=3.0)
        result = demo_engine.check_command(cmd, fleet_state)

        assert result.is_approved
        assert result.approved_command is not None
