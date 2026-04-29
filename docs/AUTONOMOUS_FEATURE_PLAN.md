AUTONOMOUS MULTI-SENSOR DECISION SYSTEM — SPEC & IMPLEMENTATION PLAN
================================================================================

Version: 0.1
Date: 2026-04-26
Status: DRAFT

1. Executive summary
--------------------
Goal: build a safe, field-ready autonomous system that scans an unknown environment with multiple sensors, constructs a hazard-aware grid, plans a "safe corridor" using an enhanced A* (hazard-penalty + safe margin), executes motion with IMU+PID stabilization, and physically marks confirmed hazards with a servo marker.

Acceptance: manual controls remain fully functional; autonomous mode reliably stops for hazards, replans, and marks verified hazards; no motor runaway.

2. High-level architecture
--------------------------
- Sensors: ultrasonic (center/left/right), metal detector, MQ2, MQ135, PIR, camera, IMU (MPU6050)
- Sensor pipeline: read -> validate -> timestamp -> normalize -> fuse
- Map: 2D grid (10 cm cell) with layers: occupancy, hazard (metal/gas), confidence, temporal persistence
- Planner: A* over costmap; cost = base + hazard_penalty + inflation
- Controller: IMU-assisted PID velocity/heading controller + speed limiter
- Actuators: differential drive motors, servo marker
- Dashboard: visualization, planning controls, status, logs

3. Map & data model
-------------------
- Grid cell: 10cm
- Layers:
  - occupancy: free/occupied
  - hazard: metal/gas (penalty value)
  - confidence: floating 0..1
  - temporal TTL: obstacle persistence (configurable ~1.0s)
- Costmap construction: occupancy cells = INF, hazard cells = base_cost + penalty
- Inflation: expand occupancy/hazard with radius = safe_margin (configurable, e.g., 30cm)

4. Sensor fusion & hazard detection
-----------------------------------
- Normalization: convert raw to comparable confidence and distance
- Fusion algorithm: weighted rules + thresholds
  - metal detector: high-priority, immediate hazard (flag & mark)
  - gas / MQ2 / MQ135: if above threshold -> hazard layer with penalty proportional to ppm
  - PIR: presence increases confidence for marking; triggers camera capture
- Persistence/hysteresis: store obstacle timestamps, expire after TTL
- Output: per-cycle updates: occupancy changes, hazard flags, nearest distances

5. Planner: Enhanced A*
------------------------
- Cost function: g(n) + h(n) where traversal cost includes hazard penalties
- Hazard penalty: large multiplier for metal, mid for gas, small for uncertain obstacles
- Safe margin: inflate obstacles by safe_margin cells before planning
- Smoothing: post-plan smoothing (path short-cutting) but keep waypoints conservative
- Tie-breaking: prefer higher-safety route over strictly shorter route

6. Dynamic replanning & triggers
--------------------------------
Triggers:
- nearest distance < obstacle_stop_distance (immediate stop + replan)
- new hazard detected (metal/gas)
- path becomes blocked (path node now occupied)

Behavior:
- immediate hard-stop if nearest <= stop_distance
- mark grid & persist obstacle timestamp
- request replan (cooldown to avoid flapping)
- if replan fails -> pause and alert dashboard

7. Motion control: IMU + PID
----------------------------
- Heading stabilization using IMU + PID loop to maintain trajectory between waypoints
- Velocity control: ramp/shaping; slowdowns when turning or near hazards
- Safety: motor watchdog, current sensing (if available), immediate stop on command

8. Servo marker system
----------------------
- Trigger conditions: confirmed metal reading + camera confirm (optional)
- Safety checks before drop: robot stopped, motors disabled, GPS/position stable
- Action: servo sequence 75° -> 120° hold -> 75°; record marker GPS/grid cell
- Audit: dashboard logs marker event with timestamp and evidence

9. Camera & human confirmation
------------------------------
- On PIR or metal trigger, capture image and attach to alert
- Optional ML model for object/hazard classification (future)

10. APIs & dashboard integration
--------------------------------
- GET /sensor-data — latest normalized sensor readings
- GET /autonomous/status — mode, status, pos, nearest obstacle, progress
- POST /autonomous/plan {start,goal} — returns path
- POST /autonomous/execute {path_id} — starts execution
- POST /autonomous/stop — immediate stop
- POST /autonomous/mark — manual hazard mark (for operator)
- GET /autonomous/logs — obstacle/hazard log

11. Safety & watchdogs
----------------------
- Manual override always preempts autonomous actions
- Emergency stop: physical button + API + dashboard
- Motor watchdog: if no heartbeat from controller or sensor thread errors -> stop motors
- Logging: persistent local logs for post-mortem and telemetry
- Simulation fallback: run path in sim before field test

