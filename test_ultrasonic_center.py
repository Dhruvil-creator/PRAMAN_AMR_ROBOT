import RPi.GPIO as GPIO
import time

# -------------------------
# PIN CONFIG
# -------------------------
TRIG = 23
ECHO = 5

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

GPIO.output(TRIG, False)
time.sleep(1)

# -------------------------
# MEASURE FUNCTION
# -------------------------
def measure_distance():
    # Send trigger pulse
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start_time = time.time()
    timeout = start_time + 0.03

    # Wait for echo HIGH
    while GPIO.input(ECHO) == 0:
        if time.time() > timeout:
            return None
        start_time = time.time()

    end_time = time.time()
    timeout = end_time + 0.03

    # Wait for echo LOW
    while GPIO.input(ECHO) == 1:
        if time.time() > timeout:
            return None
        end_time = time.time()

    duration = end_time - start_time
    distance = duration * 17150  # cm

    return round(distance, 2)

# -------------------------
# MAIN LOOP
# -------------------------
print("=== CENTER ULTRASONIC TEST ===")

try:
    while True:
        dist = measure_distance()

        if dist is None:
            print("No signal (timeout)")
        else:
            if dist > 400:
                dist = 400

            if dist < 20:
                status = "DANGER"
            elif dist < 50:
                status = "NEAR"
            else:
                status = "SAFE"

            print(f"Distance: {dist} cm → {status}")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nStopped by user")

finally:
    GPIO.cleanup()