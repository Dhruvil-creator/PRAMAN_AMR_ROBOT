AUTONOMOUS FEATURE PROGRESS
==========================

Created: 2026-04-26T10:03:10Z
Owner: PRAMAN AMR team
Purpose: Single source-of-truth tracking of completed/in-progress/pending autonomous feature work.  This document will be updated after each feature is implemented in main code and after each test evaluation.

UPDATE POLICY
-------------
- After any feature code change in main (backend/ or frontend/), the feature author will: commit with message: "feat(autonomy): <todo-id> - <short description>".
- After deployment, this progress doc will be updated with: completed feature, commit/hash (if available), files changed, and a planned test evaluation (steps + acceptance criteria).
- Tests are performed on hardware by the operator. Operator records pass/fail in this document and provides feedback.

SUMMARY (CURRENT)
-----------------
Completed features (already in repo):
- Phase 2 Autonomous rewrite (backend/autonomous.py) — Phase 2 clean implementation (status: done)
- Motor PWM logging (motor.py) — non-breaking logging for PWM commands (done)
- Safety docs: AUTONOMOUS_FEATURE_PLAN.md, SAFETY_IMPLEMENTATION_REPORT.md, IMPLEMENTATION_VERIFICATION.txt (done)
- Backup of previous autonomous version: backend/autonomous_broken_backup.py (done)

In-progress (marked in tracker):
- sensor-fusion — Integrate & normalize sensors into unified /sensor-data endpoint (status: in_progress)

UPDATE 2026-04-26T10:09Z: Sensor-fusion implementation in CODE (in-progress -> deployed to repo)
Files added/modified (sensor-fusion):
- backend/sensors/manager.py         (new)  — background SensorHub (smoothing + snapshot)
- backend/data_model.py              (modified) — now prefers SensorHub snapshot for /sensor-data
- backend/server.py                  (modified) — starts SensorHub during initialize_system

Notes: SensorHub provides get_payload() that matches the existing /sensor-data shape. The hub runs a daemon thread sampling sensors at ~100ms and applies light exponential smoothing. Next: run hardware test evaluation described below and mark sensor-fusion DONE after verification.

Pending (todo list) — PRIORITIZED TO FOLLOW USER WORKFLOW (manual controls untouched):
1. init-orientation (Initialization & Orientation Alignment) — done
2. sensor-parallel (Ensure sensors sample in parallel and never pause) — done
3. path-execution (A* execution + IMU PID integration) — done
4. hazard-mapping — done
5. grid-incremental (Incremental grid updates & visited path marking) — done
6. costmap-hazard-penalty — done
7. dynamic-replanning — done
8. servo-marker-system — done
9. camera-integration — pending
10. ui-dashboard-enhancements — done (visualization added)
11. testing-suite & field-testing — pending
12. simulation-environment — pending
13. docs-and-training — pending
14. deployment-and-monitoring — pending

Note: Manual control system remains the authoritative layer. Autonomous features must be implemented as additional layers that never modify manual control logic or GPIO mapping.

IMPLEMENTATION & TEST PLAN: SENSOR-FUSION (THIS SPRINT)
-----------------------------------------------------
Goal: produce a robust sensor-fusion pipeline that publishes normalized sensor readings to GET /sensor-data and updates grid/hazard layers used by planner.

Subtasks:
1) Review existing sensor reading functions (ultrasonic.py, imu.py, metal sensor, MQ2/MQ135 readouts) and identify standard JSON schema.
2) Implement a central sensor module (backend/sensors.py) with:
   - read() -> {timestamp, ultrasonic:{center,left,right}, metal_detector:{detected}, mq2:{ppm}, mq135:{ppm}, pir:{motion}, imu:{accel,gyro}}
   - validation + smoothing (median or exponential smoothing)
   - normalization & confidence field
   - publish to internal callback used by AutonomousModeManager and HTTP /sensor-data
3) Update AutonomousModeManager.get_sensor_data_func to use new sensors module
4) Add unit tests (mocking hardware) for read() -> JSON schema and smoothing

Sensor-Fusion Test Evaluation (Hardware):
- Preflight: reboot, start backend: ./start.sh, open dashboard
- Step 1: GET /sensor-data -> confirm JSON includes all sensors and timestamp
- Step 2: Stationary baseline: observe stable readings for 30s (no crashes)
- Step 3: Ultrasonic functional test: place hand at 10cm, 20cm, 40cm; confirm center/left/right show expected drop; grid updates within 200ms
- Step 4: Metal detection: present metal object -> /sensor-data metal_detector.detected true; servo triggers (if servo_enabled)
- Step 5: Gas sensors: test with safe gas sample (if available) -> MQ2/MQ135 PPM change and hazard flag set in map (if threshold exceeded)
- Step 6: PIR: motion triggers camera and log
- Acceptance criteria: all steps produce expected changes; no backend exceptions in logs; grid obstacle/hazard layers update and planner receives updates

