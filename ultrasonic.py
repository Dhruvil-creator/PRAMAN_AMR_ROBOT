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
import statistics

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

SENSORS = {
    "center": {"trig": 23, "echo": 5},
    "left": {"trig": 26, "echo": 25},
    "right": {"trig": 21, "echo": 24}
}

# Try to setup pins with error handling - don't crash on GPIO busy
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
# MEASURE
# -------------------------
def measure(trig, echo):
    if not _gpio_ready:
        return None
    
    try:
        GPIO.output(trig, True)
        time.sleep(0.00001)
        GPIO.output(trig, False)

        start = time.time()
        timeout = start + 0.03

        while GPIO.input(echo) == 0:
            if time.time() > timeout:
                return None
            start = time.time()

        end = time.time()
        timeout = end + 0.03

        while GPIO.input(echo) == 1:
            if time.time() > timeout:
                return None
            end = time.time()

        return (end - start) * 17150
    except Exception:
        return None


# -------------------------
# FILTERED READ
# -------------------------
def stable_read(trig, echo):
    readings = []

    for _ in range(3):
        val = measure(trig, echo)

        if val is not None and 2 < val < 400:
            readings.append(val)

        time.sleep(0.02)

    if not readings:
        return 400

    return round(statistics.median(readings), 2)


# -------------------------
# SEQUENTIAL READ
# -------------------------
def read_all():
    data = {}

    for name in ["left", "center", "right"]:
        pins = SENSORS[name]

        data[name] = stable_read(pins["trig"], pins["echo"])

        time.sleep(0.1)   # 🔥 slightly increased for better isolation

    return data


# -------------------------
# MAIN LOOP (ADDED)
# -------------------------
print("=== ULTRASONIC MULTI SENSOR TEST ===")

try:
    while True:
        data = read_all()

        for name, dist in data.items():

            if dist >= 400:
                status = "OUT"
            elif dist < 20:
                status = "DANGER"
            elif dist < 50:
                status = "NEAR"
            else:
                status = "SAFE"

            print(f"{name.upper():6}: {dist:6.2f} cm → {status}")

        print("-" * 40)

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nStopped")
    GPIO.cleanup()