12. Testing & acceptance criteria (high level)
---------------------------------------------
- Sensors: all sensors report valid, consistent readings on /sensor-data
- Grid: placing hand in front updates occupancy within 100ms and grid shows obstacle
- Planner: path avoids hazard zones and respects safe margin
- Replanning: inserting a dynamic obstacle causes hard-stop + replanning
- Servo: metal detection triggers marker sequence and logs event
- Stability: 5-minute continuous autonomous run without motor runaway
- Manual safety: manual control always works after switching back

13. Implementation roadmap & to-do list
---------------------------------------
Integration-first priority (preserve manual control at all costs):
  NOTE: autonomous features must be implemented as a separate execution layer. Manual control logic and GPIO mappings MUST NOT be modified.

Priority order (implements core safe corridor and the user's integration workflow):
  1. init-orientation (Initialization & Orientation Alignment) — read IMU yaw, compute heading to first waypoint, rotate to align before any forward motion
  2. sensor-fusion & sensor-parallel — normalize and publish sensors (ultrasonic, metal, MQ2, MQ135, PIR, IMU, camera) and ensure thread-parallel sampling (never pause during navigation)
  3. path-execution + imu-pid-motion-control — A* path execution, IMU-based PID heading stabilization, node-to-node motion with pre-turn/turn/post-turn speed shaping
  4. real-time obstacle handling — ultrasonic front/left/right multi-sensor validation, immediate stop/confirm (200–300ms), grid update, replan on blocked path
  5. hazard-mapping & grid-incremental — occupancy + hazard layers, TTL persistence, incremental grid updates (mark visited/obstacle/hazard nodes)
  6. costmap-hazard-penalty & dynamic-replanning — apply hazard penalties in cost function; replan only when necessary (cooldown)
  7. servo-marker-system (hazard marking) — edge-triggered metal detection: pause 1–2s, servo drop (75→120→75), mark grid cell, log event (drop once per detection)
  8. dashboard integration & ui-dashboard-enhancements — real-time updates: path, obstacles, hazards, sensor readings, mode & action
  9. testing-suite & field-testing — unit tests, hardware integration tests, 5-minute stress run, HIL tests
 10. simulation-environment & deployment — simulator, replay logs, deployment and monitoring

Detailed todo items (tracked in task system, mapped to repo IDs):
  - init-orientation: Initialization & Orientation Alignment — pending
  - sensor-fusion: Implement sensor fusion pipeline — done
  - sensor-parallel: Ensure sensors sample in parallel and never pause during navigation — pending
  - path-execution: A* execution + waypoint following & pre-turn alignment — pending
  - imu-pid-motion-control: Integrate IMU + PID for heading stabilization — pending
  - real-time-obstacle: Real-time obstacle handling (confirm + mark + replan) — pending
  - hazard-mapping: Implement hazard layers & TTL persistence — in_progress
  - grid-incremental: Incremental grid updates (visited, obstacle, hazard markers) — pending
  - costmap-hazard-penalty: Add hazard-penalty to A* costmap — pending
  - dynamic-replanning: Implement dynamic replanning, immediate-stop + cooldown — pending
  - servo-marker-system: Servo-based marker drop system (safe-drop flow & logging) — pending
  - proximity-drop: Proximity drop pause & servo (implemented helper) — done
  - camera-integration: Capture images on triggers & attach to alerts — pending
  - ui-dashboard-enhancements: Hazard overlay, logs, marker UI — pending
  - testing-suite: Unit & integration tests + field test checklist — pending
  - simulation-environment: Build sim/replay for offline testing — pending
  - docs-and-training: Operator guide + safety manual — pending
  - deployment-and-monitoring: Telemetry, remote logs, process supervision — pending

Notes:
- The above maps user's 10-point workflow into a prioritized implementation roadmap. Each todo should be executed incrementally and tested on hardware only after a code review and a safe preflight (sim or staged test).
- Next immediate steps: implement init-orientation and path-execution integration with imu-pid-motion-control and sensor-parallel behavior so the robot aligns before moving and sensor threads keep running.

14. Risks & mitigations
-----------------------
- False positives on metal/gas: add camera confirmation and confidence thresholds
- Sensor noise & flapping: use TTL/hysteresis and replan cooldown
- Motor runaway: hardware watchdog + software hard-stop + motor current monitor
- Marker accidental drop: confirm stationary + double-confirm trigger

15. Additional recommendations
------------------------------
- Create a hardware-in-the-loop simulator to test dynamic replanning safely
- Implement replayable sensor logs for offline debugging
- Add unit tests around grid updates, planner costs, and replanning triggers
- Add a configurable safety profile (aggressive vs conservative) for live demos
- Add persistent telemetry export (CSV/Influx) for post-run analysis

16. Next immediate steps (suggested)
-----------------------------------
1. Run sensor-fusion smoke tests and publish /sensor-data correctness
2. Implement obstacle TTL and grid updates (verify UI shows obstacles)
3. Add immediate-stop and replan hook (repeat tests)
4. Integrate IMU PID basic heading hold
5. Run combined field test: plan -> execute -> dynamic obstacle -> verify stop+replan

---

End of document.
