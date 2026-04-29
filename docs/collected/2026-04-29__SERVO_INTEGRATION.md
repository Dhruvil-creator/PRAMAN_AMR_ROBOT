# Source: SERVO_INTEGRATION.md
# Created: 2026-04-29T16:24:20+05:30
# Last commit: 2026-04-29T16:24:20+05:30

# Servo & Metal Sensor Frontend Integration Guide

## Overview
The backend now provides servo control with metal sensor automation. Use these endpoints to integrate with your frontend dashboard.

---

## Servo Control Endpoints

### Manual Servo Actions

#### 1. Servo Action (120° Swing)
Moves servo to 120° for 0.2 seconds, then returns to center (75°)
```javascript
fetch('/servo', {
  method: 'POST',
  body: new URLSearchParams({ action: 'action' })
})
```

#### 2. Open Servo (180°)
Moves servo to fully open position
```javascript
fetch('/servo', {
  method: 'POST',
  body: new URLSearchParams({ action: 'open' })
})
```

#### 3. Close Servo (0°)
Moves servo to fully closed position
```javascript
fetch('/servo', {
  method: 'POST',
  body: new URLSearchParams({ action: 'close' })
})
```

#### 4. Restore to Center (75°)
Returns servo to center position
```javascript
fetch('/servo', {
  method: 'POST',
  body: new URLSearchParams({ action: 'restore' })
})
```

---

## Metal Sensor Automation

### Toggle Metal Detector → Servo Connection

Enable/disable automatic servo action when metal is detected.

```javascript
async function toggleMetalDetection() {
  const response = await fetch('/servo', {
    method: 'POST',
    body: new URLSearchParams({ action: 'metal_detect_toggle' })
  });
  
  const data = await response.json();
  const isEnabled = data.metal_servo;
  console.log('Metal detection:', isEnabled ? '🔴 ON' : '🟢 OFF');
  
  // Update UI button state
  updateButtonState(isEnabled);
}
```

### Check Metal Automation Status

```javascript
async function checkStatus() {
  const response = await fetch('/status');
  const data = await response.json();
  
  console.log('Metal-Servo Automation:', data.metal_servo_enabled);
  // Returns: true (enabled) or false (disabled)
}
```

---

## Frontend Button Layout Example

```html
<!-- Servo Control Panel -->
<div class="servo-panel">
  <h3>Servo Control</h3>
  
  <!-- Manual Controls -->
  <button onclick="servoAction('action')">🔄 Action (120°)</button>
  <button onclick="servoAction('open')">📂 Open (180°)</button>
  <button onclick="servoAction('close')">📁 Close (0°)</button>
  <button onclick="servoAction('restore')">🎯 Center (75°)</button>
  
  <!-- Metal Sensor Toggle -->
  <div style="margin-top: 20px; border-top: 1px solid #ccc; padding-top: 15px;">
    <label>
      <input type="checkbox" id="metalToggle" onchange="toggleMetalDetection()">
      <span id="metalStatus">🔴 Metal Detection OFF</span>
    </label>
    <small>When enabled, servo automatically responds to metal detection</small>
  </div>
</div>

<script>
function servoAction(action) {
  fetch('/servo', {
    method: 'POST',
    body: new URLSearchParams({ action })
  })
  .then(() => console.log(`Servo: ${action}`))
  .catch(err => console.error('Error:', err));
}

async function toggleMetalDetection() {
  try {
    const response = await fetch('/servo', {
      method: 'POST',
      body: new URLSearchParams({ action: 'metal_detect_toggle' })
    });
    const data = await response.json();
    const statusEl = document.getElementById('metalStatus');
    statusEl.textContent = data.metal_servo ? '🟢 Metal Detection ON' : '🔴 Metal Detection OFF';
  } catch (err) {
    console.error('Error:', err);
  }
}

// Load initial status
async function loadStatus() {
  try {
    const response = await fetch('/status');
    const data = await response.json();
    document.getElementById('metalToggle').checked = data.metal_servo_enabled;
    const statusEl = document.getElementById('metalStatus');
    statusEl.textContent = data.metal_servo_enabled ? '🟢 Metal Detection ON' : '🔴 Metal Detection OFF';
  } catch (err) {
    console.error('Error loading status:', err);
  }
}

// Initialize on page load
window.addEventListener('load', loadStatus);
</script>
```

---

## Servo Angles Reference

| Position | Angle | Use Case |
|----------|-------|----------|
| Close | 0° | Gripper closed, gate closed |
| Sweep/Action | 120° | Detect/grab, temporary movement |
| Center | 75° | Default, neutral position |
| Open | 180° | Gripper open, gate open |

---

## Behavior Summary

### Without Metal Detection Toggle
- Servo responds only to manual buttons
- Metal sensor is ignored

### With Metal Detection Toggle Enabled
- Manual buttons still work normally
- **Additionally:** When metal detected → servo moves to 120° for 0.2s, returns to 75°
- Rising edge detection (triggers once per detection)
- Useful for autonomous gripper/detection workflows

---

## Performance Notes

- Servo pulse: 0.25 seconds (no shaking)
- Metal detection poll: 100ms
- Metal sensor de-bounce: 200ms
- Safe for continuous operation
