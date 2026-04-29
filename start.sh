#!/bin/bash
# PRAMAN AMR Startup Script - Handles complete cleanup and startup

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/server.log"
PID_FILE="/tmp/amr_server.pid"

cleanup() {
    echo "🛑 Shutting down gracefully..."
    if [ -f "$PID_FILE" ]; then
        kill $(cat "$PID_FILE") 2>/dev/null || true
        rm "$PID_FILE"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "🤖 PRAMAN AMR Dashboard"
echo "======================="
echo ""

# Kill any existing processes
echo "🧹 Cleaning up old processes..."
pkill -9 -f "python3 app.py" 2>/dev/null || true
pkill -9 -f "libcamera" 2>/dev/null || true
sleep 2

# Check and free port 5000 if needed
if lsof -i :5000 > /dev/null 2>&1; then
    echo "⚠️  Port 5000 in use, killing old process..."
    OLD_PID=$(lsof -ti :5000 | head -1)
    if [ ! -z "$OLD_PID" ]; then
        kill -9 $OLD_PID 2>/dev/null || true
        sleep 2
    fi
fi

# Reset GPIO state
echo "🔌 Resetting GPIO state..."
python3 << 'EOFINIT'
import sys
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.cleanup()
except Exception as e:
    pass
EOFINIT

sleep 1

# Start application
echo "✅ Starting application..."
echo "📍 Dashboard: http://localhost:5000"
echo "📊 Monitor logs: tail -f $LOG_FILE"
echo ""
echo "Press Ctrl+C to stop"
echo "======================="
echo ""

cd "$SCRIPT_DIR"
python3 app.py 2>&1 | tee "$LOG_FILE" &
APP_PID=$!
echo $APP_PID > "$PID_FILE"

# Keep the script running
wait $APP_PID

