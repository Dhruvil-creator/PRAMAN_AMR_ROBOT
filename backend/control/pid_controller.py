import time

class PIDController:
    """Simple PID controller.

    compute(measurement) returns control output.
    Keeps internal state for integral/derivative.
    """

    def __init__(self, kp=1.0, ki=0.0, kd=0.0, setpoint=0.0, output_limits=(None, None)):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.setpoint = float(setpoint)
        self.output_limits = output_limits

        self._last_time = None
        self._last_error = 0.0
        self._integral = 0.0

    def reset(self):
        self._last_time = None
        self._last_error = 0.0
        self._integral = 0.0

    def compute(self, measurement, dt=None):
        """Compute PID output for a given measurement.

        measurement: current measured value
        dt: optional delta-time in seconds (if omitted, internal clock is used)
        """
        now = time.time()
        error = float(self.setpoint) - float(measurement)

        if self._last_time is None:
            delta = dt if dt is not None else 0.0
        else:
            delta = dt if dt is not None else (now - self._last_time)

        if delta > 0.0:
            derivative = (error - self._last_error) / delta
        else:
            derivative = 0.0

        self._integral += error * (delta if delta > 0.0 else 0.0)

        output = (self.kp * error) + (self.ki * self._integral) + (self.kd * derivative)

        lo, hi = self.output_limits
        if lo is not None:
            output = max(lo, output)
        if hi is not None:
            output = min(hi, output)

        self._last_error = error
        self._last_time = now
        return float(output)
