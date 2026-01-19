"""
Safety Constraints Engine

Enforces safety rules OUTSIDE the LLM. This is the hard guardrail layer.
All commands must pass through this engine before execution.

Constraints enforced:
1. Minimum separation distance between platforms
2. Maximum speed per platform type
3. No-go zone polygons
4. Communications timeout behavior
5. World boundary limits
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from commander.core.models import (
    Command,
    FleetState,
    Platform,
    PlatformStatus,
    PlatformType,
    Position,
)


# ──────────────────────────────────────────────────────────────────────────────
# Constraint Result Types
# ──────────────────────────────────────────────────────────────────────────────


class ConstraintVerdict(str, Enum):
    """Result of constraint check."""

    APPROVED = "approved"
    REJECTED = "rejected"
    REWRITTEN = "rewritten"  # Command was modified to be safe


@dataclass
class ConstraintResult:
    """Result of running a command through the constraints engine."""

    verdict: ConstraintVerdict
    original_command: Command
    approved_command: Command | None = None  # Set if approved or rewritten
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.verdict in (ConstraintVerdict.APPROVED, ConstraintVerdict.REWRITTEN)

    def rejection_message(self) -> str:
        """Human-readable rejection message."""
        if not self.violations:
            return "Command approved."
        return "Command rejected: " + "; ".join(self.violations)


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class SpeedLimits:
    """Maximum speed limits per platform type (m/s)."""

    ugv: float = 5.0  # Ground robots: 5 m/s
    uav: float = 15.0  # Drones: 15 m/s

    def get_limit(self, platform_type: PlatformType) -> float:
        """Get speed limit for a platform type."""
        if platform_type in (PlatformType.UGV, PlatformType.GROUND):
            return self.ugv
        elif platform_type in (PlatformType.UAV, PlatformType.AERIAL):
            return self.uav
        return self.ugv  # Default to conservative limit


@dataclass
class WorldBounds:
    """World boundary limits (rectangular)."""

    x_min: float = -100.0
    x_max: float = 100.0
    y_min: float = -100.0
    y_max: float = 100.0
    z_min: float = 0.0  # Ground level
    z_max: float = 50.0  # Max altitude

    def contains(self, pos: Position) -> bool:
        """Check if position is within bounds."""
        return (
            self.x_min <= pos.x <= self.x_max
            and self.y_min <= pos.y <= self.y_max
            and self.z_min <= pos.z <= self.z_max
        )

    def clamp(self, pos: Position) -> Position:
        """Clamp position to within bounds."""
        return Position(
            x=max(self.x_min, min(self.x_max, pos.x)),
            y=max(self.y_min, min(self.y_max, pos.y)),
            z=max(self.z_min, min(self.z_max, pos.z)),
        )


@dataclass
class NoGoZone:
    """A polygon representing a restricted area (2D, ignores z)."""

    name: str
    vertices: list[tuple[float, float]]  # List of (x, y) points forming polygon

    def contains_point(self, x: float, y: float) -> bool:
        """
        Check if point is inside polygon using ray casting algorithm.
        """
        n = len(self.vertices)
        if n < 3:
            return False

        inside = False
        j = n - 1

        for i in range(n):
            xi, yi = self.vertices[i]
            xj, yj = self.vertices[j]

            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    def contains_position(self, pos: Position) -> bool:
        """Check if a Position is inside this no-go zone."""
        return self.contains_point(pos.x, pos.y)
    
    def path_intersects(self, start: Position, end: Position) -> bool:
        """
        Check if a straight-line path from start to end intersects this zone.
        Uses line-segment intersection with polygon edges.
        """
        # First check if either endpoint is inside
        if self.contains_position(start) or self.contains_position(end):
            return True
        
        # Check intersection with each edge
        n = len(self.vertices)
        for i in range(n):
            x1, y1 = self.vertices[i]
            x2, y2 = self.vertices[(i + 1) % n]
            
            if self._segments_intersect(
                start.x, start.y, end.x, end.y,
                x1, y1, x2, y2
            ):
                return True
        
        return False
    
    @staticmethod
    def _segments_intersect(
        ax1: float, ay1: float, ax2: float, ay2: float,
        bx1: float, by1: float, bx2: float, by2: float,
    ) -> bool:
        """Check if two line segments intersect."""
        def ccw(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> bool:
            return (ry - py) * (qx - px) > (qy - py) * (rx - px)
        
        return (
            ccw(ax1, ay1, bx1, by1, bx2, by2) != ccw(ax2, ay2, bx1, by1, bx2, by2)
            and ccw(ax1, ay1, ax2, ay2, bx1, by1) != ccw(ax1, ay1, ax2, ay2, bx2, by2)
        )
    
    def get_bounding_box(self) -> tuple[float, float, float, float]:
        """Get bounding box (min_x, min_y, max_x, max_y)."""
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))
    
    def get_detour_waypoints(
        self, 
        start: Position, 
        end: Position, 
        margin: float = 2.0,
    ) -> list[Position]:
        """
        Calculate detour waypoints to go around this zone.
        Returns a list of waypoints (excluding start and end).
        Uses simple corner-rounding strategy.
        """
        min_x, min_y, max_x, max_y = self.get_bounding_box()
        
        # Expand bounding box by margin
        min_x -= margin
        min_y -= margin
        max_x += margin
        max_y += margin
        
        # Corners of expanded bounding box
        corners = [
            (min_x, min_y),
            (min_x, max_y),
            (max_x, max_y),
            (max_x, min_y),
        ]
        
        # Find the best corner(s) to route through
        # Simple heuristic: choose the corner that minimizes total path length
        best_path: list[Position] = []
        best_distance = float('inf')
        
        # Try each single corner
        for cx, cy in corners:
            corner = Position(x=cx, y=cy, z=start.z)
            dist = (
                ((start.x - cx)**2 + (start.y - cy)**2)**0.5 +
                ((end.x - cx)**2 + (end.y - cy)**2)**0.5
            )
            if dist < best_distance:
                best_distance = dist
                best_path = [corner]
        
        # Try two adjacent corners (for more complex cases)
        for i in range(4):
            c1 = corners[i]
            c2 = corners[(i + 1) % 4]
            corner1 = Position(x=c1[0], y=c1[1], z=start.z)
            corner2 = Position(x=c2[0], y=c2[1], z=start.z)
            dist = (
                ((start.x - c1[0])**2 + (start.y - c1[1])**2)**0.5 +
                ((c1[0] - c2[0])**2 + (c1[1] - c2[1])**2)**0.5 +
                ((end.x - c2[0])**2 + (end.y - c2[1])**2)**0.5
            )
            if dist < best_distance:
                best_distance = dist
                best_path = [corner1, corner2]
        
        return best_path


@dataclass
class ConstraintsConfig:
    """Configuration for all safety constraints."""

    # Minimum separation distance between any two platforms (meters)
    min_separation_m: float = 2.0

    # Speed limits
    speed_limits: SpeedLimits = field(default_factory=SpeedLimits)

    # World boundaries
    world_bounds: WorldBounds = field(default_factory=WorldBounds)

    # No-go zones (restricted areas)
    no_go_zones: list[NoGoZone] = field(default_factory=list)

    # Comms timeout: if no heartbeat for this many seconds, platform goes offline
    comms_timeout_s: float = 5.0

    # Whether to attempt rewriting commands to safe variants
    allow_rewrite: bool = True


# ──────────────────────────────────────────────────────────────────────────────
# Constraints Engine
# ──────────────────────────────────────────────────────────────────────────────


class ConstraintsEngine:
    """
    Safety constraints engine.
    
    Validates commands against fleet state and safety rules.
    Runs BEFORE any command is executed.
    """

    def __init__(self, config: ConstraintsConfig | None = None) -> None:
        self.config = config or ConstraintsConfig()

    def check_command(
        self,
        command: Command,
        fleet_state: FleetState,
    ) -> ConstraintResult:
        """
        Validate a command against all safety constraints.

        Args:
            command: The command to validate
            fleet_state: Current state of all platforms

        Returns:
            ConstraintResult with verdict and any violations
        """
        violations: list[str] = []
        warnings: list[str] = []
        suggestions: list[str] = []

        # Special group targets that are valid
        GROUP_TARGETS = ("all", "*", "ugv_pod", "uav_pod")

        # Get target platform
        platform = fleet_state.get_platform(command.target)
        if not platform:
            # Target might be a pod or "all" - handle gracefully
            if command.target not in GROUP_TARGETS:
                violations.append(f"Unknown platform: '{command.target}'")
                return ConstraintResult(
                    verdict=ConstraintVerdict.REJECTED,
                    original_command=command,
                    violations=violations,
                )
            # For group commands, we skip per-platform checks here
            # The orchestrator will validate each platform individually
            platform = None

        # ── Check 1: Comms timeout ────────────────────────────────────────────
        if platform:
            timeout_result = self._check_comms_timeout(platform)
            if timeout_result:
                violations.append(timeout_result)

        # ── Check 2: Speed limits ─────────────────────────────────────────────
        if platform and command.type in ("go_to", "move", "set_speed", "patrol"):
            speed_result = self._check_speed_limit(command, platform)
            if speed_result:
                violations.append(speed_result)
                limit = self.config.speed_limits.get_limit(platform.type)
                suggestions.append(f"Use speed <= {limit} m/s for {platform.type.value}")

        # ── Check 3: World bounds ─────────────────────────────────────────────
        if command.type in ("go_to", "move"):
            bounds_result = self._check_world_bounds(command)
            if bounds_result:
                violations.append(bounds_result)

        # ── Check 4: No-go zones ──────────────────────────────────────────────
        if command.type in ("go_to", "move", "patrol"):
            nogo_result = self._check_no_go_zones(command)
            if nogo_result:
                violations.append(nogo_result)

        # ── Check 5: Minimum separation ───────────────────────────────────────
        if platform and command.type in ("go_to", "move"):
            sep_result = self._check_separation(command, platform, fleet_state)
            if sep_result:
                # Separation is a warning, not hard rejection (could be transient)
                warnings.append(sep_result)
                suggestions.append(
                    f"Ensure minimum {self.config.min_separation_m}m separation"
                )

        # ── Build result ──────────────────────────────────────────────────────
        if violations:
            return ConstraintResult(
                verdict=ConstraintVerdict.REJECTED,
                original_command=command,
                violations=violations,
                warnings=warnings,
                suggestions=suggestions,
            )

        # Approved (possibly with warnings)
        return ConstraintResult(
            verdict=ConstraintVerdict.APPROVED,
            original_command=command,
            approved_command=command,
            warnings=warnings,
            suggestions=suggestions,
        )

    def check_position_safe(
        self,
        position: Position,
        exclude_platform_id: str | None = None,
        fleet_state: FleetState | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Check if a position is safe (within bounds, not in no-go zone).

        Returns:
            Tuple of (is_safe, list of violation messages)
        """
        violations = []

        # Check world bounds
        if not self.config.world_bounds.contains(position):
            violations.append(
                f"Position ({position.x:.1f}, {position.y:.1f}, {position.z:.1f}) "
                f"is outside world bounds"
            )

        # Check no-go zones
        for zone in self.config.no_go_zones:
            if zone.contains_position(position):
                violations.append(
                    f"Position ({position.x:.1f}, {position.y:.1f}) "
                    f"is inside no-go zone '{zone.name}'"
                )

        # Check separation from other platforms
        if fleet_state:
            for pid, platform in fleet_state.platforms.items():
                if pid == exclude_platform_id:
                    continue
                dist = position.distance_to(platform.position)
                if dist < self.config.min_separation_m:
                    violations.append(
                        f"Position is {dist:.1f}m from platform '{pid}' "
                        f"(minimum: {self.config.min_separation_m}m)"
                    )

        return len(violations) == 0, violations

    # ──────────────────────────────────────────────────────────────────────────
    # Individual constraint checks
    # ──────────────────────────────────────────────────────────────────────────

    def _check_comms_timeout(self, platform: Platform) -> str | None:
        """Check if platform has timed out."""
        seconds = platform.seconds_since_heartbeat()
        if seconds > self.config.comms_timeout_s:
            return (
                f"Platform '{platform.id}' has not responded for {seconds:.1f}s "
                f"(timeout: {self.config.comms_timeout_s}s). "
                f"Commands blocked until comms restored."
            )
        return None

    def _check_speed_limit(self, command: Command, platform: Platform) -> str | None:
        """Check if requested speed exceeds limit."""
        requested_speed = command.params.get("speed")
        if requested_speed is None:
            return None

        limit = self.config.speed_limits.get_limit(platform.type)
        if requested_speed > limit:
            return (
                f"Requested speed {requested_speed} m/s exceeds maximum "
                f"{limit} m/s for {platform.type.value.upper()}"
            )
        return None

    def _check_world_bounds(self, command: Command) -> str | None:
        """Check if target position is within world bounds."""
        x = command.params.get("x")
        y = command.params.get("y")
        z = command.params.get("z", 0.0)

        if x is None or y is None:
            return None  # No position specified

        target_pos = Position(x=x, y=y, z=z)
        bounds = self.config.world_bounds

        if not bounds.contains(target_pos):
            parts = []
            if not (bounds.x_min <= x <= bounds.x_max):
                parts.append(f"x={x:.1f} outside [{bounds.x_min}, {bounds.x_max}]")
            if not (bounds.y_min <= y <= bounds.y_max):
                parts.append(f"y={y:.1f} outside [{bounds.y_min}, {bounds.y_max}]")
            if not (bounds.z_min <= z <= bounds.z_max):
                parts.append(f"z={z:.1f} outside [{bounds.z_min}, {bounds.z_max}]")
            return f"Target position out of bounds: {', '.join(parts)}"

        return None

    def _check_no_go_zones(self, command: Command) -> str | None:
        """Check if target position is in a no-go zone."""
        x = command.params.get("x")
        y = command.params.get("y")

        if x is None or y is None:
            return None

        target_pos = Position(x=x, y=y, z=0)

        for zone in self.config.no_go_zones:
            if zone.contains_position(target_pos):
                return (
                    f"Target position ({x:.1f}, {y:.1f}) is inside "
                    f"restricted zone '{zone.name}'"
                )

        return None
    
    def check_path_intersection(
        self,
        start: Position,
        end: Position,
    ) -> tuple[bool, NoGoZone | None, str | None]:
        """
        Check if a straight-line path intersects any no-go zone.
        
        Returns:
            (intersects, zone, message) - whether path intersects, which zone, and error message
        """
        for zone in self.config.no_go_zones:
            if zone.path_intersects(start, end):
                msg = (
                    f"Path from ({start.x:.1f}, {start.y:.1f}) to ({end.x:.1f}, {end.y:.1f}) "
                    f"crosses restricted zone '{zone.name}'"
                )
                return (True, zone, msg)
        
        return (False, None, None)
    
    def get_safe_path(
        self,
        start: Position,
        end: Position,
        avoid_policy: str = "reject",
    ) -> tuple[list[Position], str | None]:
        """
        Get a safe path from start to end, avoiding no-go zones.
        
        Args:
            start: Starting position
            end: Target position  
            avoid_policy: 'reject' or 'detour'
            
        Returns:
            (waypoints, error_message) - list of waypoints including detours, or error
        """
        # Check if target is inside a no-go zone (always reject)
        for zone in self.config.no_go_zones:
            if zone.contains_position(end):
                return ([], f"Target ({end.x:.1f}, {end.y:.1f}) is inside zone '{zone.name}'")
        
        # Check path intersection
        intersects, zone, msg = self.check_path_intersection(start, end)
        
        if not intersects:
            # Path is clear
            return ([end], None)
        
        if avoid_policy == "reject":
            # Suggest alternate waypoint
            if zone:
                detour = zone.get_detour_waypoints(start, end)
                if detour:
                    suggestion = f"Suggested waypoint: ({detour[0].x:.1f}, {detour[0].y:.1f})"
                    return ([], f"{msg}. {suggestion}")
            return ([], msg)
        
        elif avoid_policy == "detour":
            # Auto-insert detour waypoints
            if zone:
                detour_points = zone.get_detour_waypoints(start, end)
                # Verify detour path is safe
                waypoints = []
                current = start
                for wp in detour_points:
                    sub_intersects, _, _ = self.check_path_intersection(current, wp)
                    if sub_intersects:
                        # Detour also crosses zone - fall back to reject
                        return ([], f"{msg}. Unable to compute safe detour.")
                    waypoints.append(wp)
                    current = wp
                
                # Check final leg
                sub_intersects, _, _ = self.check_path_intersection(current, end)
                if sub_intersects:
                    return ([], f"{msg}. Unable to compute safe detour.")
                
                waypoints.append(end)
                return (waypoints, None)
        
        return ([], msg)

    def _check_separation(
        self,
        command: Command,
        platform: Platform,
        fleet_state: FleetState,
    ) -> str | None:
        """Check if move would violate minimum separation."""
        x = command.params.get("x")
        y = command.params.get("y")
        z = command.params.get("z", platform.position.z)

        if x is None or y is None:
            return None

        target_pos = Position(x=x, y=y, z=z)

        for pid, other in fleet_state.platforms.items():
            if pid == platform.id:
                continue

            dist = target_pos.distance_to(other.position)
            if dist < self.config.min_separation_m:
                return (
                    f"Target position would be {dist:.1f}m from platform '{pid}' "
                    f"(minimum separation: {self.config.min_separation_m}m)"
                )

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Rewriting (optional safe variant generation)
    # ──────────────────────────────────────────────────────────────────────────

    def try_rewrite_safe(
        self,
        command: Command,
        platform: Platform,
        fleet_state: FleetState,
    ) -> Command | None:
        """
        Attempt to rewrite a command to a safe variant.

        Returns:
            Rewritten command if possible, None if cannot be made safe
        """
        if not self.config.allow_rewrite:
            return None

        new_params = dict(command.params)
        modified = False

        # Clamp speed to limit
        if "speed" in new_params:
            limit = self.config.speed_limits.get_limit(platform.type)
            if new_params["speed"] > limit:
                new_params["speed"] = limit
                modified = True

        # Clamp position to world bounds
        if "x" in new_params and "y" in new_params:
            pos = Position(
                x=new_params["x"],
                y=new_params["y"],
                z=new_params.get("z", 0.0),
            )
            clamped = self.config.world_bounds.clamp(pos)
            if clamped.x != pos.x or clamped.y != pos.y or clamped.z != pos.z:
                new_params["x"] = clamped.x
                new_params["y"] = clamped.y
                new_params["z"] = clamped.z
                modified = True

        if modified:
            return Command(
                id=command.id,
                type=command.type,
                target=command.target,
                params=new_params,
                timestamp=command.timestamp,
            )

        return None


# ──────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ──────────────────────────────────────────────────────────────────────────────


def create_default_engine() -> ConstraintsEngine:
    """Create a constraints engine with default configuration."""
    return ConstraintsEngine(ConstraintsConfig())


def create_demo_engine() -> ConstraintsEngine:
    """
    Create a constraints engine configured for the demo.
    Includes a sample no-go zone.
    """
    config = ConstraintsConfig(
        min_separation_m=2.0,
        speed_limits=SpeedLimits(ugv=5.0, uav=15.0),
        world_bounds=WorldBounds(
            x_min=-50, x_max=50,
            y_min=-50, y_max=50,
            z_min=0, z_max=30,
        ),
        no_go_zones=[
            NoGoZone(
                name="R1",
                vertices=[(-20, -20), (-20, -10), (-10, -10), (-10, -20)],
            ),
        ],
        comms_timeout_s=5.0,
    )
    return ConstraintsEngine(config)
