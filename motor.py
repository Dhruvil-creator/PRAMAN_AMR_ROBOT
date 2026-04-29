import time
import threading

# -------------------------------
# HARDWARE CONFIGURATION
# -------------------------------

IN1 = 17
IN2 = 27
IN3 = 22
IN4 = 18

ENA = 12
ENB = 13

SERVO_PIN = 19
SERVO_FREQ = 50
SERVO_MIN_DUTY = 3.0
SERVO_MAX_DUTY = 11.5


def _create_mock_gpio():
    class MockPWM:
        def __init__(self, pin, freq):
            self.pin = pin
            self.freq = freq
            self.duty = 0

        def start(self, duty):
            self.duty = duty

        def ChangeDutyCycle(self, duty):
            self.duty = duty

        def stop(self):
            pass

    class MockGPIO:
        BCM = 'BCM'
        OUT = 'OUT'
        IN = 'IN'
        LOW = False
        HIGH = True

        def setwarnings(self, flag):
            pass

        def setmode(self, mode):
            pass

        def setup(self, pin, mode):
            pass

        def output(self, pin, value):
            pass

        def PWM(self, pin, freq):
            return MockPWM(pin, freq)

        def cleanup(self):
            pass

    return MockGPIO()


def _angle_to_duty(angle):
    angle = max(0, min(180, angle))
    # Use same mapping as test_servo.py: duty = 2.5 + (angle / 18.0)
    return 2.5 + (angle / 18.0)


class HardwareDriver:
    def __init__(self):
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self._has_gpio = True
        except Exception:
            self.GPIO = _create_mock_gpio()
            self._has_gpio = False

        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)

        self.GPIO.setup(IN1, self.GPIO.OUT)
        self.GPIO.setup(IN2, self.GPIO.OUT)
        self.GPIO.setup(IN3, self.GPIO.OUT)
        self.GPIO.setup(IN4, self.GPIO.OUT)

        self.GPIO.setup(ENA, self.GPIO.OUT)
        self.GPIO.setup(ENB, self.GPIO.OUT)

        # Wrap PWM objects to log duty changes for debugging and enforce hard-zero
        class PWMWrapper:
            def __init__(self, pwm_obj, name):
                self._pwm = pwm_obj
                self.name = name

            def start(self, duty):
                try:
                    print(f"[PWM] {self.name} start -> {duty}")
                except Exception:
                    pass
                self._pwm.start(duty)

            def ChangeDutyCycle(self, duty):
                try:
                    print(f"[PWM] {self.name} ChangeDutyCycle -> {duty}")
                except Exception:
                    pass
                self._pwm.ChangeDutyCycle(duty)

            def stop(self):
                try:
                    print(f"[PWM] {self.name} stop")
                except Exception:
                    pass
                self._pwm.stop()

        self.pwmA = PWMWrapper(self.GPIO.PWM(ENA, 1000), 'A')
        self.pwmB = PWMWrapper(self.GPIO.PWM(ENB, 1000), 'B')
        self.pwmA.start(0)
        self.pwmB.start(0)

        self.GPIO.setup(SERVO_PIN, self.GPIO.OUT)
        self.servo_pwm = PWMWrapper(self.GPIO.PWM(SERVO_PIN, SERVO_FREQ), 'SERVO')
        # Do not start PWM here; initial positioning is handled by the caller

    def cleanup(self):
        self.pwmA.stop()
        self.pwmB.stop()
        if getattr(self, 'servo_pwm', None):
            self.servo_pwm.stop()
        self.GPIO.cleanup()


class MotorDrive:
    def __init__(self, hardware):
        self.hardware = hardware
        self.current_speed = 0
        self.target_speed = 70
        self.pid_mode = False

    def set_speed(self, value):
        self.pid_mode = False
        self.target_speed = max(0, min(100, int(value)))

    def update_speed(self):
        if self.pid_mode:
            return

        step = 2
        if self.current_speed < self.target_speed:
            self.current_speed += step
        elif self.current_speed > self.target_speed:
            self.current_speed -= step

        self.current_speed = max(0, min(100, self.current_speed))
        self.hardware.pwmA.ChangeDutyCycle(self.current_speed)
        self.hardware.pwmB.ChangeDutyCycle(self.current_speed)
        # Heartbeat for motor watchdog
        try:
            import time as _time
            globals()['_last_update_time'] = _time.time()
        except Exception:
            pass

    def set_motor_speed(self, left_speed, right_speed):
        self.pid_mode = True
        left_speed = max(0, min(100, int(left_speed)))
        right_speed = max(0, min(100, int(right_speed)))

        self.hardware.pwmA.ChangeDutyCycle(left_speed)
        self.hardware.pwmB.ChangeDutyCycle(right_speed)
        # Heartbeat for motor watchdog
        try:
            import time as _time
            globals()['_last_update_time'] = _time.time()
        except Exception:
            pass

    def forward(self):
        self.hardware.GPIO.output(IN1, True)
        self.hardware.GPIO.output(IN2, False)
        self.hardware.GPIO.output(IN3, True)
        self.hardware.GPIO.output(IN4, False)

    def backward(self):
        self.hardware.GPIO.output(IN1, False)
        self.hardware.GPIO.output(IN2, True)
        self.hardware.GPIO.output(IN3, False)
        self.hardware.GPIO.output(IN4, True)

    def left(self):
        self.hardware.GPIO.output(IN1, True)
        self.hardware.GPIO.output(IN2, False)
        self.hardware.GPIO.output(IN3, False)
        self.hardware.GPIO.output(IN4, True)

    def right(self):
        self.hardware.GPIO.output(IN1, False)
        self.hardware.GPIO.output(IN2, True)
        self.hardware.GPIO.output(IN3, True)
        self.hardware.GPIO.output(IN4, False)

    def stop(self):
        self.set_speed(0)
        self.hardware.pwmA.ChangeDutyCycle(0)
        self.hardware.pwmB.ChangeDutyCycle(0)

        self.hardware.GPIO.output(IN1, False)
        self.hardware.GPIO.output(IN2, False)
        self.hardware.GPIO.output(IN3, False)
        self.hardware.GPIO.output(IN4, False)

    def _active_brake_pulse(self, duration=0.03):
        """Short active braking pulse to reduce coasting after emergency stop."""
        self.hardware.GPIO.output(IN1, True)
        self.hardware.GPIO.output(IN2, True)
        self.hardware.GPIO.output(IN3, True)
        self.hardware.GPIO.output(IN4, True)
        time.sleep(duration)

    def hard_stop(self):
        """Emergency stop: cut PWM, zero speed state, and drop motor outputs."""
        self.pid_mode = False
        self.target_speed = 0
        self.current_speed = 0
        self.hardware.pwmA.ChangeDutyCycle(0)
        self.hardware.pwmB.ChangeDutyCycle(0)
        try:
            self._active_brake_pulse()
        except Exception:
            pass
        self.hardware.GPIO.output(IN1, False)
        self.hardware.GPIO.output(IN2, False)
        self.hardware.GPIO.output(IN3, False)
        self.hardware.GPIO.output(IN4, False)


