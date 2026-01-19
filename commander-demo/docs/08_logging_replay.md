# Logging & Replay System

## Overview

The logging system captures all events for debugging, auditing, and replay purposes.

## Log Structure

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "session_id": "sess_abc123",
  "event_type": "command",
  "level": "INFO",
  "data": {
    "command_id": "cmd_xyz789",
    "type": "move",
    "target": "platform-alpha"
  }
}
```

## Event Types

| Event Type | Description |
|------------|-------------|
| `command` | User command issued |
| `validation` | Constraint validation result |
| `execution` | Command execution status |
| `simulation` | Simulation state update |
| `error` | Error occurred |

## Log Levels

- `DEBUG`: Detailed debugging information
- `INFO`: General operational events
- `WARNING`: Potential issues
- `ERROR`: Error conditions
- `CRITICAL`: System failures

## Storage

Logs are stored in:
- Development: `./logs/` directory (JSON files)
- Production: <!-- TODO: Define production storage -->

## Replay System

### Recording a Session

Sessions are automatically recorded when logging is enabled.

### Replaying a Session

```bash
# Via CLI
python -m commander.replay --session sess_abc123

# Via API
POST /api/v1/replay
{
  "session_id": "sess_abc123",
  "speed": 1.0
}
```

### Replay Controls

- Play / Pause
- Speed adjustment (0.25x - 4x)
- Step forward / backward
- Jump to timestamp

## Data Retention

<!-- TODO: Define retention policies -->
