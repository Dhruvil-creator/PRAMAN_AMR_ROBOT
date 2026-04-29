# AUTONOMY FEATURE TEST PLANS (Templates)

Use these templates when adding features. Each feature must have: unit tests, integration tests, and field test steps.

---
Feature: path_planner (A*)
- Unit tests:
  - Empty grid: A* returns straight-line path from start to goal.
  - Obstacle cells: path avoids marked obstacles.
  - No path: returns empty with appropriate error.
- Integration tests:
  - Plug into grid_manager and verify smoothing reduces waypoint count and keeps path feasible.
- Field tests:
  - Plan a short path and verify robot follows it under supervision.

---
Feature: motion_controller (PID & alignment)
- Unit tests:
  - PID compute sanity checks (step response, stability under simulated gyro noise).
- Integration tests:
  - Align-to-waypoint test using mocked IMU yaw.
- Field tests:
  - On-device tuning: verify align stop threshold; ensure manual endpoints unaffected.

---
Feature: sensor_manager (threaded hub)
- Unit tests:
  - Mock sensors: ensure get_sensor_snapshot() returns expected structure and keys.
- Integration tests:
  - Ensure sensor reads don't block main loop under synthetic load.
- Field tests:
  - Confirm ultrasonic/gas/PIR readings match raw sensor modules when both active.

---
Feature: grid_manager
- Unit tests:
  - Coordinate conversion (world <-> grid) correctness.
  - Incremental updates and TTL expiry behavior.
- Integration tests:
  - Connect sensor_manager simulated events to grid updates.
- Field tests:
  - Verify obstacles and hazards marked correctly for known sensor placements.

---
Feature test template (use per-feature):
- Feature name: <>
- Unit tests: list
- Integration tests: list
- Field test steps: list (safety checks first)
- Acceptance criteria: list (pass/fail conditions)

General test checklist for any new feature:
1. Add unit tests under tests/ (CI friendly).
2. Add integration tests using mocks/simulation harness.
3. Add field test plan file under docs/autonomy_rebuild/field-tests/<feature>.md.
4. Add regression test that manual endpoints remain functional.