class ServoDrive:
    def __init__(self, hardware):
        self.hardware = hardware
        self.angle = 75
        self.lock = threading.Lock()

    def set_position(self, angle):
        """Set servo position; supports optional continuous-hold mode to diagnose/hold position."""
        target = max(0, min(180, int(angle)))
        if target == self.angle:
            return
        duty = _angle_to_duty(target)
        try:
            if globals().get('_servo_hold_mode', False):
                # Hold mode: set duty and keep PWM running
                self.hardware.servo_pwm.ChangeDutyCycle(duty)
            else:
                self.hardware.servo_pwm.start(duty)
                time.sleep(0.25)
                self.hardware.servo_pwm.stop()
        except Exception:
            try:
                # Fallback: ChangeDutyCycle
                self.hardware.servo_pwm.ChangeDutyCycle(duty)
                if not globals().get('_servo_hold_mode', False):
                    time.sleep(0.25)
                    try:
                        self.hardware.servo_pwm.stop()
                    except Exception:
                        pass
            except Exception:
                pass
        self.angle = target

    def move_servo(self, angle):
        """Direct position set (replaces smooth movement to eliminate shaking)."""
        self.set_position(angle)

    def set_servo_angle(self, angle):
        with self.lock:
            self.set_position(angle)

    def pulse_servo(self, angle, duration=0.5):
        """Servo action: move to angle, wait, then return to center (75°)."""
        with self.lock:
            self.set_position(angle)
            time.sleep(duration)
            self.set_position(75)


_hardware = None
_motor = None
_servo = None
_last_update_time = 0.0
_servo_hold_mode = False

def _init_hardware():
    global _hardware, _motor, _servo
    if _hardware is None:
        try:
            _hardware = HardwareDriver()
            _motor = MotorDrive(_hardware)
            _servo = ServoDrive(_hardware)
        except Exception as e:
            print(f"⚠️ Hardware init deferred: {e}")
            return False
    return True


def set_speed(value):
    if _init_hardware():
        _motor.set_speed(value)


def update_speed():
    if _init_hardware():
        _motor.update_speed()


def set_motor_speed(left_speed, right_speed):
    if _init_hardware():
        _motor.set_motor_speed(left_speed, right_speed)


def forward():
    if _init_hardware():
        _motor.forward()


def backward():
    if _init_hardware():
        _motor.backward()


def left():
    if _init_hardware():
        _motor.left()


def right():
    if _init_hardware():
        _motor.right()


def stop():
    if _init_hardware():
        _motor.stop()


def hard_stop():
    if _init_hardware():
        _motor.hard_stop()


def set_servo_angle(angle):
    if _init_hardware():
        _servo.set_servo_angle(angle)


def pulse_servo(angle, duration=0.5):
    if _init_hardware():
        _servo.pulse_servo(angle, duration)


def cleanup():
    if _hardware is not None:
        _hardware.cleanup()


def set_servo_hold_mode(enabled):
    """Enable/disable continuous-hold (keep PWM running) for servo."""
    if not _init_hardware():
        return {'error': 'hardware init failed'}
    global _servo_hold_mode
    _servo_hold_mode = bool(enabled)
    try:
        duty = _angle_to_duty(getattr(_servo, 'angle', 75))
        if _servo_hold_mode:
            _hardware.servo_pwm.start(duty)
        else:
            _hardware.servo_pwm.stop()
    except Exception:
        pass
    return {'servo_hold_mode': _servo_hold_mode}


def toggle_servo_hold_mode():
    if not _init_hardware():
        return {'error': 'hardware init failed'}
    return set_servo_hold_mode(not globals().get('_servo_hold_mode', False))


def get_servo_hold_mode():
    return bool(globals().get('_servo_hold_mode', False))
