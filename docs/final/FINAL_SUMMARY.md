# FINAL SUMMARY

This folder collects all project documentation files and a summary of working and non-working features.

## Working features
- Safety guard (obstacle detection, hard stop)
- Motor safety interlock
- Ultrasonic spike handling and basic validation
- Conservative localization mode
- Dashboard suppression of optimistic grid updates

## Non-working / Known Issues
- Left ultrasonic sensor reports repeated 0.0 readings (hardware or GPIO timing issue)
- Occasional collisions reported in field tests; tune STOP_DISTANCE and speed
- Intermittent metal sensor triggers for servo
- Grid vs physical pose mismatch requires field validation

## How to use docs/collected
Each file in docs/collected is a copy of the original markdown with metadata header showing creation and last commit dates.

## Next steps
- Run field tests to validate left ultrasonic sensor wiring
- Tune safety distances and max speed
- Collect logs for sensor->stop latency

