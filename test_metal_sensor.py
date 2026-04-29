import RPi.GPIO as GPIO
import time

METAL_PIN = 6

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Enable pull-up
GPIO.setup(METAL_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("=== METAL DETECTOR TEST ===")

try:
    while True:
        state = GPIO.input(METAL_PIN)

        print("Raw:", state)  # DEBUG

        if state == 1:
            print("Metal Detected ✅")
        else:
            print("No Metal ❌")

        print("-------------------")
        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nStopped")

finally:
    GPIO.cleanup()