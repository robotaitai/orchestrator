# System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ChatPanel │ │ MiniMap  │ │PlatCards │ │ SimView  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/WebSocket
┌─────────────────────────┴───────────────────────────────────┐
│                        Backend                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                      API Layer                        │   │
│  │              (REST + WebSocket endpoints)             │   │
│  └──────────────────────────────────────────────────────┘   │
│                            │                                 │
│  ┌─────────────────────────┴────────────────────────────┐   │
│  │                   Orchestrator                        │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐              │   │
│  │  │Validator │ │Playbook  │ │Constraints│              │   │
│  │  └──────────┘ └──────────┘ └──────────┘              │   │
│  └──────────────────────────────────────────────────────┘   │
│                            │                                 │
│  ┌─────────────┬───────────┴───────────┬────────────────┐   │
│  │  LLM Layer  │     Simulation        │    Logging     │   │
│  │  (Gemini)   │     (MuJoCo)         │                │   │
│  └─────────────┴───────────────────────┴────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### API Layer
- FastAPI-based REST API
- WebSocket for real-time updates
- Request validation and authentication

### Orchestrator
- Command routing and execution
- State management
- Playbook coordination

### LLM Layer
- Natural language processing
- Command interpretation
- Response generation

### Simulation
- MuJoCo physics engine
- Platform models
- Environment rendering

### Logging
- Structured event logging
- Session recording
- Replay capability

## Data Flow

<!-- TODO: Add data flow diagrams -->

## Technology Stack

| Component | Technology |
|-----------|------------|
| Backend   | Python, FastAPI |
| Frontend  | React, TypeScript, Vite |
| LLM       | Google Gemini |
| Simulation| MuJoCo |
| Database  | SQLite (dev), PostgreSQL (prod) |
