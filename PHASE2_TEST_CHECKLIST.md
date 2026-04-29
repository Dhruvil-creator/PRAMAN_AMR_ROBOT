# Phase 2 - Autonomous Feature Test Checklist

**Status:** Phase 2 Restored (2026-04-25)  
**Backend:** `backend/autonomous.py` (Phase 2 clean implementation)  
**Frontend:** `frontend/js/autonomous.js` + `frontend/dashboard.html`

---

## 🎯 Test Categories

### A. Manual Mode - Baseline (✓ Should be unaffected)
- [ ] **Forward**: Press and hold "Forward" button → Robot moves forward steadily
- [ ] **Backward**: Press "Backward" → Robot moves backward
- [ ] **Left**: Press "Left" → Robot rotates left in place
- [ ] **Right**: Press "Right" → Robot rotates right in place
- [ ] **Stop**: Press "Stop" → All motion stops immediately
- [ ] **Speed Slider**: Adjust speed 0-100 → Motor PWM changes proportionally
- [ ] **Speed Feedback**: Speed value in dashboard updates with slider changes

**Expected:** Manual controls work exactly as before Phase 3. No changes.

---

### B. Autonomous Mode Switching
- [ ] **Initial State**: Dashboard shows "Manual Mode" indicator
- [ ] **Switch to Autonomous**: Click "Switch to Autonomous Mode" button
  - Expected: Display changes to "Autonomous Mode"
  - Expected: Manual buttons become disabled (grayed out)
  - Expected: Grid canvas appears (20×15 cells)
  - Expected: Console shows "📍 Switched to autonomous mode"
- [ ] **Switch Back to Manual**: In autonomous idle state, click "Switch to Manual Mode"
  - Expected: Returns to manual mode display
  - Expected: Manual buttons enabled again
  - Expected: Console shows "🎮 Switched to manual mode"

---

### C. Grid Interaction (Autonomous Mode)
#### C1: Grid Drawing Tools
- [ ] **Set Start**: 
  - Click "Start" tool, then click on grid cell (e.g., position [5, 5])
  - Expected: Green square appears at clicked cell
  - Expected: Server shows start position confirmed
- [ ] **Set Goal**:
  - Click "Goal" tool, then click on grid cell (e.g., position [15, 10])
  - Expected: Red square appears at clicked cell
  - Expected: Server shows goal position confirmed
- [ ] **Set Wall** (Obstacle):
  - Click "Wall" tool, then click multiple cells to draw obstacles
  - Expected: Blue cells appear where you click
  - Expected: Can draw continuous walls by rapid clicking
- [ ] **Clear Wall**:
  - Click "Clear" tool, then click on blue cell
  - Expected: Blue cell turns white (cleared)
- [ ] **Clear Entire Grid**:
  - Click "Clear Grid" button
  - Expected: All walls disappear
  - Expected: Start/goal remain (or optionally clear too)

#### C2: Grid Validation
- [ ] **Grid Size**: Grid shows 20×15 cells exactly
- [ ] **Cell Coordinates**: Hover over cells → coordinates visible (0-19, 0-14)
- [ ] **Boundary Checking**: Cannot place start/goal/walls outside grid bounds

---

### D. A* Pathfinding
- [ ] **Plan Path** (No Obstacles):
  - Set start at [2, 2], goal at [18, 13]
  - Draw NO walls
  - Click "Plan Path" button
  - Expected: Yellow line drawn from start to goal (shortest diagonal path)
  - Expected: Console shows pathfinding stats (cells visited, path length)
  - Expected: Path is smooth and diagonal when possible
  
- [ ] **Plan Path** (With Obstacles):
  - Set start at [2, 2], goal at [18, 13]
  - Draw wall(s) blocking direct path (e.g., vertical wall at x=10)
  - Click "Plan Path" button
  - Expected: Path avoids obstacles, finds alternate route
  - Expected: Path is still optimal (no zigzag)
  
- [ ] **Plan with No Path**:
  - Set start at [2, 2], goal at [18, 13]
  - Draw complete walls isolating goal
  - Click "Plan Path" button
  - Expected: Error message "No path found" or similar
  - Expected: No yellow line appears on grid

- [ ] **Plan with Missing Start/Goal**:
  - Clear start/goal, try to plan
  - Expected: Error "Start or goal not set"

