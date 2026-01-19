PRD v1: commander demo, mujoco + gemini agent orchestrator
1) summary

Build a laptop-runnable demo that shows an LLM-powered “commander” executing complex multi-step tasks end-to-end by decomposing natural language into validated atomic capabilities and orchestrating them across a small fleet in simulation.

Core wow sentence (exec/investor):
“I can type a complex mission-level request, and the commander decomposes it into safe, executable steps and coordinates multiple platforms to complete it end-to-end.”

2) goals
product goals

Demonstrate an end-to-end “command → plan → execute → observe → adapt” loop.

Show progression of capability:

single platform control

homogeneous pod control

heterogeneous pod control

sequencing + constraints + deconfliction (at least as a preview)

full mission profile (at least as a preview)

credibility goals

Make it obvious to executives/investors that:

there is a playbook (allowed actions, not free-form),

the system is safe-by-construction (constraints enforced outside the model),

logs make it auditable (traceability, replay).

3) non-goals

No real robot/hardware integration in v1.

No weaponization/attack behaviors. “Laser pointer / spotlight” is only a non-destructive targeting/attention primitive.

No role-based access control in v1 (single admin/operator mode).

No full autonomy stack research. We implement plausible behaviors (nav, formation, hold), not publish-grade algorithms.

4) target users

Primary: executive stakeholders, investors.

Secondary: internal engineering and product teams (as a platform starter).

5) environment and platforms
simulation

Mujoco as the primary visual + physics environment.

Abstract environment (simple obstacles, open space). Can optionally add “orchard-row-like lanes” later if it helps storytelling.

platforms

Assumption (adjustable): 5 total platforms:

3 UGV (ground robots)

2 UAV (drones)

Each platform supports:

navigation to a pose / checkpoint

relative awareness of others (“radar” abstraction)

basic behaviors: hold, convoy, formation, orbit/overwatch, return-to-home

state reporting: position, velocity, battery (simulated), health flags (simulated)

6) demo concept

You type a mission request in English (text-only input v1). Gemini acts as the agent that:

interprets intent,

converts to structured commands,

calls orchestrator functions,

monitors execution,

updates plan if constraints/conditions require.

7) functional requirements
7.1 command surface

Text input in English.

Optional later: GUI buttons for common commands (not required for v1).

7.2 playbook (must be defined from scratch)

A strict catalog of allowed commands, with schema validation. Example categories:

navigation

go_to(platform|pod, waypoint|pose, speed?)

return_home(platform|pod)

hold_position(platform|pod, duration?)

patrol(platform|pod, waypoints, loop?)

coordination

form_formation(pod, type=[line|wedge|column], spacing_m, leader?)

follow_leader(pod, leader_id, gap_m) (convoy)

assign_roles(pod, roles={uav_overwatch, ugv_scout, ...})

observation / marking (non-weapon)

point_laser(uav_id, target_pose|target_id, duration?)

spotlight(uav_id, target_pose|target_id, duration?)

orbit(uav_id, center_pose|target_id, radius_m, altitude_m)

diagnostics

report_status(platform|pod)

report_faults(platform|pod)

set_mode(platform|pod, mode=[manual_sim|autonomy]) (sim-only switch)

7.3 “radar” abstraction

Each platform has a local perception primitive that can report:

nearby obstacles (range/bearing)

nearby allies (range/bearing and id)

In v1 it can be “perfect sim truth + noise” so it’s reliable and predictable.

7.4 orchestrator behavior

Convert playbook commands into executable controller goals for each platform.

Maintain:

platform states

pod membership

active tasks

task status (queued/running/succeeded/failed)

Provide feedback loop to agent: “what is happening now”.

7.5 conversation memory

Gemini keeps conversational context:

“Do the same but slower”

“Keep the formation, move to checkpoint bravo”

“Now have the drones orbit above them”

7.6 safety and constraints (hard requirements)

Constraints are enforced by deterministic code, not the model.

global safety constraints

min separation distance between platforms

max speed per platform type

no-go zones (optional in v1, recommended for Sprint 4 preview)

comms timeout behavior (simulated): if no update, default to hold/stop

command validation: unknown commands are rejected, never executed

uncertainty policy

If intent is ambiguous, Gemini must ask a clarifying question.

If command violates constraints, orchestrator rejects and returns a reason + safe alternative suggestions.

