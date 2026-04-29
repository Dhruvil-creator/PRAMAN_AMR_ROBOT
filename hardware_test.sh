#!/bin/bash
set -euo pipefail

# Hardware test automation script for AMR
# - Starts server (./start.sh)
# - Switches to autonomous, plans and executes a short path
# - Prompts operator to present: (1) non-metal obstacle (~15-20cm) -> expect immediate STOP (no servo)
#   and (2) metal object -> expect STOP + ~1-2s pause + servo drop + hazard mark
# - Collects server.log and /autonomous/status snapshots into logs/

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/hardware_test_${TIMESTAMP}.log"

echo "Hardware test started at ${TIMESTAMP}" | tee -a "$LOG_FILE"
read -p "CONFIRM: robot powered off/clear area? Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted by operator" | tee -a "$LOG_FILE"
  exit 1
fi

# Start server (if not already running)
if lsof -i :5000 > /dev/null 2>&1; then
  echo "Server already listening on :5000" | tee -a "$LOG_FILE"
else
  echo "Starting server via ./start.sh (background)..." | tee -a "$LOG_FILE"
  bash ./start.sh 2>&1 | tee -a "$LOG_FILE" &
  sleep 1
fi

# Wait for server readiness
echo "Waiting for backend to respond on /status..." | tee -a "$LOG_FILE"
for i in $(seq 1 60); do
  status=$(curl -s http://127.0.0.1:5000/status || true)
  if echo "$status" | grep -q '"mode"'; then
    echo "Backend ready: $status" | tee -a "$LOG_FILE"
    break
  fi
  sleep 1
done

# Ensure servo-on-metal enabled in autonomous manager
echo "Enabling servo-on-metal in autonomous manager" | tee -a "$LOG_FILE"
curl -s -H "Content-Type: application/json" -X POST -d '{"enabled":true}' http://127.0.0.1:5000/autonomous/servo-on-detection | tee -a "$LOG_FILE"

# Switch to autonomous mode
echo "Switching to autonomous mode" | tee -a "$LOG_FILE"
curl -s -H "Content-Type: application/json" -X POST -d '{"mode":"autonomous"}' http://127.0.0.1:5000/mode/switch | tee -a "$LOG_FILE"

# Planner coordinates (adjust if needed)
START_X=2; START_Y=7
GOAL_X=15; GOAL_Y=7

echo "Setting start ($START_X,$START_Y) and goal ($GOAL_X,$GOAL_Y)" | tee -a "$LOG_FILE"
curl -s -H "Content-Type: application/json" -X POST -d "{\"type\":\"start\",\"x\":$START_X,\"y\":$START_Y}" http://127.0.0.1:5000/autonomous/grid/set | tee -a "$LOG_FILE"
curl -s -H "Content-Type: application/json" -X POST -d "{\"type\":\"goal\",\"x\":$GOAL_X,\"y\":$GOAL_Y}" http://127.0.0.1:5000/autonomous/grid/set | tee -a "$LOG_FILE"

# Plan path
echo "Requesting path planning..." | tee -a "$LOG_FILE"
curl -s -X POST http://127.0.0.1:5000/autonomous/plan | tee -a "$LOG_FILE"

# Execute path
echo "Starting autonomous execution..." | tee -a "$LOG_FILE"
curl -s -X POST http://127.0.0.1:5000/autonomous/execute | tee -a "$LOG_FILE"

# Wait a short time for robot to start moving
sleep 2

# OPERATOR: non-metal obstacle test
read -p "PLACE a non-metal obstacle at ~15-20cm in front of robot, then press ENTER to continue (expect immediate STOP, NO servo)." dummy
sleep 1

echo "Status after non-metal obstacle presentation:" | tee -a "$LOG_FILE"
curl -s http://127.0.0.1:5000/autonomous/status | tee -a "$LOG_FILE"

echo "Recent server.log excerpt:" | tee -a "$LOG_FILE"
tail -n 200 server.log | tee -a "$LOG_FILE"

# OPERATOR: metal detection test
read -p "NOW PRESENT a METAL object to the sensor (same location). Press ENTER when ready (expect STOP -> ~1-2s pause -> servo drop -> hazard marked)." dummy
sleep 3

echo "Status after metal presentation:" | tee -a "$LOG_FILE"
curl -s http://127.0.0.1:5000/autonomous/status | tee -a "$LOG_FILE"

echo "Recent server.log excerpt (post-metal):" | tee -a "$LOG_FILE"
tail -n 200 server.log | tee -a "$LOG_FILE"

# Save grid & status snapshots
curl -s http://127.0.0.1:5000/autonomous/grid > "$LOG_DIR/grid_${TIMESTAMP}.json"
curl -s http://127.0.0.1:5000/autonomous/status > "$LOG_DIR/status_${TIMESTAMP}.json"

echo "Hardware test completed. Logs -> $LOG_FILE" | tee -a "$LOG_FILE"
echo "Grid snapshot: $LOG_DIR/grid_${TIMESTAMP}.json" | tee -a "$LOG_FILE"
echo "Status snapshot: $LOG_DIR/status_${TIMESTAMP}.json" | tee -a "$LOG_FILE"

echo "To stop autonomous mode: curl -s -H 'Content-Type: application/json' -X POST -d '{\"mode\":\"manual\"}' http://127.0.0.1:5000/mode/switch" | tee -a "$LOG_FILE"
