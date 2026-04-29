# backend/sensors/ultrasonic.py

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

SENSORS = {
    "center": {"trig": 23, "echo": 5},
    "left": {"trig": 26, "echo": 25},
    "right": {"trig": 21, "echo": 24}
}

# Maximum wait timeout for echoes (seconds)
TIMEOUT = 0.03

# Setup pins with error handling - don't crash on GPIO busy
_gpio_ready = False
try:
    for s in SENSORS.values():
        GPIO.setup(s["trig"], GPIO.OUT)
        GPIO.setup(s["echo"], GPIO.IN)
        GPIO.output(s["trig"], False)
    _gpio_ready = True
    time.sleep(0.5)
except Exception as e:
    print(f"⚠️  Ultrasonic GPIO setup deferred: {e}")
    _gpio_ready = False


# -------------------------
# LOW LEVEL MEASURE
# -------------------------
def measure(trig, echo):
    if not _gpio_ready:
        return None
    GPIO.output(trig, True)
    time.sleep(0.00001)
    GPIO.output(trig, False)

    # Wait for echo to go HIGH
    wait_start = time.time()
    while GPIO.input(echo) == 0:
        if time.time() - wait_start > TIMEOUT:
            return None

    # Record the exact moment echo went HIGH
    start = time.time()

    # Wait for echo to go LOW
    wait_end = time.time()
    while GPIO.input(echo) == 1:
        if time.time() - wait_end > TIMEOUT:
            return None

    # Record the exact moment echo went LOW
    end = time.time()

    distance = (end - start) * 17150
    return round(distance, 2)


# -------------------------
# FILTERED STABLE READ
# -------------------------
def stable_read(trig, echo):
    readings = []

    for _ in range(3):
        val = measure(trig, echo)

        # Reject invalid readings
        if val is not None and 2 < val < 400:
            readings.append(val)

        # Slightly longer pause between pulses for better isolation
        time.sleep(0.05)

    # If all readings failed
    if not readings:
        # Treat as invalid (0cm) so safety layers can hard-stop
        return 0

    avg = sum(readings) / len(readings)

    # Clamp to safe range
    avg = max(2, min(avg, 400))

    return round(avg, 2)


# -------------------------
# READ ALL SENSORS
# -------------------------
def read_all():
    data = {}

    for name, pins in SENSORS.items():
        data[name] = stable_read(pins["trig"], pins["echo"])
        # Give sensors brief time to settle between triggers
        time.sleep(0.08)

    return data


def get_distance():
    """Return unified ultrasonic distance values."""
    return read_all()