Artifacts to update after completion:
- This progress doc: mark sensor-fusion as DONE with files changed and test results
- Detailed test report file: docs/sensor-fusion-test-report.md (create)
- Update todos table: set sensor-fusion -> done

WORKFLOW & COMMUNICATION
------------------------
- Development strategy: iterative, one feature at a time (sensor-fusion -> hazard-mapping -> planner enhancements).
- After each feature: implement, create PR (if using git), update this doc with brief changelog, add test plan, run the tests, record results.
- User feedback loop: operator runs tests and returns feedback; next actions are scheduled and documented here.

NEXT ACTION (requested):
- Begin sensor-fusion implementation (status: in_progress). After implementation: push code, update this doc with changed files and test plan, then run hardware tests.

Notes:
- The dashboard will be updated to show hazard layers and persisted obstacles after hazard-mapping and UI enhancements tasks.
- If any safety issue arises, use rollback (autonomous_broken_backup.py) and report immediately.



UPDATE 2026-04-26T10:30Z: Quick fix — frontend crash (dashboard.js TypeError: reading 'charAt') caused by SensorHub snapshot missing 'status' fields. Fixed in backend/data_model.py: SensorHub snapshot now converted through build_payload(...) so gas.mq2.status and ultrasonic.status are present. Restart backend to apply. Files changed: backend/data_model.py. QA: reload dashboard and confirm console no longer shows the charAt error.



UPDATE 2026-04-26T10:40Z: Started hazard-mapping (status -> in_progress).
Files changed:
- backend/autonomous.py (modified) — added obstacle inflation (self.obstacle_inflation) and expanded grid-update logic so detected obstacles now inflate to neighbouring cells; preserves obstacle TTL and timestamps.

QA / Test checklist (quick):
1. Restart backend: ./start.sh
2. Confirm logs: "Sensor hub started" and "System ready"
3. Start autonomous execution in a safe area or simulate path; present an obstacle within 10-40cm and observe grid update: inflated cells should be marked as obstacles for ~1s
4. Verify immediate stop behavior at <=12cm and that replan occurs around inflated cells

Next steps: implement costmap hazard penalties (todo: costmap-hazard-penalty) to prefer safer paths rather than binary blocked cells.

UPDATE 2026-04-26T11:20Z: Safety tweak — increased immediate obstacle_stop_distance from 12cm to 20cm to make the robot stop earlier when obstacles are detected in front of it. This means:
- Immediate hard-stop now triggers when nearest obstacle <= 20cm (previously 12cm).
- Replanning behavior and obstacle inflation remain unchanged.
Files changed: backend/autonomous.py

QA / Test checklist for safety tweak:
1. Restart backend: ./start.sh
2. Plan and execute a short path as before.
3. Place the box at ~15cm in front of the ultrasonic sensor.
   - Expected: robot should perform an immediate stop (motor PWM -> 0), status transitions to 'paused' and obstacle_log will show an 'Immediate proximity stop' entry.
   - Grid should show inflated obstacle cells around the detected coordinate for ~1s.
4. To resume: use /autonomous/resume or re-run execute after clearing obstacle.



UPDATE 2026-04-26T11:45Z: Proximity drop behavior implemented (status -> done).

UPDATE 2026-04-26T13:08Z: Log analysis — 400 (Bad Request) on /autonomous/execute
- Observed multiple 400 responses for POST /autonomous/execute in server.log (18:34:29, 18:35:44, 18:35:47). Likely causes: front-end attempted execute without a planned path or while autonomous execution was already running ("Already executing").
- Action items: add backend error logging for 4xx responses; return 409 for "Already executing"; disable execute button in frontend until plan success; add integration tests for execute/plan ordering.

UPDATE 2026-04-26T13:13Z: Backend fix applied
- /autonomous/execute now logs failure reasons and returns 409 Conflict for 'Already executing' cases; 400 remains for other client errors. A success log line is printed when execution starts.
- Next: expose runtime tuning endpoint /autonomous/params (adding now) and run a full simulation + hardware test.


Files changed:
- backend/autonomous.py (modified) — added proximity-drop pause and marker behavior: when an obstacle is detected within obstacle_stop_distance while executing, the robot pauses for proximity_drop_pause (1.5s), triggers servo action (75→120→75) to drop marker, logs event with action 'drop', then resumes execution. If obstacle persists, a replan is requested.

QA / Test checklist for proximity-drop:
1. Restart backend: ./start.sh
2. Plan & execute a path in a safe area.
3. Place marker/box ~10–20cm in front of ultrasonic while executing.
   - Expected: robot pauses ~1.5s, servo pulses (75→120→75) to drop marker, grid shows obstacle cells (red), obstacle-log will include an entry with reason 'Proximity drop' and action 'drop', then robot resumes.
4. If obstacle remains after resume: replan is requested and status changes accordingly.

Notes: Configurable parameters: obstacle_stop_distance, proximity_drop_pause, drop_cooldown. Files changed: backend/autonomous.py. Updated todos: 'proximity-drop' added.

-END
