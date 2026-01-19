# Commander Demo Script

## Overview

This is a 5-minute investor demo showcasing LLM-powered multi-robot orchestration with safety constraints.

**Total Duration:** ~5 minutes  
**Platforms:** 3 UGVs (ground robots) + 2 UAVs (drones)  
**Key Highlights:** Natural language control, smooth motion, safety guardrails, real-time visualization

---

## Pre-Demo Setup

1. Start the backend:
   ```bash
   cd commander-demo/backend
   source .venv/bin/activate
   SIM_MODE=mujoco python -m commander.main
   ```

2. Start the frontend:
   ```bash
   cd commander-demo/frontend
   npm run dev
   ```

3. Open browser to http://localhost:5173

4. Verify:
   - Connection status shows "CONNECTED" (green)
   - 5 platforms visible on MiniMap (3 green squares, 2 purple triangles)
   - All platforms show "IDLE" status

---

## Demo Script (5 Scenes)

### Scene 1: Fleet Status Report (30 seconds)
**Goal:** Establish situational awareness

**Action:** Click "START DEMO" or type:
> "Report status of all platforms"

**What Happens:**
- System queries all 5 platforms
- Fleet status cards update with current positions
- Timeline shows "report_status" event

**Talking Points:**
- "Let me first get a status report of our fleet"
- "We have 3 ground vehicles and 2 aerial drones"
- "All systems nominal, ready for tasking"

---

### Scene 2: Convoy Formation to Alpha (60 seconds)
**Goal:** Demonstrate coordinated ground movement

**Action:** The demo will execute:
> "Form convoy with all ground robots, UGV1 leads, 3 meter gap"
> "Move the convoy to checkpoint alpha"

**What Happens:**
- UGVs form a line formation (leader + 2 followers)
- Convoy moves smoothly from origin to checkpoint Alpha (20, 30)
- Platforms maintain 3m spacing throughout movement
- MiniMap shows coordinated movement

**Talking Points:**
- "Now let's coordinate our ground vehicles"
- "Watch how they maintain formation spacing automatically"
- "This is all natural language - no coding required"

---

### Scene 3: Wedge Formation to Bravo (60 seconds)
**Goal:** Demonstrate dynamic formation change

**Action:** The demo will execute:
> "Reform into wedge formation"
> "Move to checkpoint bravo"

**What Happens:**
- UGVs transition from line to V-shaped wedge
- Formation moves to checkpoint Bravo (40, 45)
- Smooth coordinated motion throughout

**Talking Points:**
- "Formations can change dynamically"
- "The wedge provides better situational awareness"
- "Each robot maintains its relative position"

---

### Scene 4: Aerial Support (60 seconds)
**Goal:** Demonstrate UAV capabilities

**Action:** The demo will execute:
> "UAV1 orbit above checkpoint bravo at 20 meters altitude, 8 meter radius"
> "UAV2 spotlight the convoy"

**What Happens:**
- UAV1 moves to orbit position and begins circular flight
- UAV2 positions for spotlight/observation
- Both drones visible on MiniMap at altitude
- Timeline shows orbit and spotlight commands

**Talking Points:**
- "Now let's bring in aerial support"
- "UAV1 is providing persistent overwatch"
- "UAV2 is spotlighting our ground convoy"
- "All coordinated through natural language"

---

### Scene 5: Safety Constraints Demo (90 seconds)
**Goal:** Demonstrate safety guardrails

**Action:** The demo will execute:
> "Move UGV2 to position -15, -15"

**What Happens:**
- Command is REJECTED by safety constraints
- Error message: "Path crosses restricted zone R1"
- Timeline shows "constraint_violation" event
- Suggestion provided for alternate waypoint

**Then:** The demo will execute:
> "Move UGV2 to position -25, -5"

**What Happens:**
- This path avoids the no-go zone
- UGV2 moves smoothly to the safe position
- Demonstrates the system respects safety boundaries

**Talking Points:**
- "But what about safety? Let me try something dangerous..."
- "The system rejected that - the path would cross our restricted zone"
- "These guardrails run OUTSIDE the AI - they can't be bypassed"
- "Let me route around the obstacle instead..."
- "Now we have a safe path"

---

### Finale: Stop All (15 seconds)
**Goal:** Clean ending

**Action:** The demo will execute:
> "Stop all platforms"

**What Happens:**
- All movement ceases immediately
- Platforms hold current positions
- Status changes to "IDLE"

**Talking Points:**
- "And we can stop everything with a single command"
- "That's LLM-powered robot orchestration with safety constraints"

---

## One-Click Demo Mode

The **START DEMO** button in the UI runs this entire script automatically with proper timing:

| Step | Scene | Command | Delay After |
|------|-------|---------|-------------|
| 0 | Status | Report status of all platforms | 3s |
| 1 | Convoy | Form convoy with all ground robots, UGV1 leads, 3 meter gap | 4s |
| 2 | Move | Move the convoy to checkpoint alpha | 8s |
| 3 | Wedge | Reform all ground robots into wedge formation | 4s |
| 4 | Move | Move the formation to checkpoint bravo | 8s |
| 5 | Orbit | UAV1 orbit above checkpoint bravo at 20 meters, 8 meter radius | 5s |
| 6 | Spotlight | UAV2 spotlight checkpoint bravo | 3s |
| 7 | Violation | Move UGV2 to position -15, -15 | 4s |
| 8 | Safe Path | Move UGV2 to position -25, -5 | 5s |
| 9 | Stop | Stop all platforms | 2s |

**Total automated runtime:** ~46 seconds + motion time ≈ 2-3 minutes

---

## Post-Demo: Replay from Logs

After running the demo, you can replay the session:

1. **Export the session:**
   - Click "EXPORT" button to download JSONL file
   - Or: `curl http://localhost:8000/api/v1/replay/export`

2. **Load for replay:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/replay/load \
     -H "Content-Type: application/json" \
     -d @commander-replay-2026-01-20.jsonl
   ```

3. **View in UI:**
   - Timeline shows all recorded events
   - Can scrub through event history

---

## Troubleshooting

### "Gemini API key not valid"
→ Set your API key in `backend/.env`:
```
GEMINI_API_KEY=your-key-here
```

### Platforms don't move smoothly
→ Ensure `SIM_MODE=mujoco` when starting backend

### Demo gets stuck
→ Check terminal for errors, restart backend if needed

### Commands fail with timeout
→ Restart backend to reset platform heartbeats

---

## Direct API Commands (for testing)

You can also run scenes manually via API:

```bash
# Scene 1: Status
curl -X POST http://localhost:8000/api/v1/commands \
  -d '{"command": "report_status", "target": "all", "params": {}}'

# Scene 2: Convoy
curl -X POST http://localhost:8000/api/v1/commands \
  -d '{"command": "follow_leader", "target": "ugv_pod", "params": {"leader": "ugv1", "gap_m": 3}}'

# Scene 5: Constraint test (will fail)
curl -X POST http://localhost:8000/api/v1/commands \
  -d '{"command": "go_to", "target": "ugv2", "params": {"x": -15, "y": -15}}'
```
