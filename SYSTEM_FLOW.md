# System Flow Diagrams

## 🎛️ Servo Control Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SERVO SYSTEM                                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND (Dashboard)                                                │
├─────────────────────────────────────────────────────────────────────┤
│  • Manual Buttons (Open/Close/Center/Action)                         │
│  • Metal Detection Toggle Button                                     │
│  • Status Indicator                                                  │
└──────────────────────────────┬──────────────────────────────────────┘
                              │
                   HTTP POST /servo
                              │
┌─────────────────────────────▼──────────────────────────────────────┐
│  BACKEND (server.py)                                                 │
├─────────────────────────────────────────────────────────────────────┤
│  Routes:                                                             │
│    action='action'         → pulse_servo(120, 0.2)                  │
│    action='open'           → pulse_servo(180, 0.5)                  │
│    action='close'          → pulse_servo(0, 0.5)                    │
│    action='restore'        → pulse_servo(75, 0.5)                   │
│    action='metal_detect_toggle' → toggle metal_servo_enabled        │
└─────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
┌──────────────────────────────┐         ┌──────────────────────────────┐
│  motor.pulse_servo()         │         │  metal_sensor_loop()         │
│  (motor.py)                  │         │  (server.py)                 │
├──────────────────────────────┤         ├──────────────────────────────┤
│  1. set_position(angle)      │         │  ✓ Continuous monitoring     │
│     - PWM.start(duty)        │         │  ✓ Rising edge detect        │
│     - sleep(0.25s)           │         │  ✓ Triggers servo action     │
│     - PWM.stop()             │         │  ✓ Thread-safe               │
│  2. sleep(duration)          │         │                              │
│  3. set_position(75)         │         │  if metal_servo_enabled:     │
│     → Return to center       │         │    if metal_detected:        │
│                              │         │      pulse_servo(120, 0.2)   │
└──────────────────────────────┘         └──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│  Servo Motor (RPi GPIO 19)   │
├──────────────────────────────┤
│  Current position: 75°       │
│  Target: Varies by command   │
│  Status: Stable (no shaking) │
└──────────────────────────────┘
```

---

## 🔄 Servo Command Execution Flow

### Manual Command (Button Click)
```
User clicks "Action" button
        ↓
Frontend: fetch('/servo', {action: 'action'})
        ↓
Backend: servo_control() route
        ↓
Launch thread: motor.pulse_servo(120, 0.2)
        ↓
set_position(120):
  • PWM.start(duty=9.17%)
  • sleep(0.25s)          ← Pulse duration
  • PWM.stop()            ← STOP = No shaking!
        ↓
sleep(0.2s)              ← Hold at 120°
        ↓
set_position(75):
  • PWM.start(duty=6.67%)
  • sleep(0.25s)
  • PWM.stop()
        ↓
Servo at center (75°)
```

---

## 🔍 Metal Detection Flow

### Continuous Monitoring
```
metal_sensor_loop() [Background Thread]
        ↓
every 100ms:
  ┌─────────────────────────────┐
  │ if metal_servo_enabled:     │
  │   metal_state = read()      │
  │                             │
  │   if metal_state and        │
  │      not last_state:        │  ← Rising edge
  │     ┌─────────────────────┐ │
  │     │ TRIGGER ACTION:     │ │
  │     │ pulse_servo(120,    │ │
  │     │   duration=0.2)     │ │
  │     └─────────────────────┘ │
  │   last_state = metal_state  │
  └─────────────────────────────┘
```

### De-bounce Pattern
```
Metal Sensor Reading Timeline:
───────────────────────────────────────────────────────────

Time: 0ms    50ms   100ms  150ms  200ms  250ms  300ms
State: 0      1      1      1      0      0      0

Rising edge at 50ms → TRIGGER (only once)
Continuous HIGH until 200ms → NO re-trigger
Falling edge at 200ms → Awaiting next rising edge

Result: Single servo action per metal detection ✓
```

---

## 🎮 User Interaction Scenarios

### Scenario 1: Manual Control Only
```
User Flow:
  1. Dashboard loads
  2. Metal toggle is OFF
  3. User clicks "Action" button
  4. Servo moves to 120°, returns to 75°
  5. Metal sensor data is read but ignored
  
State:
  metal_servo_enabled = False
  Only manual buttons work