---

### E. Autonomous Execution (Simple Path)
**Setup:** Start at [2, 2], Goal at [5, 2] (short horizontal path, no obstacles)

- [ ] **Execute Path**:
  - Click "Execute Path" button
  - Expected: Robot status changes to "executing"
  - Expected: Console shows "[AUTONOMY] Moving to (5, 2)" repeatedly
  - Expected: Motor PWM increases (forward motion)
  - Expected: Progress bar advances (0% → 100%)
  
- [ ] **Waypoint Reached Logging**:
  - After reaching goal
  - Expected: Console shows "📍 Waypoint X reached"
  - Expected: Progress reaches 100%
  - Expected: Robot stops (motor.stop())
  - Expected: Status changes to "idle"

- [ ] **Execution Stop**:
  - While executing, click "Stop Execution" button
  - Expected: Motor stops immediately
  - Expected: "⏹️ Stopped autonomous execution" appears in console
  - Expected: Status returns to "idle"

---

### F. Sensor Integration & Obstacle Detection
**Setup:** Start at [5, 5], Goal at [15, 5], draw small wall at [10, 5]

- [ ] **Sensor Monitoring** (100ms loop):
  - Execute path with walls present
  - Expected: Console shows "[AUTONOMY SENSOR] center=XXcm left=XXcm right=XXcm" every 100ms
  - Expected: Distances update in real-time

- [ ] **Proximity Threshold Trigger** (default: 30cm):
  - Place obstacle close enough (~25-30cm ahead)
  - Execute path
  - Expected: When center distance < 30cm, replanning triggers
  - Expected: Console shows "🔄 Replanning due to: Obstacle detected"
  - Expected: Robot temporarily stops, recalculates path
  - Expected: New path avoids obstacle
  - Expected: Execution resumes (if viable path exists)

- [ ] **Complete Blockage**:
  - Place walls completely blocking path ahead
  - Execute
  - Expected: Robot stops before hitting wall
  - Expected: Status shows "paused" or "replanning"
  - Expected: Console shows "⚠️ No viable path found"

---

### G. Metal Detector & Servo Automation
**Prerequisite:** Metal sensor reading functional in sensor data

- [ ] **Servo Manual Control** (Baseline):
  - In **any mode**, click "Servo Control" panel
  - Click "Center (75°)" → Expected: servo moves to 75° (neutral position)
  - Click "Detect (120°)" → Expected: servo swings to 120° (detection pose)
  - Click "Open (180°)" → Expected: servo fully opens
  - Click "Close (0°)" → Expected: servo fully closes
  - Console should show servo angle changes

- [ ] **Metal Detection Toggle** (Manual Mode):
  - In manual mode, click "Enable Metal→Servo Link" button
  - Expected: Toggle state visible (enabled/disabled)
  - Bring metal object near sensor
  - Expected: If enabled, servo triggers (120° swing) when metal detected
  - Expected: Console shows "🔔 Metal detected! Triggering servo action..."

- [ ] **Metal Detection During Autonomous** (Autonomous Mode):
  - Switch to autonomous mode
  - Set start/goal, plan path
  - Click "Enable Metal→Servo Link" (if not already enabled)
  - Execute path
  - Bring metal object near robot
  - Expected: Servo triggers (120° swing) when metal detected
  - Expected: Autonomous may also replan (if configured)
  - Expected: Console shows "🔔 Metal detected! Triggering servo action..."

- [ ] **Servo Sequence Verification** (test_servo.py pattern):
  - Servo should follow: 75° (center) → 120° (detect) → 75° (return)
  - Timing: ~0.2s at 120° before return
  - **Manual verification**: Use oscilloscope/logic analyzer on servo PWM pin, or observe mechanical position

---

### H. Speed Control & Obstacle Avoidance
**Setup:** Start [5, 5], Goal [15, 5], varying obstacle distances

- [ ] **Max Speed** (No obstacles nearby, >50cm):
  - Execute path with clear passage
  - Expected: Motor PWM reaches max (75 by default)
  - Expected: Robot moves at steady fast speed
  - Status shows "autonomous_speed: 75"

- [ ] **Linear Slowdown** (Obstacles 30-50cm away):
  - Execute path with obstacle slowly approaching
  - Expected: Speed decreases as distance to obstacle shrinks
  - Expected: Speed linearly interpolates between min and max
  - Status shows "nearest_obstacle_cm" decreasing, speed decreasing

