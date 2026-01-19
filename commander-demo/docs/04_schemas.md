# Data Schemas

## Platform Schema

```json
{
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "name": { "type": "string" },
    "type": { "type": "string", "enum": ["ground", "aerial", "marine"] },
    "position": {
      "type": "object",
      "properties": {
        "x": { "type": "number" },
        "y": { "type": "number" },
        "z": { "type": "number" }
      }
    },
    "orientation": {
      "type": "object",
      "properties": {
        "roll": { "type": "number" },
        "pitch": { "type": "number" },
        "yaw": { "type": "number" }
      }
    },
    "status": { "type": "string", "enum": ["idle", "moving", "error"] }
  }
}
```

## Command Schema

```json
{
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "type": { "type": "string" },
    "target": { "type": "string" },
    "params": { "type": "object" },
    "timestamp": { "type": "string", "format": "date-time" }
  }
}
```

## Event Schema

<!-- TODO: Define event schema -->

## Constraint Schema

<!-- TODO: Define constraint schema -->
