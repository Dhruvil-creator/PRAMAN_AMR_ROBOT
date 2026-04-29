import RPi.GPIO as GPIO
import time

SERVO_PIN = 19

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

pwm = GPIO.PWM(SERVO_PIN, 50)

# -------------------------
# DIRECT POSITION SET (FAST)
# -------------------------
def set_position(angle):
    duty = 2.5 + (angle / 18.0)
    
    pwm.start(duty)
    time.sleep(0.25)   # short pulse only
    pwm.stop()         # STOP signal → no shaking


# -------------------------
# ACTION (90° SWING)
# -------------------------
def servo_action():
    print("Move backward 90°")
    set_position(120)

    time.sleep(0.2)

    print("Return to center")
    set_position(75)


# -------------------------
# MAIN
# -------------------------
try:
    print("Setting center position")
    set_position(75)

    while True:
        input("Press ENTER to trigger...")
        servo_action()

except KeyboardInterrupt:
    GPIO.cleanup()
