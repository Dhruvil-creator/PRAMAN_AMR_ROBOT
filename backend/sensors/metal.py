# backend/sensors/metal.py

import time
try:
    import RPi.GPIO as GPIO
except Exception:
    # Minimal MockGPIO so sensors can run off-device for development
    class _MockPWM:
        def __init__(self, pin, freq):
            self.pin = pin
            self.freq = freq
            self._duty = 0
        def start(self, duty):
            self._duty = duty
        def ChangeDutyCycle(self, duty):
            self._duty = duty
        def stop(self):
            pass
    class _MockGPIO:
        BCM = 'BCM'
        OUT = 'OUT'
        IN = 'IN'
        PUD_UP = 'PUD_UP'
        HIGH = 1
        LOW = 0
        def setwarnings(self, flag):
            pass
        def setmode(self, mode):
            pass
        def setup(self, *args, **kwargs):
            pass
        def input(self, pin):
            return 0
        def output(self, pin, val):
            pass
        def PWM(self, pin, freq):
            return _MockPWM(pin, freq)
    GPIO = _MockGPIO()

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

METAL_PIN = 6

# Try to setup with error handling - don't crash on GPIO busy
_gpio_ready = False
try:
    GPIO.setup(METAL_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    _gpio_ready = True
except Exception as e:
    print(f"⚠️  Metal sensor GPIO setup deferred: {e}")
    _gpio_ready = False

# debounce buffer
_last_state = None
_last_time = time.time()
_debounce_time = 0.2


def read():
    """Read metal detector state with debouncing (matches test_metal_sensor.py logic)."""
    global _last_state, _last_time
    
    if not _gpio_ready:
        return False
    
    try:
        val = GPIO.input(METAL_PIN)
        now = time.time()
        
        # Debounce: only update state if pin value changed and debounce time elapsed
        if _last_state is None or (val != _last_state and now - _last_time > _debounce_time):
            _last_state = val
            _last_time = now
        
        # Metal detected when pin is HIGH (1) - same as test_metal_sensor.py line 20
        return _last_state == 1
    except Exception as e:
        print(f"Metal sensor read error: {e}")
        return False


def get_hazard():
    """Return metal sensor hazard status in a unified format."""
    return {"detected": bool(read())}

