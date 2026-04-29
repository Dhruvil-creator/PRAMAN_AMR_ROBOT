# PRAMAN AMR — Autonomous Rebuild Overview

Objective
---------
Rebuild the entire autonomous system from scratch. Must be independent of manual mode, testable, and safe. Manual controls, motor driver, GPIO mapping, and sensor read logic must NOT be changed.

Backups
-------
All previous autonomous code has been backed up under backend/autonomy_backup_* in the repository root.

Key modules to implement
------------------------
- autonomous_controller.py  — main loop & state machine (INIT, ALIGN, PLAN_PATH, MOVE, OBSTACLE_DETECTED, HAZARD_DETECTED, REPLAN, STOP, COMPLETE)
- path_planner.py           — A* on center-based 50x50 grid + smoothing
- motion_controller.py     — PID-based alignment & node-to-node motion
- sensor_manager.py        — Threaded non-blocking sensor hub (ultrasonic, metal, gas, PIR, camera)
- grid_manager.py          — 50×50 center-origin occupancy grid; cell_size_cm=10
- event_manager.py         — event handling (obstacle/hazard/gas/stop)
- dashboard_sync.py        — real-time sync to dashboard (SocketIO/REST)

Grid conventions
----------------
- Grid size: 50×50
- Cell size: 10 cm
- Robot origin: (0,0) at grid center
- Axis: +X forward, +Y left

Mode separation
---------------
- Manual code remains unchanged. Autonomous modules claim/release motor control via a small API; manual retains priority.

Starter tasks (in progress)
---------------------------
- autonomy-code-review (audit old autonomous for reusable pieces)
- autonomy-grid-config (define constants and utils)
- autonomy-sensor-manager (start implementing non-blocking sensor hub)
- autonomy-grid-manager (implement grid structure)

Next steps
----------
1. Complete code review and extract safe, testable sensor functions.
2. Implement grid manager & path planner unit tests.
3. Implement motion controller and basic controller skeleton.
4. Incrementally integrate components with extensive tests and no changes to manual paths.

Contact
-------
- This document is the authoritative rebuild plan. Update docs/autonomy_rebuild/TASKS.md when tasks progress.
