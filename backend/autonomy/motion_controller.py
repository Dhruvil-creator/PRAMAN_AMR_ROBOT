"""Motion controller: PID & safe movement helpers.

Default: simulation-friendly; hardware calls only when use_hardware=True and motor/imu modules exist.
"""
import time
import math
from typing import Optional, Tuple


class PIDController:
    def __init__(self, kp: float = 1.0, ki: float = 0.0, kd: float = 0.0, out_min: float = -100.0, out_max: float = 100.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.out_min = out_min
        self.out_max = out_max
        self._integral = 0.0
        self._last_error = 0.0

    def compute(self, error: float, dt: float) -> float:
        self._integral += error * dt
        derivative = 0.0 if dt <= 0 else (error - self._last_error) / dt
        out = (self.kp * error) + (self.ki * self._integral) + (self.kd * derivative)
        self._last_error = error
        if out < self.out_min:
            return self.out_min
        if out > self.out_max:
            return self.out_max
        return out


class MotionController:
    def __init__(self, use_hardware: bool = False):
        self.use_hardware = bool(use_hardware)
        self.motor = None
        self.imu = None
        self.heading_est_deg = 0.0
        self._last_heading_ts: Optional[float] = None
        try:
            if self.use_hardware:
                import motor
                import imu
                self.motor = motor
                self.imu = imu
        except Exception:
            # hardware not available
            self.motor = None
            self.imu = None

        self.heading_pid = PIDController(kp=1.0, ki=0.0, kd=0.05, out_min=-30, out_max=30)
        self.abort_check = None

    def _should_abort(self) -> bool:
        try:
            return bool(self.abort_check and self.abort_check())
        except Exception:
            return False

    def stop(self):
        if self.use_hardware and self.motor is not None:
            try:
                self.motor.stop()
            except Exception:
                pass

    def set_heading_estimate(self, heading_deg: float):
        self.heading_est_deg = float(heading_deg) % 360.0
        self._last_heading_ts = time.time()

    def align_to_angle(self, target_deg: float, timeout: float = 3.0, tolerance_deg: float = 8.0) -> bool:
        """Align robot heading to target_deg. If no IMU or hardware, return True immediately (no-op simulation).
        """
        if not self.use_hardware or self.imu is None:
            # Simulation: assume alignment successful
            time.sleep(0.05)
            return True

        # Hardware alignment loop (best-effort)
        start = time.time()
        try:
            heading_fn = getattr(self.imu, 'get_heading', None)
            gyro_fn = getattr(self.imu, 'get_gyro_z', None)
            while time.time() - start < timeout:
                if self._should_abort():
                    self.stop()
                    return False
                if heading_fn is not None:
                    current = heading_fn()
                elif gyro_fn is not None:
                    now = time.time()
                    if self._last_heading_ts is None:
                        self._last_heading_ts = now
                    dt = now - self._last_heading_ts
                    self._last_heading_ts = now
                    if 0 < dt <= 0.2:
                        self.heading_est_deg = (self.heading_est_deg + (gyro_fn() * dt)) % 360.0
                    current = self.heading_est_deg
                else:
                    time.sleep(0.02)
                    return True
                error = (target_deg - current + 180.0) % 360.0 - 180.0
                if abs(error) <= tolerance_deg:
                    # aligned
                    self.stop()
                    return True
                # compute turn command using PID, then apply symmetric turn speed
                correction = self.heading_pid.compute(error, 0.05)
                turn_speed = max(35, min(80, int(abs(correction) + 35)))
                # Set motor direction for turning
                try:
                    self.motor.set_speed(turn_speed)
                    if correction > 0:
                        self.motor.right()
                    else:
                        self.motor.left()
                except Exception:
                    pass
                time.sleep(0.05)
        except Exception:
            return False
        try:
            self.stop()
        except Exception:
            pass
        return False

    def move_to_waypoint(self, grid_manager, target_gx: int, target_gy: int, step_m: float = 0.05, speed: int = 60, drive_time: Optional[float] = None) -> bool:
        """Step towards a grid waypoint. In simulation (default) this simply updates the grid_manager.robot_world.
        Returns True when waypoint reached.
        """
        tx, ty = grid_manager.grid_to_world(target_gx, target_gy)
        cx, cy = grid_manager.robot_world
        dx = tx - cx
        dy = ty - cy
        dist = math.hypot(dx, dy)
        if dist <= step_m:
            grid_manager.set_robot_position(tx, ty)
            grid_manager.set_visited(target_gx, target_gy)
            if self.use_hardware and self.motor is not None:
                self.stop()
            return True
        nx = cx + (dx / dist) * step_m
        ny = cy + (dy / dist) * step_m

        if self.use_hardware and self.motor is not None and speed > 0:
            try:
                if self._should_abort():
                    self.stop()
                    return False
                self.motor.set_speed(int(speed))
                self.motor.forward()
                total = drive_time if drive_time is not None else 0.08
                deadline = time.time() + max(0.0, float(total))
                while time.time() < deadline:
                    if self._should_abort():
                        self.stop()
                        return False
                    time.sleep(0.01)
            except Exception:
                pass

        grid_manager.set_robot_position(nx, ny)
        gx, gy = grid_manager.world_to_grid(nx, ny)
        grid_manager.set_visited(gx, gy)
        return False
