# Safety Constraints Engine

The safety constraint system validates all commands **before execution** to ensure safe operation. Constraints are enforced by deterministic code, **not the LLM**.

## Architecture

```
User Command → Validator → ┌─────────────────────┐ → Orchestrator → Execution
                           │ Constraints Engine  │
                           │ (Hard Guardrails)   │
                           └─────────────────────┘
                                    │
                            ┌───────┴───────┐
                            ▼               ▼
                        APPROVED        REJECTED
                    (with warnings)   (with reasons)
```

## Constraint Types

### 1. Speed Limits

Maximum velocity limits per platform type:

| Platform Type | Max Speed (m/s) |
|--------------|-----------------|
| UGV (ground) | 5.0             |
| UAV (drone)  | 15.0            |

**Rejection example:**
```
"Requested speed 10 m/s exceeds maximum 5 m/s for UGV"
```

### 2. World Boundaries

Platforms must remain within defined operational boundaries:

```python
world_bounds = {
    "x_min": -100,  "x_max": 100,
    "y_min": -100,  "y_max": 100,
    "z_min": 0,     "z_max": 50    # Ground to max altitude
}
```

**Rejection example:**
```
"Target position out of bounds: x=150.0 outside [-100, 100]"
```

### 3. No-Go Zones

Restricted polygonal areas where platforms cannot enter:

```python
no_go_zones = [
    NoGoZone(
        name="R1",
        vertices=[(-20, -20), (-20, -10), (-10, -10), (-10, -20)]
    )
]
```

**Rejection example:**
```
"Target position (-15.0, -15.0) is inside restricted zone 'R1'"
```

### 4. Minimum Separation

Minimum distance between any two platforms:

```python
min_separation_m = 2.0  # meters
```

**Warning example:**
```
"Target position would be 1.0m from platform 'ugv2' (minimum separation: 2.0m)"
```

### 5. Communications Timeout

If a platform hasn't sent a heartbeat within the timeout window, commands are blocked:

```python
comms_timeout_s = 5.0  # seconds
```

**Rejection example:**
```
"Platform 'ugv1' has not responded for 10.0s (timeout: 5.0s). Commands blocked until comms restored."
```

## Constraint Result Types

| Verdict | Description |
|---------|-------------|
| `APPROVED` | Command passes all checks, safe to execute |
| `REJECTED` | Command violates one or more constraints |
| `REWRITTEN` | Command was modified to a safe variant |

## Human-Readable Messages

All rejections include human-readable messages:

```python
result = engine.check_command(cmd, fleet_state)

if not result.is_approved:
    print(result.rejection_message())
    # "Command rejected: Requested speed 10 m/s exceeds maximum 5 m/s for UGV"
    
    for suggestion in result.suggestions:
        print(f"  Suggestion: {suggestion}")
    # "  Suggestion: Use speed <= 5 m/s for ugv"
```

## Safe Rewriting (Optional)

The engine can attempt to rewrite unsafe commands to safe variants:

```python
# Original: speed=10, position=(200, 200)
rewritten = engine.try_rewrite_safe(cmd, platform, fleet_state)

# Rewritten: speed=5 (clamped), position=(100, 100) (clamped to bounds)
```

## Usage

```python
from commander.core.constraints import (
    ConstraintsEngine,
    ConstraintsConfig,
    create_demo_engine,
)

# Create engine with default config
engine = ConstraintsEngine()

# Or use demo config (includes sample no-go zone)
engine = create_demo_engine()

# Check a command
result = engine.check_command(command, fleet_state)

if result.is_approved:
    # Safe to execute
    execute(result.approved_command)
else:
    # Log rejection
    log.warning(result.rejection_message())
    for v in result.violations:
        log.warning(f"  - {v}")
```

## Configuration

```python
config = ConstraintsConfig(
    min_separation_m=2.0,
    speed_limits=SpeedLimits(ugv=5.0, uav=15.0),
    world_bounds=WorldBounds(
        x_min=-50, x_max=50,
        y_min=-50, y_max=50,
        z_min=0, z_max=30,
    ),
    no_go_zones=[
        NoGoZone(name="R1", vertices=[...]),
    ],
    comms_timeout_s=5.0,
    allow_rewrite=True,  # Enable safe rewriting
)

engine = ConstraintsEngine(config)
```

## Testing

```bash
cd backend
pytest tests/test_constraints.py -v
```

27 tests covering:
- Speed limits (UGV and UAV)
- World boundaries
- No-go zone detection
- Minimum separation
- Communications timeout
- Unknown platform handling
- Command rewriting
- Position safety checks
