import RPi.GPIO as GPIO
import time

# -------------------------
# CONFIG
# -------------------------
PIR_PIN = 16

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

print("=== PIR SENSOR TEST ===")
print("Waiting for sensor to stabilize (30 sec)...")

# PIR needs warm-up time
time.sleep(30)

print("System ready. Monitoring motion...\n")

try:
    while True:
        state = GPIO.input(PIR_PIN)

        if state:
            print("MOTION DETECTED")
        else:
            print("No motion")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nExiting...")
    GPIO.cleanup()