- [ ] **Stop Threshold** (Obstacle <12cm):
  - Obstacle very close (< 12cm detection threshold)
  - Expected: Motor PWM drops to 0
  - Expected: Motor stops (motor.stop() called)
  - Status shows "nearest_obstacle_cm: <12"

- [ ] **Speed Limits Adjustment**:
  - GET /autonomous/speed-limits → returns current min/max
  - POST /autonomous/speed-limits with {"min_autonomous_speed": 45, "max_autonomous_speed": 85}
  - Execute path
  - Expected: Motion uses new limits instead of defaults (40/75)
  - Expected: Status reflects updated limits

---

### I. Path Replanning (Dynamic Obstacles)
**Setup:** Start [2, 5], Goal [18, 5], initial clear path

- [ ] **Obstacle Detection Trigger**:
  - Execute path
  - While executing, add wall(s) in front of robot
  - Expected: Sensor detects new obstacle (center_dist < 30cm)
  - Expected: Console shows "🔄 Replanning due to: Obstacle detected"
  - Expected: Status changes to "replanning"

- [ ] **Replan Execution**:
  - After replanning triggered
  - Expected: New path calculated within ~500ms
  - Expected: Console shows "✅ Replanned: N waypoints"
  - Expected: Status returns to "executing"
  - Expected: Robot resumes toward goal on new route

- [ ] **Replan Cooldown** (0.8s minimum):
  - Trigger replanning, then immediately add another obstacle
  - Expected: Second obstacle does NOT trigger immediate replan
  - Expected: Waits ~0.8s before allowing next replan
  - Prevents excessive replanning loops

- [ ] **Obstacle Log**:
  - Execute with multiple replans triggered
  - GET /autonomous/status → check "obstacle_log" field
  - Expected: Log contains recent obstacle events with timestamps and distances
  - Expected: Last 10 events preserved

---

### J. Robot Position Tracking
- [ ] **Position Updates**:
  - Execute path from [2, 2] to [10, 10]
  - GET /autonomous/status → check "robot_position" field
  - Expected: Starts at [2, 2]
  - Expected: Position increments smoothly as movement occurs
  - Expected: Final position near [10, 10] (within waypoint tolerance of 0.75)

- [ ] **Waypoint Index**:
  - Execute path with 5 waypoints
  - Poll GET /autonomous/status → check "current_waypoint"
  - Expected: Starts at index 1 (after start position)
  - Expected: Increments as each waypoint reached
  - Expected: Reaches length-1 at final waypoint

- [ ] **Progress Bar**:
  - Dashboard shows progress % (0-100%)
  - Executing multi-waypoint path
  - Expected: Progress increments smoothly
  - Expected: Reaches 100% at completion

---

### K. Grid Recenter & Resume
- [ ] **Recenter Start**:
  - Start at [2, 2], execute to [10, 10], pause mid-execution
  - Click "Recenter Start" button
  - Expected: Grid start point moves to current robot position
  - GET /autonomous/grid → start now shows updated position

- [ ] **Resume After Pause**:
  - Pause execution (if UI supports pause)
  - Click "Resume" button
  - Expected: Execution resumes from paused state
  - Expected: Console shows status changes back to "executing"

---

### L. Error Handling & Safety
- [ ] **No Crash on Bad Input**:
  - Try to set invalid grid coordinates (>20, >15)
  - Expected: Error message, no crash
  
- [ ] **Mode Lock During Execution**:
  - Execute autonomous path
  - Try to send manual command (forward/left/right)
  - Expected: Manual command is **rejected** or ignored
  - Expected: Console shows "Manual control disabled in autonomous mode"
  - Expected: SocketIO ack shows rejected: true
  
- [ ] **Safe Stop on Error**:
  - Trigger any error condition (e.g., sensor read failure)
  - Expected: Motor stops
  - Expected: Status shows 'error'
  - Expected: No runaway motion

---

