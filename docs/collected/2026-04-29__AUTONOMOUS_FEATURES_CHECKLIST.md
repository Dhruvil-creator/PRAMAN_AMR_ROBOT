# Source: AUTONOMOUS_FEATURES_CHECKLIST.md
# Created: 2026-04-29T16:24:20+05:30
# Last commit: 2026-04-29T16:24:20+05:30

# PRAMAN AMR - Autonomous Features Checklist

This document lists all autonomous features implemented so far, with a brief description and a simple test for each. Use this as a verification checklist before further additions.

---

## ✅ Core Autonomous Features (Phase 2)

| # | Feature | Description | Test Procedure |
|---|---------|-------------|---------------|
| 1 | A* Pathfinding | Plans optimal path on grid map | Set start/goal, run A*, verify blue path appears |
| 2 | Grid Visualization | Canvas-based field map, obstacles auto-update | Place obstacles, see grid update in real-time |
| 3 | Mode Switching | Manual/Autonomous toggle, safe transitions | Switch modes, verify controls enable/disable |
| 4 | Real-time Sensor Integration | Ultrasonic → grid, 100ms polling | Place object, see obstacle on grid instantly |
| 5 | Dynamic Path Replanning | Replans if obstacle blocks path | Block path during run, see new path generated |
| 6 | Servo Automation | 75°→120°→75° on detection | Trigger proximity/metal, observe servo motion |
| 7 | Metal Detection Integration | Servo triggers on metal | Place metal, servo should activate |
| 8 | Status Monitoring | 200ms frontend polling, live updates | Observe status bar/grid, see live changes |
| 9 | Manual Mode Preservation | Manual controls always work | Switch to manual, verify direct control |
|10 | Error Handling & Safety | Graceful stop, no crashes | Induce error, system should recover safely |

---

## 🛠️ Phase 3 Additions (In Progress)

| # | Feature | Description | Test Procedure |
|---|---------|-------------|---------------|
|11 | DWA Velocity Control | Smooth, safe motion (local planner) | Run execute, robot moves smoothly, avoids obstacles |
|12 | Position Tracking | Real-time robot position on grid | Robot icon follows real robot on UI |
|13 | Field Testing | Hardware validation | Run all above on real robot, confirm behavior |

---

## How to Use
- For each feature, follow the test procedure and check if the system behaves as described.
- If any feature fails, note the issue for debugging before adding new features.

---

**Last updated:** Phase 3 development