```

### Scenario 2: Autonomous Detection Only
```
User Flow:
  1. Dashboard loads
  2. User clicks toggle to enable metal detection
  3. metal_servo_enabled = True
  4. User touches metal object near sensor
  5. Servo auto-triggers 120° action
  6. Servo returns to 75°
  
State:
  metal_servo_enabled = True
  Servo responds automatically
```

### Scenario 3: Mixed Manual + Autonomous
```
User Flow:
  1. Dashboard loads
  2. Metal detection is enabled (metal_servo_enabled = True)
  3. User clicks "Action" button → Servo moves
  4. Simultaneously, metal detected → Servo action triggered
  5. Both commands queued (thread-safe with lock)
  
State:
  metal_servo_enabled = True
  Manual buttons override/queue with auto actions
```

---

## 📊 State Machine

```
                    ┌─────────────────┐
                    │  SYSTEM START   │
                    └────────┬────────┘
                             │
              motor.set_servo_angle(75)
                             │
                    ┌────────▼────────┐
                    │  AT CENTER 75°  │
                    │  (Stable)       │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼─────┐   ┌────────▼────────┐   ┌────▼──────┐
    │   Manual   │   │ Metal Detected  │   │  Button   │
    │   Button   │   │  (if enabled)   │   │  Click    │
    │  Click     │   └────────┬────────┘   └────┬──────┘
    └─────┬─────┘             │                  │
          │                   │      ┌───────────┘
          │                   │      │
          └───────┬───────────┴──────┘
                  │
          ┌───────▼──────────┐
          │ Set Position:    │
          │ - Start PWM      │
          │ - Wait 0.25s     │
          │ - Stop PWM       │
          │ (No Shaking!)    │
          └───────┬──────────┘
                  │
          ┌───────▼──────────┐
          │  At Target Angle │
          │  (Current + new) │
          └───────┬──────────┘
                  │
          (if pulse_servo)
             │
          ┌──▼──────────────┐
          │  Wait Duration  │
          │  (0.2 to 0.5s)  │
          └──┬──────────────┘
             │
          ┌──▼──────────────┐
          │  Return to 75°  │
          │  (Center)       │
          └──┬──────────────┘
             │
          ┌──▼──────────────┐
          │ AT CENTER 75°   │
          │ (Stable)        │
          │ (Loop back)     │
          └────────────────┘
```

---

## 🧵 Thread Architecture

```
┌────────────────────────────────────────────────────────┐
│  Main Flask Thread                                      │
├────────────────────────────────────────────────────────┤
│ • HTTP request handling                                 │
│ • Route dispatch (/servo, /status, etc.)               │
│ • Response generation                                   │
└──────┬─────────────────────────────────────────────────┘
       │
       ├─► Spawns daemon threads for blocking operations
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ Daemon Threads (Motor Operations)                    │
├──────────────────────────────────────────────────────┤
│ • speed_loop()      │ Updates motor speed             │
│ • command_loop()    │ Processes movement commands     │
│ • sensor_loop()     │ Broadcasts sensor data (SocketIO)│
│ • metal_sensor_loop()│ ◄─ NEW: Metal detection       │
│ • pulse_servo()     │ (launched per manual action)    │
└──────────────────────────────────────────────────────┘

Thread Safety:
  • ServoDrive uses: threading.Lock()
  • motor.pulse_servo() queues safely
  • metal_sensor_loop() reads safely
  • No data races
```

---

## 🔌 Hardware Signal Flow

```
┌──────────────────────┐
│  Raspberry Pi GPIO   │
├──────────────────────┤
│ Pin 19: Servo PWM    │       ┌──────────────┐
│ Pin 6:  Metal Detect │──────▶│  Metal Sensor│
│ Pins 17-18: Motor    │       │   (Input)    │
│ Pin 12-13: Motor PWM │       └──────────────┘
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Servo Motor (Pin 19)│
│  • Signal: PWM 50Hz  │
│  • Duty: 2.5%-12.5%  │
│  • Angle: 0-180°     │
│  • Position: Stable  │
└──────────────────────┘

Metal Sensor Input (Pin 6):
  • Active HIGH: Metal detected
  • Active LOW: No metal
  • De-bounce: 200ms (in metal.py)
  • Poll rate: 100ms (in metal_sensor_loop())
```

