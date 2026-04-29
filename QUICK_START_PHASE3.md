# Phase 3 Quick Start Guide - DWA Motion Control

## What's New in Phase 3

**Dynamic Window Approach (DWA)** now controls smooth robot motion:
- Generates optimal velocity commands in real-time
- Predicts collisions 0.5s ahead
- Respects acceleration limits (no jerky movements)
- Integrates seamlessly with A* pathfinding from Phase 1
- Works with real-time obstacle detection from Phase 2

---

## Key Files

### New Code
```
backend/pathfinding/dwa.py (460 lines)
  - DynamicWindowApproach: velocity planning algorithm
  - SimpleOdometry: position tracking
  - VelocityController: motor command generation
```

### Modified Code
```
backend/autonomous.py
  - Line 9: Added DWA imports
  - Line 51: DWA initialization in __init__
  - Lines 259-287: DWA-based motion control
  - Lines 291-309: Odometry-based waypoint detection
```

---

## How It Works

```
1. Get Next Waypoint from A* Path
   ↓
2. Convert Grid → Real-World Coordinates
   ↓
3. Get Obstacles from Sensor Grid
   ↓
4. DWA Calculates Best Velocity:
   - Sample velocities within acceleration limits
   - Predict trajectory for each
   - Score based on: heading, distance, velocity
   - Select best one
   ↓
5. Convert Velocity → Motor Commands
   ↓
6. Send to Motors + Update Odometry
   ↓
7. Check if Waypoint Reached (15cm tolerance)
   ↓
8. Repeat 100ms
```

---

## Configuration

Default safe parameters (in `backend/pathfinding/dwa.py`):

```python
MAX_LINEAR_VELOCITY = 0.5 m/s      # Safe for mine detection
MAX_ANGULAR_VELOCITY = 1.0 rad/s   # ~57° per second
MAX_LINEAR_ACCELERATION = 0.2 m/s² # Smooth, not jerky
OBSTACLE_THRESHOLD = 0.3 m         # 30cm safety margin
GOAL_THRESHOLD = 0.1 m             # 10cm goal tolerance
```

---

## Testing

### Run Integration Test
```python
from backend.server import app, initialize_system

initialize_system()

with app.test_client() as client:
    # Plan path
    client.post('/autonomous/grid/clear')
    client.post('/autonomous/grid/set', json={'type': 'start', 'x': 5, 'y': 7})
    client.post('/autonomous/grid/set', json={'type': 'goal', 'x': 15, 'y': 7})
    
    resp = client.post('/autonomous/plan')
    print(f"Plan: {resp.get_json()['status']}")
    
    # Execute with DWA motion control
    resp = client.post('/autonomous/execute')
    print(f"Execute: {resp.get_json()['status']}")
    
    # Check status
    resp = client.get('/autonomous/status')
    print(f"Status: {resp.get_json()['status']}")
    
    # Stop
    resp = client.post('/autonomous/stop')
    print(f"Stop: {resp.get_json()['status']}")
```

---

## Autonomous Mode Usage

### Via Web UI
1. Click **"AUTONOMY"** button (top of dashboard)
2. Click grid cells to set **Start** and **Goal**
3. Click **"Plan Path"** button
4. Click **"Execute"** button
5. Watch DWA smooth motion in real-time
6. Click any **manual control** to override

### Via API
```bash
# Plan path
curl -X POST http://localhost:5000/autonomous/plan

# Execute with DWA motion control
curl -X POST http://localhost:5000/autonomous/execute

# Monitor real-time status
curl http://localhost:5000/autonomous/status

# Stop anytime
curl -X POST http://localhost:5000/autonomous/stop
```

---

## Performance

| Metric | Value |
|--------|-------|
| Computation Time | <5ms |
| Update Cycle | 100ms (10Hz) |
| Max Velocity | 0.5 m/s |
| Safety Margin | 30cm |
| Waypoint Tolerance | 15cm |

---

## Documentation

- **PHASE3_DWA_IMPLEMENTATION.md** - Complete technical guide
- **IMPLEMENTATION_COMPLETE.md** - All phases overview
- **DEVELOPER_REFERENCE.md** - API reference

---

**Phase 3: COMPLETE ✅** | **Status: Ready for Phase 4** | **Tests: 14/14 PASS**
