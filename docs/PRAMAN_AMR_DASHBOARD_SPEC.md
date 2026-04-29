# PRAMAN AMR Dashboard Design and Implementation

## 1. Dashboard Layout (Final Recommended Structure)

```
┌────────────────────────────────────────────┐
│            PRAMAN AMR DASHBOARD            │
├────────────────────────────────────────────┤
│ 🔋 System Status | CPU | Temp | Voltage    │
├────────────────────────────────────────────┤
│ 🎮 Control Panel                           │
│  ⬆️                                       │
│ ⬅️ ⏹️ ➡️                                   │
│  ⬇️                                       │
│ Speed Slider | Emergency Stop              │
├────────────────────────────────────────────┤
│ 🧭 Ultrasonic Radar (CENTER FEATURE)       │
├────────────────────────────────────────────┤
│ 📡 Sensor Monitoring                       │
│ MQ2 | MQ135 | PIR | Metal                 │
├────────────────────────────────────────────┤
│ 📊 Graphs Section                          │
│ Gyro Graph | Speed Graph | Gas Graph       │
├────────────────────────────────────────────┤
│ 🚨 Alerts Section                          │
│ Motion | Metal | Gas Danger                │
└────────────────────────────────────────────┘
```

## 2. Design Principles

- **Hierarchy**: Controls at top, visualization in center, analytics at bottom.
- **Real-time visibility**: Radar and alerts remain always visible.
- **Minimal clutter**: Present only actionable information with clear status colors.
- **Hardware alignment**: Maintain existing GPIO, voltage, and wiring architecture.

## 3. Execution Architecture

### Software Flow

```
Hardware → Sensor Modules → Backend Data Model → Flask Server → Dashboard UI
                                         ↓
                                   AI + Logic Layer
```

### Current Backend Implementation

- `backend/sensors/mq.py`: unified MQ gas sensor wrapper.
- `backend/sensors/ultrasonic.py`: ultrasonic distance interface.
- `backend/sensors/pir.py`: PIR motion detection wrapper.
- `backend/sensors/metal.py`: metal hazard wrapper.
- `backend/sensors/imu_wrapper.py`: IMU data adapter.
- `backend/data_model.py`: unified dashboard payload builder.

## 4. Current Implementation Status

### Completed

- Added professional sensor module wrappers under `backend/sensors/`.
- Created a unified backend payload in `backend/data_model.py`.
- Verified the payload shape and runtime operation with a quick execution test.
- Added documentation scaffolding under `docs/PRAMAN_AMR_DASHBOARD_SPEC.md`.

### Next Development Step

- Build the backend Flask API layer in `backend/server.py`.
- Add WebSocket support for real-time updates.
- Implement the dashboard UI using the finalized layout and improved components.

## 5. Data Payload Format

The backend now emits a standardized sensor payload with the shape:

```json
{
  "gas": {
    "mq2": {"raw": 2730, "rs": 5.0, "ppm": 114, "status": "safe"},
    "mq135": {"raw": 1787, "rs": 12.92, "ppm": 49, "status": "safe"}
  },
  "ultrasonic": {
    "center": 999,
    "left": 999,
    "right": 999,
    "status": "safe"
  },
  "pir": {"value": false, "alert": false},
  "metal": {"detected": true},
  "imu": {"gyro_z": 0.18},
  "system": {"cpu": 24.9, "temp": 38.4, "voltage": 5.0}
}
```

## 6. Notes for Future Features

- Real-time streaming should be implemented with `flask-socketio`.
- The next major feature is the structured backend API with `/data`, `/control`, and WebSocket events.
- After that, a dashboard UI redesign should follow the final structure and visualization principles.
