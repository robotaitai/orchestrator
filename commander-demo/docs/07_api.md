# API Reference

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

<!-- TODO: Define authentication mechanism -->

## Endpoints

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Platforms

#### List Platforms

```http
GET /platforms
```

#### Get Platform

```http
GET /platforms/{platform_id}
```

#### Update Platform

```http
PATCH /platforms/{platform_id}
```

### Commands

#### Send Command

```http
POST /commands
```

**Request Body:**
```json
{
  "type": "move",
  "target": "platform-alpha",
  "params": {
    "x": 10,
    "y": 20
  }
}
```

#### Get Command History

```http
GET /commands
```

### Chat

#### Send Message

```http
POST /chat
```

**Request Body:**
```json
{
  "message": "Move platform Alpha to coordinates 10, 20"
}
```

### Playbooks

#### List Playbooks

```http
GET /playbooks
```

#### Execute Playbook

```http
POST /playbooks/{playbook_id}/execute
```

## WebSocket API

### Connection

```
ws://localhost:8000/ws
```

### Events

| Event Type | Description |
|------------|-------------|
| `platform_update` | Platform state changed |
| `command_result` | Command execution result |
| `simulation_frame` | Simulation frame data |

## Error Codes

| Code | Description |
|------|-------------|
| 400  | Bad Request |
| 404  | Not Found |
| 422  | Validation Error |
| 500  | Internal Server Error |
