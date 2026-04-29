# Phase 3 Debug Checklist - Autonomous Execution Issues

**Problem Statement**: Robot stays still during autonomous execution; motors make sound (trying to reposition) but don't move. Speed is the limiting factor.

**Date**: 2026-04-25

---

## 🔴 Critical Issues Found

### Issue 1: Motor Speed Too Low (min_speed = 35)
**Severity**: 🔴 **CRITICAL** - Robot barely moves or doesn't move at all  
**Location**: `backend/autonomous.py`, line 76  
**Root Cause**: `min_autonomous_speed = 35` may be insufficient for actual robot motor startup  
**Evidence**: Motor makes sound (PWM signal active) but robot doesn't move  
**Fix**: Increase minimum speed to 50-60 to ensure motor can overcome friction  

---

### Issue 2: Speed Calculation Always Starts at 0
**Severity**: 🔴 **CRITICAL** - No acceleration from stop  
**Location**: `backend/autonomous.py`, lines 151, 368-381  
**Root Cause**: 
- `self.current_autonomous_speed = 0` at line 151 (on execution start)
- Speed ramp steps up from 0 very slowly (3 PWM units per 50ms cycle = ~0.06s per PWM)
- At 50 cycles/sec, reaching speed 50 takes ~40 cycles = 2 seconds
**Fix**: Start with `min_autonomous_speed` instead of 0, or use larger ramp step  

---

### Issue 3: Speed Ramp Step Too Small
**Severity**: 🟠 **HIGH** - Very slow acceleration  
**Location**: `backend/autonomous.py`, line 78  
**Current Value**: `self.speed_ramp_step = 3` (3 PWM units per 50ms = 60 PWM/sec)  
**Problem**: Takes 0.83 seconds to ramp from 0 to 50 PWM  
**Fix**: Increase to 10-15 for snappier response  

---

### Issue 4: Target Speed Calculation Has Edge Cases
**Severity**: 🟠 **HIGH** - Speed stuck at minimum in early execution  
**Location**: `backend/autonomous.py`, lines 566-587  
**Root Cause**: 
- Obstacle distances default to 999 (no obstacle)
- But `_nearest_obstacle_distance()` returns `None` if all distances are 999
- When `None`, returns `max_speed` - correct
- BUT if ANY sensor reads <999, even briefly, speed may drop unexpectedly
**Fix**: More robust nearest-obstacle logic with hysteresis  

---

### Issue 5: Motor Commands Not Always Executed
**Severity**: 🟠 **HIGH** - Motor may not respond to speed changes  
**Location**: `backend/autonomous.py`, lines 383-384  
```python
motor.set_motor_speed(self.current_autonomous_speed, self.current_autonomous_speed)
motor.forward()
```
**Problem**: 
- `set_motor_speed()` called every 50ms, but speed starts at 0
- If speed is 0, `set_motor_speed(0, 0)` might be skipped by motor logic
- Need to ensure motor **actually receives** speed commands
**Fix**: Add explicit check and logging; ensure forward() is called after speed is set  

---

### Issue 6: Waypoint Tolerance Too Tight
**Severity**: 🟡 **MEDIUM** - Robot may never reach waypoint  
**Location**: `backend/autonomous.py`, line 75  
**Current Value**: `self.waypoint_tolerance = 0.25` grid cells (2.5cm in real distance)  
**Problem**: With slow movement, robot overshoots or undershoots  
**Fix**: Increase to 0.5-1.0 grid cells (5-10cm)  

---

### Issue 7: Position Update Logic Problematic
**Severity**: 🟡 **MEDIUM** - Robot position may not sync with actual movement  
**Location**: `backend/autonomous.py`, lines 387-392  
```python
step = 0.02 + (self.current_autonomous_speed / 100.0) * 0.04  # 0.02 to 0.06 cells per cycle
move_x = (dx / distance) * step
move_y = (dy / distance) * step
self.robot_position[0] += move_x
self.robot_position[1] += move_y
```
**Problem**: 
- Step size (0.02-0.06 cells) is very small compared to waypoint tolerance (0.25 cells)
- If speed is 35 (min), step = 0.02 + 0.35*0.04 = 0.034 cells
- Takes ~7-10 cycles to move 0.25 cells
- At 20Hz, that's 0.35-0.5 seconds per waypoint with only 2 waypoints = 1 second for small path
- Too slow for real robot response
**Fix**: Adjust step calculation or use odometry from motor feedback  

