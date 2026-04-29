# backend/sensors/pir.py

import time
try:
    import RPi.GPIO as GPIO
except Exception:
    # Minimal MockGPIO for development
    class _MockPWM:
        def __init__(self, pin, freq):
            self.pin = pin; self.freq = freq; self._duty = 0
        def start(self, duty): self._duty = duty
        def ChangeDutyCycle(self, duty): self._duty = duty
        def stop(self): pass
    class _MockGPIO:
        BCM = 'BCM'; OUT = 'OUT'; IN = 'IN'; LOW = 0; HIGH = 1
        def setwarnings(self, flag): pass
        def setmode(self, mode): pass
        def setup(self, *args, **kwargs): pass
        def input(self, pin): return 0
        def output(self, pin, val): pass
        def PWM(self, pin, freq): return _MockPWM(pin, freq)
    GPIO = _MockGPIO()

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

PIR_PIN = 16

# Try to setup with error handling - don't crash on GPIO busy
_gpio_ready = False
try:
    GPIO.setup(PIR_PIN, GPIO.IN)
    _gpio_ready = True
except Exception as e:
    print(f"⚠️  PIR sensor GPIO setup deferred: {e}")
    _gpio_ready = False

# Simple debounce buffer
_last_state = False
_last_time = 0


def read():
    global _last_state, _last_time

    if not _gpio_ready:
        return False

    try:
        val = GPIO.input(PIR_PIN)
        now = time.time()

        # debounce (avoid rapid flicker)
        if val != _last_state:
            if now - _last_time > 0.3:
                _last_state = val
                _last_time = now

        return _last_state
    except Exception:
        return False


def get_motion():
    """Return PIR motion state in a unified format."""
    return {"detected": bool(read())}
