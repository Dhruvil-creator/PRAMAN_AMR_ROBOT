# Backend Servo & Metal Sensor Integration - Changes Summary

## Issues Fixed

### 1. Servo Instability (Shaking)
**Problem:** Servo motor was continuously shaking even without button input due to persistent PWM signal.

**Solution:** 
- Changed from continuous PWM to pulse-and-stop approach
- PWM starts only for 0.25s to set position, then stops immediately
- Prevents constant signal that causes shaking

**Implementation:**
- New `set_position()` method sends pulse then stops PWM
- Applied to all servo movements (manual and autonomous)

### 2. Servo Angles Aligned with Test Code
**Changes:**
- Center position: **75°** (was 90°)
- Action position: **120°** (swing test)
- Default positions match test_servo.py specifications

### 3. Metal Sensor Detection
**Feature:** Autonomous servo action when metal is detected

**How it works:**
- Continuous background monitoring of metal sensor
- When metal detected → servo moves to 120° for 0.2s then returns to 75°
- Uses rising edge detection to trigger only once per detection

### 4. Manual Mode Toggle for Metal-Servo Connection
**Feature:** User button to enable/disable metal detector → servo automation

**New Endpoint:** `POST /servo`
- Action: `metal_detect_toggle` - Enable/disable metal sensor automation
- Response: `{"metal_servo": true/false}`
- Allows users to keep manual servo control independent of metal detection

## Code Changes

### motor.py
```python
class ServoDrive:
    def set_position(angle):
        # Set servo position and immediately stop PWM to prevent shaking
        # Formula: duty = 2.5 + (angle / 18.0)
        
    def pulse_servo(angle, duration):
        # Move to angle, wait duration, return to 75° center
```

### backend/server.py
- Added `metal_servo_enabled` global flag
- Added `metal_sensor_loop()` - background thread monitoring metal sensor
- Updated `/servo` endpoint with new actions:
  - `action` → servo action (120° swing)
  - `metal_detect_toggle` → enable/disable automation
- Updated `/status` endpoint to include metal_servo status
- Initialize servo to 75° at startup

## API Usage Examples

### Enable Metal-Servo Automation
```bash
curl -X POST http://localhost:5000/servo \
  -d "action=metal_detect_toggle"
```

### Trigger Servo Action (120° swing)
```bash
curl -X POST http://localhost:5000/servo \
  -d "action=action"
```

### Get System Status (includes metal_servo state)
```bash
curl http://localhost:5000/status
```

## Testing
All logic applied from test_servo.py and test_metal_sensor.py to ensure compatibility.
