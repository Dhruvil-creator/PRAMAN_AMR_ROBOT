# Source: docs/OPERATOR_GUIDE.md
# Created: 2026-04-29T16:24:20+05:30
# Last commit: 2026-04-29T16:24:20+05:30

PRAMAN AMR Operator Guide (short)
=================================

Safety first:
- Ensure robot power is off when wiring sensors.
- Use a stable 5V supply for servo and common ground with Raspberry Pi.
- Keep hands clear of wheels and servo while testing.

Pre-flight checklist:
1. Power servo and motors using stable supply.
2. Verify sensor wiring (ultrasonic trig/echo pins, metal sensor pins).
3. Start backend on Pi: sudo ./start.sh
4. Check GET /sensor-data returns expected fields.

Hardware tests:
- Ultrasonic: run python3 backend/sensors/ultrasonic.py and present an object at 10/20/40 cm to validate readings.
- Metal sensor: toggle /servo?action=metal_detect_toggle and present metal; servo should pulse only on detection.
- Motor watchdog: ensure robot stops if backend crashes (watchdog is active by default).

If issues persist, collect server.log and paste to the developer for analysis.
