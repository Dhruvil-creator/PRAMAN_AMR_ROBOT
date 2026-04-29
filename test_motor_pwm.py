import motor
import time

motor.set_speed(60)

motor.forward()
time.sleep(3)

motor.left()
time.sleep(2)

motor.right()
time.sleep(2)

motor.backward()
time.sleep(3)

motor.stop()