7.7 logging and traceability (hard requirements)

For every request:

trace id

user text

Gemini prompt context (redacted key material)

Gemini structured output / tool calls

selected playbook commands

validation results

execution timeline (state transitions)

final outcome summary
Optional: record demo run (replay) and/or save a simple “event log player”.

8) user stories

As an exec, I type: “Move the ground team to checkpoint alpha in convoy, drones provide overwatch, and mark the target with a laser.”
→ Commander executes, you see it happen, and you see the steps and constraints.

As an investor, I ask: “Now repeat it but keep 10m separation and avoid the restricted zone.”
→ System respects constraints and adapts.

As an operator, I ask: “What’s the status of all platforms?”
→ Commander returns a clean fleet status summary + highlights.

9) demo flow (5–7 minutes, suggested)

Scene 1 (30s): show UI layout

Mujoco view, minimap, platform list, chat, timeline panel.

Scene 2 (90s): single-command baseline

“UGV1 go to checkpoint alpha.”

show structured command + execution.

Scene 3 (2–3 min): pod orchestration

“Form convoy, move UGVs to checkpoint bravo, drones orbit above and spotlight the area.”

show multi-agent coordination.

Scene 4 (1–2 min): hetero + memory

“Keep the convoy, slow down, and have drone 2 mark the target with laser for 5 seconds.”

show conversational control and safe execution.

Scene 5 (30–60s): Sprint 4/5 preview

“Avoid restricted zone R1 and deconflict paths.”

even a simple no-go polygon + path re-route looks very impressive.

10) UX requirements

Must show on screen:

Mujoco 3D viewport

minimap/top-down (even a simple 2D overlay is fine)

platform cards: pose, mode, status

chat panel (user ↔ commander)

timeline/event log panel (traceable, investor-friendly)
Nice-to-have:

“command plan” preview (steps list)

replay button / run recorder

11) technical approach (proposed)
stack (laptop-friendly)

Backend: Python

Mujoco simulation loop

Orchestrator + controllers

FastAPI server

WebSocket for live state streaming

Frontend: Web UI (React or lightweight HTML/JS)

Gemini integration:

tool/function calling OR strict JSON output that backend validates

model: Gemini 1.5 Flash (confirm exact name you’ll use)

architecture blocks

UI (chat, minimap, status)

Agent service (Gemini)

Command validator (JSON schema + constraints)

Orchestrator (task graph + scheduling)

Simulation (Mujoco + platform controllers)

Logging (event store + replay)

12) milestones (mapped to your Sprint 1–5)

You said you want to deliver 1–3 strongly, and hint 4–5. So plan:

sprint 1: intent translation (software-only, no sim required, but we’ll connect sim early)

Define playbook + schemas

Implement validator and logging

Implement Gemini → structured command → mock execution
DoD: typed command produces validated playbook calls + full trace.

sprint 2: homogeneous pod control (in mujoco)

UGV nav + hold + convoy/formation (ground-only)

basic diagnostics
DoD: pod executes formation + move.

sprint 3: heterogeneous pod control

Add UAV dynamics + orbit/spotlight/laser pointer

same command language works across UGV/UAV
DoD: single command coordinates mixed team.

sprint 4 preview: constraints + deconfliction

no-go zone polygon + avoidance

min separation enforcement with rejection/auto-adjust
DoD: at least one visible “constraint saved us” moment.

sprint 5 preview: mission profiles

define a “mission script” object composed of steps and conditions

run one full mission from start to completion
DoD: one end-to-end “mission profile” demoable.

13) success criteria

must hit

end-to-end command execution works reliably on laptop

80–90% of your scripted demo commands succeed first try (because demo is scripted)

every run produces trace logs and a clean summary

wow moments

one multi-vehicle coordination command that executes correctly

one conversational modification (“same but slower / keep formation”) that works

one safety/constraint moment (no-go zone or min separation enforcement)

14) risks and mitigations

LLM unpredictability → enforce strict schemas + validation + “ask clarifying question” policy.

demo fragility → pre-scripted scenarios, deterministic seeds, and a replay option.

UI scope creep → keep UI minimal, focus on 4 panels only.

formation control complexity → start with simple leader-follower + spacing, not fancy control theory.

Mac compatibility → keep everything local, python-based, avoid heavy ROS2 dependence (ROS2 bridge optional).

