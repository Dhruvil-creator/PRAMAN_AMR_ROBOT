# Quick Reference - Code Changes

## 🔧 Key Code Sections

### 1. Servo Position Setting (motor.py)
```python
# NEW: Pulse-and-stop method (lines 187-195)
def set_position(self, angle):
    """Set servo position and stop PWM to prevent shaking."""
    target = max(0, min(180, int(angle)))
    duty = 2.5 + (target / 18.0)
    
    self.hardware.servo_pwm.start(duty)
    time.sleep(0.25)
    self.hardware.servo_pwm.stop()
    self.angle = target
```

**What this does:**
- Converts angle to PWM duty cycle (formula from test_servo.py)
- Sends pulse to servo for 0.25 seconds
- Stops PWM to prevent vibration
- Motor inertia holds final position

---

### 2. Servo Action Sequence (motor.py)
```python
# UPDATED: pulse_servo now returns to 75° (lines 205-210)
def pulse_servo(self, angle, duration=0.5):
    """Servo action: move to angle, wait, then return to center (75°)."""
    with self.lock:
        self.set_position(angle)
        time.sleep(duration)
        self.set_position(75)  # Always return to center
```

**What this does:**
- Moves servo to specified angle
- Holds for duration (default 0.5s, can be 0.2s for quick action)
- Returns to center position (75°)
- Thread-safe with lock

---

### 3. Metal Sensor Monitoring (backend/server.py)
```python
# NEW: Metal sensor loop (lines 209-228)
def metal_sensor_loop():
    """Monitor metal sensor and trigger servo action when metal detected."""
    from backend.sensors.metal import read as read_metal_sensor
    last_metal_state = False
    
    while True:
        try:
            if metal_servo_enabled:
                metal_detected = read_metal_sensor()
                
                # Trigger servo action on metal detection (rising edge)
                if metal_detected and not last_metal_state:
                    print("🔔 Metal detected! Triggering servo action...")
                    threading.Thread(target=lambda: motor.pulse_servo(120, duration=0.2), daemon=True).start()
                
                last_metal_state = metal_detected
        except Exception as e:
            print(f"Metal sensor loop error: {e}")
        
        time.sleep(0.1)
```

**What this does:**
- Runs continuously in background
- Checks if metal automation is enabled
- Detects rising edge (0→1 transition only)
- Triggers servo to 120° for 0.2s when metal detected
- De-bounces at 100ms polling interval

---

### 4. Metal Automation Toggle (backend/server.py)
```python
# NEW: Toggle endpoint (lines 301-305)
elif action == 'metal_detect_toggle':
    metal_servo_enabled = not metal_servo_enabled
    status = 'enabled' if metal_servo_enabled else 'disabled'
    print(f'Metal detector -> servo connection {status}')
    return {'metal_servo': metal_servo_enabled}, 200
```

**What this does:**
- Flip metal automation on/off
- Return new state to frontend
- Allow simultaneous manual + autonomous control

---

### 5. New Servo Action Endpoint (backend/server.py)
```python
# NEW: Action endpoint (lines 298-300)
elif action == 'action':
    print('Servo action command received (120° swing)')
    threading.Thread(target=lambda: motor.pulse_servo(120, duration=0.2), daemon=True).start()
```

**What this does:**
- Trigger servo action manually (same as metal detection would)
- Move to 120°, hold 0.2s, return to 75°

---

## 📱 Frontend Button Integration

### Basic Setup
```html
<!-- Enable Metal Detection Button -->
<button onclick="toggleMetal()">Toggle Metal Detection</button>

<!-- Servo Action Button -->
<button onclick="servoAction()">Trigger Servo Action</button>

<script>
async function toggleMetal() {
  const res = await fetch('/servo', {
    method: 'POST',
    body: new URLSearchParams({ action: 'metal_detect_toggle' })
  });
  const data = await res.json();
  console.log('Metal detection:', data.metal_servo ? 'ON' : 'OFF');
}

function servoAction() {
  fetch('/servo', {
    method: 'POST',
    body: new URLSearchParams({ action: 'action' })
  });
}
</script>
```

---

## 🧪 Quick Test Commands

### Test Manual Servo Action
```bash
curl -X POST http://localhost:5000/servo -d "action=action"
```

### Test Toggle Metal Detection
```bash
curl -X POST http://localhost:5000/servo -d "action=metal_detect_toggle"
```

### Check Status
```bash
curl http://localhost:5000/status
```

### Manual Servo Movements
```bash
curl -X POST http://localhost:5000/servo -d "action=restore"    # 75° center
curl -X POST http://localhost:5000/servo -d "action=open"       # 180° open
curl -X POST http://localhost:5000/servo -d "action=close"      # 0° close
```

---

## ⚙️ Configuration Points

### Change Servo Center Angle
File: `motor.py` line 184 or line 100
```python
self.angle = 75  # Change to any 0-180
```

### Change Metal Detection Action Angle
File: `backend/server.py` line 222
```python
motor.pulse_servo(120, duration=0.2)  # Change 120 to desired angle
```

### Change Metal Detection Hold Duration
File: `backend/server.py` line 222
```python
motor.pulse_servo(120, duration=0.2)  # Change 0.2 to desired seconds
```

### Change Metal Detection Poll Rate
File: `backend/server.py` line 228
```python
time.sleep(0.1)  # Change to desired seconds (lower = faster response)
```

---

## 🔍 Debugging

### Check if Metal Sensor Loop is Running
Look for console output when metal is detected:
```
🔔 Metal detected! Triggering servo action...
```

### Check Metal Automation Status
```bash
curl http://localhost:5000/status | grep metal_servo_enabled
```

### Monitor Backend Logs
```bash
tail -f backend_logs.txt | grep -i "metal\|servo"
```

---

## ✅ Verification Checklist

- [ ] Both `motor.py` and `backend/server.py` compile without errors
- [ ] Servo responds to `/servo?action=action` (120° swing)
- [ ] Servo responds to `/servo?action=restore` (return to 75°)
- [ ] `/servo?action=metal_detect_toggle` toggles the state
- [ ] `/status` includes `metal_servo_enabled` field
- [ ] Background metal sensor loop starts at system init
- [ ] No shaking observed when servo holds position
- [ ] Metal detection triggers servo action when enabled

