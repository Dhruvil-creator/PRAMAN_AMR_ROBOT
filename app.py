import sys
import time
import atexit

# AUTO-CLEANUP GPIO on startup to prevent "GPIO not allocated" errors
def cleanup_gpio_on_startup():
    """Automatically cleanup any orphaned GPIO processes before starting."""
    for attempt in range(3):
        try:
            import RPi.GPIO as GPIO
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.cleanup()
                return
            except Exception:
                pass
        except Exception:
            pass
        if attempt < 2:
            time.sleep(0.5)

def cleanup_on_exit():
    """Cleanup GPIO when application exits."""
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except:
        pass

# Register cleanup on exit
atexit.register(cleanup_on_exit)

# Cleanup on import to ensure clean state
cleanup_gpio_on_startup()

from backend.server import run

if __name__ == '__main__':
    run(host='0.0.0.0', port=5000, debug=False)