---

### Issue 8: Heading Alignment May Stall Execution
**Severity**: 🟡 **MEDIUM** - Robot might rotate forever  
**Location**: `backend/autonomous.py`, lines 357-365  
**Problem**: 
- If `_needs_heading_alignment()` returns true, robot tries to rotate
- If heading never converges, timeout is 1.5 seconds
- After timeout, still forces forward motion but alignment flag persists
**Fix**: Better heading convergence logic or skip alignment if sensor not available  

---

### Issue 9: Manual Control Interference
**Severity**: 🟡 **MEDIUM** - Manual commands might override autonomous  
**Location**: `backend/server.py` (manual motor endpoints)  
**Problem**: Frontend might send manual commands while autonomous executing  
**Fix**: Prevent manual motor commands when in autonomous mode  

---

## 📋 Feature Implementation Status

| Feature | Implemented | Working | Issue |
|---------|-------------|---------|-------|
| Mode switch | ✅ Yes | ✅ Yes | None |
| A* path planning | ✅ Yes | ✅ Yes | None |
| Autonomous execute | ✅ Yes | ❌ No | Speed too low, stuck at 0 |
| Robot position tracking | ✅ Yes | ⚠️ Partial | Updates too slowly |
| Heading alignment | ✅ Yes | ❌ No | May stall execution |
| Adaptive speed control | ✅ Yes | ⚠️ Partial | Works but slow to converge |
| Speed sliders | ✅ Yes | ⚠️ Partial | Work but min speed too low |
| Obstacle detection | ✅ Yes | ✅ Yes | None |
| Replan on obstacle | ✅ Yes | ⚠️ Partial | Depends on speed fix |
| Servo on detection | ✅ Yes | ✅ Yes | None |
| Emergency stop | ✅ Yes | ✅ Yes | None |

---

## 🔧 Priority Fix Order

### Priority 1: FIX MOTOR SPEED (Critical - blocks all motion)
1. **Increase `min_autonomous_speed` from 35 to 55**
   - File: `backend/autonomous.py`, line 76
   - Reason: Current min (35) insufficient to overcome motor friction
   
2. **Start with `min_speed` instead of 0**
   - File: `backend/autonomous.py`, line 151
   - Change: `self.current_autonomous_speed = 0` → `self.current_autonomous_speed = self.min_autonomous_speed`
   - Reason: No need to ramp from zero; starts moving immediately

3. **Increase speed ramp step from 3 to 12**
   - File: `backend/autonomous.py`, line 78
   - Reason: Snappier response, 0.4 seconds to full speed instead of 1.7 seconds

### Priority 2: VERIFY MOTOR COMMANDS (High - ensure commands reach hardware)
1. Add logging to motor commands
2. Verify `motor.forward()` called after `motor.set_motor_speed()`
3. Test manual mode motor commands work

### Priority 3: FIX POSITION UPDATE (High - affects waypoint detection)
1. Increase step size or use feedback
2. Align position tracking with actual motor response

### Priority 4: IMPROVE HEADING ALIGNMENT (Medium - may cause stalls)
1. Add convergence check
2. Reduce timeout or skip if IMU not available

---

## 📝 Test Plan (After Fixes)

1. **Basic Move Test**
   - Plan 2-waypoint path
   - Execute
   - Verify: Robot moves forward smoothly

2. **Speed Control Test**
   - Move obstacle close
   - Verify: Robot slows down
   - Move obstacle away
   - Verify: Robot speeds up

3. **Path Following Test**
   - Plan 5-waypoint path
   - Execute
   - Verify: Robot follows all waypoints and stops

4. **Obstacle Replan Test**
   - Plan path
   - Execute
   - Block path mid-execution
   - Verify: Robot stops, replans, resumes

---

## 📊 Expected Behavior After Fixes

- **Autonomous Execute**: Robot starts moving within 0.5 seconds (not 2+ seconds)
- **Speed Range**: 55-70 PWM (instead of 35-70, which is too narrow)
- **Waypoint Reach**: ~1 second per 1-meter path (instead of 3+ seconds)
- **Obstacle Response**: <1 second to detect and start replan

---

**Next Steps**: Implement Priority 1 fixes and test motor response.