### M. Frontend UI & Dashboard
- [ ] **Mode Indicator**: Shows "Manual Mode" or "Autonomous Mode" clearly
- [ ] **Mode Switch Buttons**: Buttons visible and functional for switching modes
- [ ] **Grid Canvas**: Renders correctly (20×15 cells, responsive size)
- [ ] **Tools Panel**: Start/Goal/Wall/Clear tools visible and clickable
- [ ] **Action Buttons**: Plan, Execute, Stop, Clear Grid, Recenter buttons visible
- [ ] **Status Panel**: Shows current position, waypoint, progress, obstacle distance
- [ ] **Obstacle Log**: Displays last 10 replan/obstacle events with timestamps
- [ ] **Speed Control**: Min/max speed limits displayed; adjustable
- [ ] **Servo Control**: Servo angle buttons visible and responsive
- [ ] **Metal Detector Toggle**: Button shows current state (enabled/disabled)
- [ ] **Progress Bar**: Fills as path executes
- [ ] **Console/Logging**: Real-time console shows all print statements

---

### N. Performance & Stability
- [ ] **20Hz Execution Loop**: Path execution commands sent at 20Hz (50ms cycle)
  - Expected: smooth, responsive motion (not jerky)
  
- [ ] **100ms Sensor Polling**: Sensor updates every 100ms
  - Expected: Real-time obstacle detection responsive within 200ms
  
- [ ] **Smooth Speed Ramping**: Speed changes smoothly, not step-like
  - Expected: No sudden PWM jumps (ramp step ~5 PWM per cycle)
  
- [ ] **Thread Safety**: No crashes from concurrent access
  - Expected: Multiple status polls while executing → no errors
  - Expected: Stop command while in motion → clean transition

- [ ] **Long Execution**: Execute path with 20+ waypoints, 60+ seconds
  - Expected: No memory leaks
  - Expected: No slowdown over time
  - Expected: Completes successfully

---

## 🧪 Quick Test Sequence (5 mins)

1. **Launch**: `./start.sh` → Server starts, shows "System ready"
2. **Manual Check**: Press Forward/Stop → confirms manual works
3. **Mode Switch**: Dashboard → "Switch to Autonomous" → grid appears
4. **Grid Setup**: 
   - Click Start tool → [5, 5]
   - Click Goal tool → [15, 5]
   - Draw one small wall at [10, 5]
5. **Plan**: Click "Plan Path" → yellow line avoids wall
6. **Execute**: Click "Execute" → robot moves, avoids obstacle
7. **Stop**: Click "Stop" → robot stops immediately
8. **Manual**: Click "Switch to Manual" → buttons re-enable
9. **Verify**: Manual forward/stop still works

**Expected Result**: All steps succeed without errors.

---

## 📋 Detailed Test Report Template

For each test, record:
```
Test ID: [e.g., B1-Mode-Switch]
Result: [PASS / FAIL]
Observation: [What happened?]
Console Log: [Relevant output]
Issues: [Any problems?]
```

---

## 🔗 Related Files

- **Backend**: `backend/autonomous.py`, `backend/server.py`
- **Frontend**: `frontend/js/autonomous.js`, `frontend/dashboard.html`
- **Motor/Servo**: `motor.py` (pulse_servo, set_motor_speed, forward/stop)
- **Sensor Data**: `backend/data_model.py` (ultrasonic, metal_detector)
- **Pathfinding**: `backend/pathfinding/astar.py`, `backend/pathfinding/__init__.py`

---

## 📞 Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Grid doesn't appear | Not in autonomous mode | Click "Switch to Autonomous Mode" |
| Can't click grid cells | Tool not selected | Click Start/Goal/Wall before clicking grid |
| Plan shows no path | Start/goal not set or blocked | Set both points, clear obstacles |
| Execute does nothing | No path planned | Click "Plan Path" first |
| Motor spins continuously | force_stop flag stuck | Restart backend (Ctrl+C, ./start.sh) |
| Servo doesn't move | Metal detect override off | Toggle "Enable Metal→Servo Link" |
| Obstacle log empty | No replans triggered | Add walls in front, execute (needs obstacle) |
| Speed slider doesn't work | In autonomous mode | Only works in manual mode |

---

## ✅ Sign-Off

- [ ] All A-N tests reviewed and understood
- [ ] Quick Test Sequence completed successfully
- [ ] No critical issues found
- [ ] Ready for field testing

**Tester Name:** ________________  
**Date:** ________________  
**Notes:** ________________________________

---

**Phase 2 Restored:** 2026-04-25 09:35 UTC  
**Status:** READY FOR TESTING ✅

