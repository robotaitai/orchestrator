# Commander Demo

A demonstration of LLM-powered robot fleet orchestration with safety constraints.

## What This Demo Shows

This is a **simulated** multi-robot coordination system where:

1. **You type natural language commands** → "Move the convoy to checkpoint bravo"
2. **Gemini LLM converts them to structured commands** → `go_to`, `form_formation`, etc.
3. **Safety constraints engine validates them** → Speed limits, no-go zones, separation distances
4. **Commands execute on a simulated fleet** → 3 ground robots (UGVs) + 2 drones (UAVs)
5. **Real-time visualization shows everything** → Map, positions, events, status

---

## Quick Start

### Prerequisites

- Python 3.11+ 
- Node.js 18+
- A [Google Gemini API key](https://aistudio.google.com/apikey)

### Step 1: Start the Backend

```bash
cd commander-demo/backend

# Create virtual environment (first time only)
python -m venv .venv

# Activate it
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (first time only)
pip install -e ".[dev]"

# Create .env file with your API key
echo "GEMINI_API_KEY=your-actual-key-here" > .env

# Start the backend server
python -m commander.main
```

You should see:
```
INFO     Commander API starting...
INFO     Registered platform: ugv1
INFO     Registered platform: ugv2
INFO     Registered platform: ugv3
INFO     Registered platform: uav1
INFO     Registered platform: uav2
INFO     Orchestrator started with 5 platforms
INFO     Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Start the Frontend

In a **new terminal**:

```bash
cd commander-demo/frontend

# Install dependencies (first time only)
npm install

# Start dev server
npm run dev
```

You should see:
```
VITE v6.x.x ready
➜ Local: http://localhost:5173/
```

### Step 3: Open the UI

**Open your browser to: http://localhost:5173**

---

## What You'll See in the UI

The interface has **5 panels**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  COMMANDER                    ● CONNECTED              [START DEMO] │
├───────────────┬─────────────────────────────────┬───────────────────┤
│               │                                 │   TACTICAL MAP    │
│   COMMAND     │      3D SIMULATION VIEW         │   (Top-down view) │
│   INTERFACE   │                                 │   - Platform dots │
│               │      (Isometric view of         │   - No-go zones   │
│   (Chat box   │       platforms moving)         │   - Checkpoints   │
│    for your   │                                 ├───────────────────┤
│    commands)  │                                 │   FLEET STATUS    │
│               │                                 │   (Platform cards)│
│               ├─────────────────────────────────┤   - UGV1, UGV2... │
│               │      EVENT TIMELINE             │   - Position      │
│               │      (Scrolling event log)      │   - Battery       │
└───────────────┴─────────────────────────────────┴───────────────────┘
```

### Panel Details:

1. **Command Interface** (left) - Type natural language commands here
2. **3D Simulation View** (center-top) - Isometric view showing:
   - UGVs as green rectangles with wheels
   - UAVs as purple triangles (drones)
   - Ground plane with grid
3. **Event Timeline** (center-bottom) - Shows task lifecycle events
4. **Tactical Map** (right-top) - Top-down 2D map showing:
   - Platform positions (squares for UGV, triangles for UAV)
   - **Red dashed zone = No-go area (R1)**
   - Checkpoints: α (Alpha), β (Bravo), γ (Charlie), H (Home)
5. **Fleet Status** (right-bottom) - Cards for each platform with stats

---

## The Simulated World

### Platforms (5 total)

| ID   | Name      | Type | Starting Position |
|------|-----------|------|-------------------|
| ugv1 | UGV Alpha | UGV  | (0, 0, 0)         |
| ugv2 | UGV Bravo | UGV  | (5, 0, 0)         |
| ugv3 | UGV Charlie| UGV | (10, 0, 0)        |
| uav1 | UAV Delta | UAV  | (0, 0, 15)        |
| uav2 | UAV Echo  | UAV  | (5, 0, 20)        |

### World Boundaries

- X: -50 to +50 meters
- Y: -50 to +50 meters  
- Z (altitude): 0 to 30 meters

### Named Checkpoints

| Name    | Coordinates |
|---------|-------------|
| Alpha   | (20, 30)    |
| Bravo   | (40, 50)    |
| Charlie | (10, -20)   |
| Home    | (0, 0)      |

### No-Go Zone (Obstacle)

There is **one red restricted zone** called **R1**:
- Location: A square from (-20, -20) to (-10, -10)
- Any command trying to move into this area will be **rejected**

### Speed Limits

- UGVs (ground): Max 5 m/s
- UAVs (aerial): Max 15 m/s

### Minimum Separation

Platforms must stay at least **3 meters** apart.

---

## Try These Commands

Type these in the Command Interface:

1. **"Move UGV1 to checkpoint alpha"**
   - UGV1 will move from (0,0) to (20, 30)

2. **"Have UAV1 orbit above checkpoint bravo at 20 meters"**  
   - UAV1 will start orbiting around (40, 50) at 20m altitude

3. **"Form convoy with all ground robots, leader is UGV1"**
   - All UGVs will form a line formation

4. **"Report status of all platforms"**
   - Get a status report of the entire fleet

5. **"Move UGV2 to position -15, -15"**
   - This will be **REJECTED** because it's in the no-go zone R1!

---

## Demo Mode

Click the **START DEMO** button to run a pre-scripted sequence:

1. Move UGV1 to checkpoint alpha
2. Form convoy with ground robots
3. Move convoy to checkpoint bravo
4. UAV1 orbits above bravo
5. UAV2 spotlights the convoy
6. Report status
7. Stop all platforms

---

## What If I Don't Have a Gemini API Key?

You can still test the system using **direct API commands** (bypassing the LLM):

```bash
# Move UGV1 to position (10, 15)
curl -X POST http://localhost:8000/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{"command": "go_to", "target": "ugv1", "params": {"x": 10, "y": 15}}'

# Try to enter no-go zone (will be rejected!)
curl -X POST http://localhost:8000/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{"command": "go_to", "target": "ugv2", "params": {"x": -15, "y": -15}}'

# Form a line formation
curl -X POST http://localhost:8000/api/v1/commands \
  -H "Content-Type: application/json" \
  -d '{"command": "form_formation", "target": "ugv_pod", "params": {"formation": "line", "leader": "ugv1", "spacing_m": 3}}'
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/status` | GET | Full system status |
| `/api/v1/platforms` | GET | List all platforms |
| `/api/v1/command` | POST | Send natural language command |
| `/api/v1/commands` | POST | Send direct command (no LLM) |
| `/api/v1/timeline` | GET | Get event history |
| `/api/v1/constraints` | GET | Get safety constraint config |
| `/ws` | WebSocket | Real-time updates |

---

## Troubleshooting

### "Gemini API key not valid"
→ Create `.env` file in `backend/` with `GEMINI_API_KEY=your-key`

### "Connection refused"
→ Make sure backend is running on port 8000

### Platforms show "offline" or commands fail with timeout
→ Restart the backend server

### Frontend shows blank or errors
→ Make sure backend is running first, then refresh frontend

---

## Architecture

```
┌──────────────┐     Natural     ┌──────────────┐
│   Frontend   │ ──Language───→  │  Gemini LLM  │
│   (React)    │                 │  (Cloud API) │
└──────┬───────┘                 └──────┬───────┘
       │                                │
       │ WebSocket                      │ Structured Commands
       ↓                                ↓
┌──────────────────────────────────────────────────┐
│                  Backend (FastAPI)                │
├──────────────────────────────────────────────────┤
│  ┌────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │   Agent    │→ │ Constraints │→ │Orchestrator│ │
│  │ (Parse LLM)│  │  (Safety)   │  │  (Tasks)   │ │
│  └────────────┘  └─────────────┘  └───────────┘ │
├──────────────────────────────────────────────────┤
│              Simulated Fleet State               │
│  [UGV1] [UGV2] [UGV3] [UAV1] [UAV2]             │
└──────────────────────────────────────────────────┘
```

---

## Simulation Modes

The demo supports two simulation modes, controlled by `SIM_MODE` environment variable:

### State Mode (default): `SIM_MODE=state`
- Instant position updates (teleportation)
- No physics, no animation
- Best for quick testing

### MuJoCo Mode: `SIM_MODE=mujoco`
- **Smooth motion** - platforms accelerate and decelerate realistically
- Proper velocity limits (UGV: 5 m/s, UAV: 15 m/s)
- Controllers for:
  - `go_to` - smooth path following
  - `hold` - position stabilization
  - `orbit` - UAV circular orbits
  - `follow_leader` - convoy formation with gap maintenance
  - `form_formation` - line/wedge/column formations
- 50Hz simulation tick rate

**To enable MuJoCo mode:**
```bash
SIM_MODE=mujoco python -m commander.main
```

**Note:** Full MuJoCo physics requires a compatible Python installation. If MuJoCo isn't available, the system falls back to kinematic-only simulation (smooth motion without physics collision).

### World Configuration

The MuJoCo world (`sim/assets/world.xml`) includes:
- 100m × 100m ground plane with grid
- 3 UGV robots (box-shaped with wheels)
- 2 UAV drones (quadrotor style)
- No-go zone R1 (translucent red box)
- Checkpoint markers (α, β, γ, Home)
