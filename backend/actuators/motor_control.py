"""Actuator wrapper for motor commands in the PRAMAN AMR stack."""
import motor


def set_speed(value):
    motor.set_speed(value)


def move(direction, speed=None):
    if speed is not None:
        motor.set_speed(speed)

    if direction == 'forward':
        motor.forward()
    elif direction == 'backward':
        motor.backward()
    elif direction == 'left':
        motor.left()
    elif direction == 'right':
        motor.right()
    else:
        motor.stop()


def stop():
    motor.stop()


def set_motor_speed(left_speed, right_speed):
    motor.set_motor_speed(left_speed, right_speed)


def servo_open():
    motor.set_servo_angle(90)


def servo_close():
    motor.set_servo_angle(0)


def servo_pulse():
    motor.pulse_servo(0)


def cleanup():
    motor.cleanup()
