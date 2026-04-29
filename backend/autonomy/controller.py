"""AutonomousController: orchestrates sensor_manager -> planner -> motion -> events -> dashboard.

Default operation is simulation-friendly (does not command motors) unless use_hardware=True.
"""
import threading
import time
import math
from typing import Optional, Tuple, List

from .grid_manager import GridManager
from .path_planner import PathPlanner
from .sensor_manager import SensorManager
from .motion_controller import MotionController
from .event_manager import EventManager
from .dashboard_sync import build_status, emit_status_via_socketio

try:
    import motor
except Exception:
    motor = None


class AutonomousController:
    def __init__(self, use_hardware: bool = False):
        self.use_hardware = bool(use_hardware)
        self.grid = GridManager()
        self.sensors = SensorManager()
        self.planner = PathPlanner(self.grid)
        self.motion = MotionController(use_hardware=self.use_hardware)
        self.motion.abort_check = lambda: (
            self._safety_hold
            or self.paused
            or self.state in ('fail_safe', 'stopped')
        )
        self.events = EventManager(self.grid, use_hardware=self.use_hardware)

        self._exec_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()

        self.current_path: List[Tuple[int,int]] = []
        self.current_waypoint_index = 0
        self.state = 'idle'
        self.paused = False
        self.pause_reason: Optional[str] = None
        self.obstacle_log: List[dict] = []
        self.last_nearest_obstacle_cm: Optional[float] = None
        self.robot_heading_deg = 0.0
        self.imu_heading_deg = 0.0
        self._last_imu_ts: Optional[float] = None
        self.path_trace: List[Tuple[int, int]] = []
        self.current_speed = 0.0

        self.min_speed = 40
        self.max_speed = 75
        self._base_max_speed = self.max_speed
        self.obstacle_stop_distance = 20.0
        self.obstacle_emergency_distance = 10.0
        self.obstacle_slow_distance = 50.0
        self.stop_distance_speed_factor = 12.0
        self.metal_drop_pause = 2.0
        self.metal_drop_cooldown = 3.0
        self.alignment_threshold_deg = 8.0
        self.heading_pid_kp = self.motion.heading_pid.kp
        self.heading_pid_ki = self.motion.heading_pid.ki
        self.heading_pid_kd = self.motion.heading_pid.kd
        self.servo_enabled = True
        self._last_metal_ts = 0.0
        self._last_metal_state = False
        self.obstacle_confirm_reads = 3
        self._ultra_breach_count = 0
        self.obstacle_trigger_distance = 25.0
        self.ultrasonic_max_cm = 400.0
        self.ultrasonic_emergency_cm = 5.0
        self.ultrasonic_jump_threshold = 120.0
        self.ultrasonic_drop_threshold = 80.0
        self.ultrasonic_clear_reads = 3
        self._ultra_prev = {'center': None, 'left': None, 'right': None}
        self._ultra_last_valid_nearest = None
        self._ultra_last_valid_ts = 0.0
        self._safety_hold = False
        self._safety_reason = None
        self._safety_clear_count = 0
        self._last_obstacle_cell: Optional[Tuple[int, int]] = None
        self._last_obstacle_ts = 0.0
        self._obstacle_repeat_count = 0
        self.replan_fail_count = 0
        self.replan_fail_limit = 3
        self.no_progress_timeout = 6.0
        self._last_progress_ts = time.time()
        self._last_robot_grid = self.grid.robot_grid

        self.loop_period = 0.05
        self.watchdog_timeout = 1.5
        self._last_loop_ts = time.time()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_running = False

        self.localization_snap_interval = 2.0
        self._last_snap_ts = 0.0
        self.localization_corrections = 0
        self.memory_obstacles: set[Tuple[int, int]] = set()
        self.memory_hazards: set[Tuple[int, int]] = set()
        self.failed_paths: List[dict] = []
        self.failed_paths_limit = 20
        self.last_dynamic_stop_cm = self.obstacle_stop_distance

        self.micro_avoidance_enabled = True
        self.micro_avoidance_cooldown = 1.0
        self._last_micro_ts = 0.0
        self.micro_avoidance_attempts = 0
        self.dwa_enabled = True
        self.dwa_cooldown = 1.2
        self._last_dwa_ts = 0.0
        self.dwa_bypass_attempts = 0
        self.dwa = None
        try:
            from backend.pathfinding.dwa import DynamicWindowApproach
            self.dwa = DynamicWindowApproach()
        except Exception:
            self.dwa = None

        self.low_voltage_threshold = 3.3
        self.critical_voltage_threshold = 3.0
        self.voltage_scale_floor = 0.6
        self.last_voltage: Optional[float] = None
        self.power_limited = False
        self._power_state = 'normal'

        self.event_log: List[dict] = []
        self.event_log_limit = 120
        self.speed_mps_max = 0.15
        self.min_step_m = 0.005
        self.min_drive_time = 0.15

    def start(self):
        # start sensors
        self.sensors.start()
        with self._lock:
            self._running = True
            self.state = 'idle'
            self.paused = False
            self.pause_reason = None
            self._pause_event.set()
            self._last_progress_ts = time.time()
            self._last_robot_grid = self.grid.robot_grid
            self._last_loop_ts = time.time()
            self._watchdog_running = True
        self._start_watchdog()

    def stop(self):
        with self._lock:
            self._running = False
            self.state = 'stopped'
            self.paused = False
            self.pause_reason = None
            self._pause_event.set()
            self._watchdog_running = False
        try:
            self.sensors.stop()
        except Exception:
            pass

    def set_goal_world(self, x_m: float, y_m: float):
        gx, gy = self.grid.world_to_grid(x_m, y_m)
        return self.set_goal_grid(gx, gy)

    def set_goal_grid(self, gx: int, gy: int):
        if not self.grid.is_valid(gx, gy):
            return {'error': 'invalid goal'}
        self.grid.set_goal(gx, gy)
        return {'goal': [gx, gy]}

    def plan_path(self):
        start = self.grid.robot_grid
        goal = self.grid.goal
        self._apply_memory_to_grid()
        if goal is None:
            self.replan_fail_count += 1
            return []
        path = self.planner.plan(start, goal)
        path = self.planner.smooth_path(path)
        self.current_path = path
        self.current_waypoint_index = 1 if len(path) > 1 else 0
        self.path_trace = []
        if path:
            self.replan_fail_count = 0
        else:
            self.replan_fail_count += 1
            self._remember_failed_path(start, goal)
        return path

    def execute_plan(self, blocking: bool = False):
        if not self.current_path:
            return {'error': 'no path'}
        if self._exec_thread and self._exec_thread.is_alive():
            return {'error': 'already executing'}
        self._exec_thread = threading.Thread(target=self._execution_loop, daemon=True)
        self._exec_thread.start()
        if blocking:
            self._exec_thread.join()
        return {'status': 'executing', 'path_length': len(self.current_path)}

    def resume(self):
        with self._lock:
            if not self.paused:
                return {'status': self.state}
            self.paused = False
            self.pause_reason = None
            if self._running:
                self.state = 'executing'
        self._pause_event.set()
        return {'status': self.state}

    def set_heading_pid(self, kp: float, ki: float, kd: float):
        self.heading_pid_kp = float(kp)
        self.heading_pid_ki = float(ki)
        self.heading_pid_kd = float(kd)
        self.motion.heading_pid.kp = self.heading_pid_kp
        self.motion.heading_pid.ki = self.heading_pid_ki
        self.motion.heading_pid.kd = self.heading_pid_kd

    def _pause(self, reason: str):
        with self._lock:
            self.paused = True
            self.pause_reason = reason
            self.state = 'paused'
        self._pause_event.clear()

    def _trigger_fail_safe(self, reason: str):
        with self._lock:
            if self.state == 'fail_safe':
                return
            self.state = 'fail_safe'
            self.paused = True
            self.pause_reason = reason
        self._pause_event.clear()
        self.motion.stop()
        self._log_event('fail_safe', {'reason': reason})

    def _log_obstacle(self, reason: str, distance_cm: Optional[float] = None):
        entry = {
            'ts': time.time(),
            'reason': reason,
            'distance_cm': distance_cm
        }
        self.obstacle_log.append(entry)
        if len(self.obstacle_log) > 50:
            self.obstacle_log = self.obstacle_log[-50:]

    def _log_event(self, event_type: str, data: Optional[dict] = None):
        entry = {
            'ts': time.time(),
            'type': event_type,
            'data': data or {}
        }
        self.event_log.append(entry)
        if len(self.event_log) > self.event_log_limit:
            self.event_log = self.event_log[-self.event_log_limit:]

    def _remember_failed_path(self, start: Tuple[int, int], goal: Optional[Tuple[int, int]]):
        if goal is None:
            return
        entry = {
            'ts': time.time(),
            'start': [int(start[0]), int(start[1])],
            'goal': [int(goal[0]), int(goal[1])]
        }
        self.failed_paths.append(entry)
        if len(self.failed_paths) > self.failed_paths_limit:
            self.failed_paths = self.failed_paths[-self.failed_paths_limit:]

    def _remember_obstacle(self, gx: int, gy: int):
        if (gx, gy) not in self.memory_obstacles:
            self.memory_obstacles.add((gx, gy))
            self.grid.set_obstacle(gx, gy)

    def _remember_hazard(self, gx: int, gy: int):
        if (gx, gy) not in self.memory_hazards:
            self.memory_hazards.add((gx, gy))
            self.grid.set_hazard(gx, gy)

    def _apply_memory_to_grid(self):
        for gx, gy in self.memory_obstacles:
            self.grid.set_obstacle(gx, gy)
        for gx, gy in self.memory_hazards:
            self.grid.set_hazard(gx, gy)

    def _update_heading_from_imu(self, snapshot: dict):
        imu = snapshot.get('imu') or {}
        gz = imu.get('gyro_z')
        if not isinstance(gz, (int, float)):
            return
        now = time.time()
        if self._last_imu_ts is None:
            self._last_imu_ts = now
            return
        dt = now - self._last_imu_ts
        self._last_imu_ts = now
        if dt <= 0 or dt > 1.0:
            return
        self.imu_heading_deg = (self.imu_heading_deg + (gz * dt)) % 360.0
        self.robot_heading_deg = self.imu_heading_deg

    def _apply_power_limits(self, snapshot: dict):
        system = snapshot.get('system') or {}
        voltage = system.get('voltage')
        if isinstance(voltage, (int, float)):
            self.last_voltage = float(voltage)
        if self.last_voltage is None:
            self.power_limited = False
            self._power_state = 'normal'
            return
        if self.last_voltage <= self.critical_voltage_threshold:
            state = 'critical'
            scale = self.voltage_scale_floor
        elif self.last_voltage <= self.low_voltage_threshold:
            state = 'low'
            scale = 0.8
        else:
            state = 'normal'
            scale = 1.0

        if state != self._power_state:
            if state == 'critical':
                self._log_event('power_critical', {'voltage': self.last_voltage})
            elif state == 'low':
                self._log_event('power_low', {'voltage': self.last_voltage})
            else:
                self._log_event('power_normal', {'voltage': self.last_voltage})
            self._power_state = state

        if state == 'normal':
            self.power_limited = False
            self.max_speed = self._base_max_speed
        else:
            self.power_limited = True
            self.max_speed = max(self.min_speed, int(self._base_max_speed * scale))

    def _snap_robot_to_grid(self, reason: str, force: bool = False):
        now = time.time()
        if not force and (now - self._last_snap_ts) < self.localization_snap_interval:
            return
        gx, gy = self.grid.robot_grid
        x_m, y_m = self.grid.grid_to_world(gx, gy)
        self.grid.set_robot_position(x_m, y_m)
        self._last_snap_ts = now
        self.localization_corrections += 1
        self._log_obstacle(f'Localization snap: {reason}')

    def _estimate_ahead_cell(self, gx: int, gy: int, target: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        if target:
            dx = target[0] - gx
            dy = target[1] - gy
        else:
            dx = 1
            dy = 0
        if dx == 0 and dy == 0:
            return gx, gy
        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)
        return gx + step_x, gy + step_y

    def _compute_speed(self, nearest_cm: Optional[float]) -> float:
        if nearest_cm is None:
            return float(self.max_speed)
        if nearest_cm <= self.obstacle_stop_distance:
            return 0.0
        if nearest_cm >= self.obstacle_slow_distance:
            return float(self.max_speed)
        span = max(1.0, self.obstacle_slow_distance - self.obstacle_stop_distance)
        ratio = (nearest_cm - self.obstacle_stop_distance) / span
        return float(self.min_speed + (self.max_speed - self.min_speed) * ratio)

    def _dynamic_stop_distance(self) -> float:
        speed_ratio = 0.0
        if self.max_speed > 0:
            speed_ratio = min(1.0, max(0.0, self.current_speed / self.max_speed))
        dynamic_stop = self.obstacle_stop_distance + (self.stop_distance_speed_factor * speed_ratio)
        return max(self.obstacle_emergency_distance, dynamic_stop)

    def _sleep_cycle(self, loop_start: float):
        elapsed = time.time() - loop_start
        remaining = self.loop_period - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _start_watchdog(self):
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def _watchdog_loop(self):
        while self._watchdog_running:
            time.sleep(0.2)
            if not self._running:
                continue
            if self.state != 'executing':
                continue
            if (time.time() - self._last_loop_ts) > self.watchdog_timeout:
                self._trigger_fail_safe('watchdog timeout')

    def _apply_heading_pid(self):
        self.motion.heading_pid.kp = self.heading_pid_kp
        self.motion.heading_pid.ki = self.heading_pid_ki
        self.motion.heading_pid.kd = self.heading_pid_kd

    def _hard_stop(self, reason: str, details: Optional[dict] = None):
        self.current_speed = 0.0
        if self.use_hardware and motor is not None:
            try:
                if getattr(motor, 'hard_stop', None):
                    motor.hard_stop()
                else:
                    motor.stop()
            except Exception:
                pass
        try:
            self.motion.stop()
        except Exception:
            pass
        payload = {'reason': reason}
        if details:
            payload.update(details)
        self._log_event('hard_stop', payload)

    def _set_safety_hold(self, reason: str, distance_cm: Optional[float] = None):
        if not self._safety_hold or self._safety_reason != reason:
            self._log_event('emergency_stop', {'reason': reason, 'distance_cm': distance_cm})
            try:
                print(f"[SAFETY] Emergency stop: reason={reason} distance={distance_cm}")
            except Exception:
                pass
        self._safety_hold = True
        self._safety_reason = reason
        self._safety_clear_count = 0
        self.paused = True
        self.pause_reason = reason
        if self.state != 'fail_safe':
            self.state = 'paused'

    def _clear_safety_hold(self):
        self._safety_hold = False
        self._safety_reason = None
        self._safety_clear_count = 0
        if self.pause_reason:
            self.pause_reason = None
        if self.state == 'paused':
            self.state = 'executing'
        self.paused = False

    def _update_ultrasonic_state(self, ultrasonic: dict):
        readings = {}
        reasons: List[str] = []
        invalid = False
        unsafe = False
        now = time.time()

        for key in ('center', 'left', 'right'):
            raw = ultrasonic.get(key) if isinstance(ultrasonic, dict) else None
            if not isinstance(raw, (int, float)):
                invalid = True
                reasons.append(f'{key}_missing')
                continue
            val = float(raw)
            readings[key] = val
            prev = self._ultra_prev.get(key)

            if val <= 0:
                invalid = True
                reasons.append(f'{key}_invalid')
            if val > self.ultrasonic_max_cm:
                invalid = True
                reasons.append(f'{key}_over_max')
            if val < self.ultrasonic_emergency_cm:
                unsafe = True
                reasons.append(f'{key}_too_close')
            if val >= self.ultrasonic_max_cm:
                if prev is not None and prev <= self.obstacle_trigger_distance:
                    invalid = True
                    reasons.append(f'{key}_max_spike')
            if prev is not None:
                if abs(val - prev) > self.ultrasonic_jump_threshold:
                    invalid = True
                    reasons.append(f'{key}_jump')
                if (prev - val) > self.ultrasonic_drop_threshold:
                    unsafe = True
                    reasons.append(f'{key}_drop')

        valid_vals = [v for v in readings.values() if isinstance(v, (int, float))]
        nearest = min(valid_vals) if valid_vals else None

        if valid_vals:
            max_val = max(valid_vals)
            min_val = min(valid_vals)
            if max_val >= self.ultrasonic_max_cm and min_val <= self.obstacle_trigger_distance:
                invalid = True
                reasons.append('sensor_inconsistent')
        else:
            invalid = True
            reasons.append('no_valid_reading')

        if nearest is not None and nearest <= self.obstacle_stop_distance:
            unsafe = True
            reasons.append('stop_distance')

        if invalid:
            if (
                self._ultra_last_valid_nearest is not None
                and self._ultra_last_valid_nearest <= self.obstacle_trigger_distance
                and (now - self._ultra_last_valid_ts) <= 1.0
            ):
                unsafe = True
                reasons.append('blind_zone')

        if not invalid and nearest is not None:
            self._ultra_last_valid_nearest = nearest
            self._ultra_last_valid_ts = now

        for key, val in readings.items():
            self._ultra_prev[key] = val

        if nearest is not None and nearest <= self.obstacle_trigger_distance and not invalid:
            self._ultra_breach_count += 1
        else:
            self._ultra_breach_count = 0

        obstacle_confirmed = self._ultra_breach_count >= self.obstacle_confirm_reads
        emergency_stop = unsafe or invalid

        return {
            'nearest_cm': nearest,
            'invalid': invalid,
            'unsafe': unsafe,
            'emergency_stop': emergency_stop,
            'obstacle_confirmed': obstacle_confirmed,
            'reasons': reasons
        }

    def _cell_is_free(self, gx: int, gy: int) -> bool:
        if not self.grid.is_valid(gx, gy):
            return False
        try:
            cell = self.grid.grid[gy][gx]
            return cell not in (self.grid.OBSTACLE, self.grid.HAZARD)
        except Exception:
            return False

    def _world_obstacles(self) -> List[Tuple[float, float]]:
        obstacles = []
        for gx, gy in self.memory_obstacles:
            obstacles.append(self.grid.grid_to_world(gx, gy))
        for gx, gy in self.memory_hazards:
            obstacles.append(self.grid.grid_to_world(gx, gy))
        return obstacles

    def _attempt_dwa_bypass(self, current: Tuple[int, int], target: Optional[Tuple[int, int]]) -> bool:
        if not self.dwa_enabled or self.dwa is None:
            return False
        if (time.time() - self._last_dwa_ts) < self.dwa_cooldown:
            return False
        if target is None:
            return False
        gx, gy = current
        cx, cy = self.grid.robot_world
        goal_w = self.grid.grid_to_world(target[0], target[1])
        yaw = math.radians(self.robot_heading_deg)
        try:
            self.dwa.odometry.set_position(cx, cy, yaw)
            v, w = self.dwa.calculate_velocity_command(goal_w, self._world_obstacles())
        except Exception:
            return False
        if v <= 0.0:
            return False
        dt = getattr(self.dwa.config, 'DT', 0.1)
        heading = yaw + (w * dt)
        step = self.grid.cell_size_m
        nx = cx + math.cos(heading) * step
        ny = cy + math.sin(heading) * step
        ngx, ngy = self.grid.world_to_grid(nx, ny)
        if (ngx, ngy) == (gx, gy):
            return False
        if not self._cell_is_free(ngx, ngy):
            return False
        idx = self.current_waypoint_index
        self.current_path = self.current_path[:idx] + [(ngx, ngy)] + self.current_path[idx:]
        self._last_dwa_ts = time.time()
        self.dwa_bypass_attempts += 1
        self._log_event('dwa_bypass', {'from': [gx, gy], 'to': [ngx, ngy]})
        return True

    def _attempt_micro_avoidance(self, current: Tuple[int, int], target: Optional[Tuple[int, int]]) -> bool:
        if not self.micro_avoidance_enabled:
            return False
        if (time.time() - self._last_micro_ts) < self.micro_avoidance_cooldown:
            return False
        if target is None:
            return False
        gx, gy = current
        dx = target[0] - gx
        dy = target[1] - gy
        if dx == 0 and dy == 0:
            return False
        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)
        left = (gx - step_y, gy + step_x)
        right = (gx + step_y, gy - step_x)
        for candidate in (left, right):
            if self._cell_is_free(candidate[0], candidate[1]) and candidate not in self.current_path:
                idx = self.current_waypoint_index
                self.current_path = self.current_path[:idx] + [candidate] + self.current_path[idx:]
                self._last_micro_ts = time.time()
                self.micro_avoidance_attempts += 1
                self._log_obstacle('Micro-avoidance', None)
                return True
        return False

    def _execution_loop(self):
        with self._lock:
            self.state = 'executing'
        while True:
            loop_start = time.time()
            self._last_loop_ts = loop_start
            with self._lock:
                if not self._running:
                    break
            if not self._pause_event.is_set():
                self._sleep_cycle(loop_start)
                continue
            # get sensors
            snapshot = self.sensors.get_snapshot()
            self._update_heading_from_imu(snapshot)

            # check emergency/gas
            gas = snapshot.get('gas') or snapshot.get('mq2') or snapshot.get('mq135')
            # basic hazard detection example
            metal = snapshot.get('metal', {}).get('detected', False) if isinstance(snapshot.get('metal'), dict) else False
            ultrasonic = snapshot.get('ultrasonic_raw') or snapshot.get('ultrasonic', {})

            ultra_state = self._update_ultrasonic_state(ultrasonic)
            nearest = ultra_state.get('nearest_cm')
            self.last_nearest_obstacle_cm = nearest

            if ultra_state.get('emergency_stop'):
                reason = 'ultrasonic_invalid' if ultra_state.get('invalid') else 'emergency_stop'
                self._hard_stop('ultrasonic', {'reason': reason, 'distance_cm': nearest, 'details': ultra_state.get('reasons')})
                self._set_safety_hold(reason, distance_cm=nearest)
                if not ultra_state.get('obstacle_confirmed') or ultra_state.get('invalid'):
                    self._sleep_cycle(loop_start)
                    continue

            if self._safety_hold:
                if ultra_state.get('emergency_stop') and (not ultra_state.get('obstacle_confirmed') or ultra_state.get('invalid')):
                    self._hard_stop('safety_hold', {'reason': self._safety_reason, 'distance_cm': nearest})
                    self._sleep_cycle(loop_start)
                    continue
                if not ultra_state.get('emergency_stop'):
                    self._safety_clear_count += 1
                    if self._safety_clear_count >= self.ultrasonic_clear_reads:
                        self._clear_safety_hold()
                    else:
                        self._hard_stop('safety_hold', {'reason': self._safety_reason, 'distance_cm': nearest})
                        self._sleep_cycle(loop_start)
                        continue
                else:
                    self._clear_safety_hold()

            # power-aware scaling
            self._apply_power_limits(snapshot)
            self._apply_heading_pid()

            # Priority handling: gas -> metal -> obstacle -> path
            if gas and isinstance(gas, dict) and gas.get('status') == 'danger':
                # mark and stop
                gx, gy = self.grid.robot_grid
                self.events.handle_gas(gx, gy)
                self._remember_hazard(gx, gy)
                self.motion.stop()
                self._log_event('gas_detected', {'grid': [gx, gy]})
                self._pause('gas')
                self._sleep_cycle(loop_start)
                continue

            metal_trigger = (
                metal
                and not self._last_metal_state
                and (time.time() - self._last_metal_ts) >= self.metal_drop_cooldown
            )
            self._last_metal_state = metal
            if metal_trigger:
                self._last_metal_ts = time.time()
                gx, gy = self.grid.robot_grid
                self.motion.stop()
                self.events.handle_hazard(gx, gy, pause_seconds=0.0, servo_action=False)
                self._remember_hazard(gx, gy)
                self._log_event('metal_detected', {'grid': [gx, gy]})
                if self.servo_enabled and self.use_hardware and motor is not None:
                    try:
                        time.sleep(self.metal_drop_pause)
                        motor.pulse_servo(120, duration=0.2)
                    except Exception:
                        pass
                else:
                    time.sleep(self.metal_drop_pause)
                self.plan_path()
                self._snap_robot_to_grid('metal', force=True)
                self._pause('metal')
                self._sleep_cycle(loop_start)
                continue

            # check obstacle close
            obstacle_confirmed = bool(ultra_state.get('obstacle_confirmed'))
            dynamic_stop = self._dynamic_stop_distance()
            self.last_dynamic_stop_cm = dynamic_stop

            if obstacle_confirmed:
                # confirm and mark obstacles in front cell
                gx, gy = self.grid.robot_grid
                next_wp = None
                if self.current_path and self.current_waypoint_index < len(self.current_path):
                    next_wp = self.current_path[self.current_waypoint_index]
                # estimate obstacle at cell ahead (projection to next waypoint)
                ahead_gx, ahead_gy = self._estimate_ahead_cell(gx, gy, target=next_wp)
                if self.grid.is_valid(ahead_gx, ahead_gy):
                    self.events.handle_obstacle(ahead_gx, ahead_gy)
                    self._remember_obstacle(ahead_gx, ahead_gy)
                    self._log_event('obstacle_detected', {
                        'grid': [ahead_gx, ahead_gy],
                        'distance_cm': nearest,
                        'ultrasonic': ultra_state.get('reasons')
                    })
                    now = time.time()
                    if self._last_obstacle_cell == (ahead_gx, ahead_gy) and (now - self._last_obstacle_ts) < 5.0:
                        self._obstacle_repeat_count += 1
                    else:
                        self._obstacle_repeat_count = 1
                    self._last_obstacle_cell = (ahead_gx, ahead_gy)
                    self._last_obstacle_ts = now
                if nearest is not None and nearest > self.obstacle_emergency_distance:
                    if self._attempt_dwa_bypass((gx, gy), next_wp):
                        self.motion.stop()
                        self._sleep_cycle(loop_start)
                        continue
                    if self._attempt_micro_avoidance((gx, gy), next_wp):
                        self.motion.stop()
                        self._log_event('micro_avoidance', {'grid': [gx, gy]})
                        self._sleep_cycle(loop_start)
                        continue
                # replan
                self.plan_path()
                if self.current_path:
                    self._log_event('replan', {'start': [gx, gy], 'goal': list(self.grid.goal or [])})
                if self.replan_fail_count >= self.replan_fail_limit or self._obstacle_repeat_count >= 3:
                    self._trigger_fail_safe('replan failed')
                    self._sleep_cycle(loop_start)
                    continue
                self.motion.stop()
                self._snap_robot_to_grid('obstacle', force=True)
                self._pause('obstacle')
                self._sleep_cycle(loop_start)
                continue

            if (time.time() - self._last_progress_ts) > self.no_progress_timeout:
                self._trigger_fail_safe('no progress')
                self._sleep_cycle(loop_start)
                continue

            # Follow path waypoints
            if not self.current_path or self.current_waypoint_index >= len(self.current_path):
                with self._lock:
                    self.state = 'complete'
                    self.paused = False
                    self.pause_reason = None
                    self.current_speed = 0.0
                self._log_event('mission_complete', {'goal': list(self.grid.goal or [])})
                break

            next_wp = self.current_path[self.current_waypoint_index]
            self.current_speed = self._compute_speed(nearest)
            if nearest is not None and nearest <= self.obstacle_trigger_distance:
                speed_high = self.current_speed > (self.min_speed + 10)
                if speed_high:
                    self._hard_stop('speed_safety', {'distance_cm': nearest, 'speed': self.current_speed})
                    self._sleep_cycle(loop_start)
                    continue
            # Align before moving toward the next waypoint
            tx, ty = self.grid.grid_to_world(next_wp[0], next_wp[1])
            cx, cy = self.grid.robot_world
            dx = tx - cx
            dy = ty - cy
            if dx != 0.0 or dy != 0.0:
                target_deg = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
                self.motion.set_heading_estimate(self.robot_heading_deg)
                aligned = self.motion.align_to_angle(target_deg, tolerance_deg=self.alignment_threshold_deg)
                if aligned:
                    self.robot_heading_deg = target_deg
            step_m = 0.05
            drive_time = None
            if self.use_hardware:
                speed_ratio = 0.0 if self.max_speed <= 0 else (self.current_speed / self.max_speed)
                if self.current_speed <= 0:
                    step_m = 0.0
                    drive_time = 0.0
                else:
                    drive_time = max(self.min_drive_time, self.loop_period)
                    step_m = max(self.min_step_m, self.speed_mps_max * speed_ratio * drive_time)
            reached = self.motion.move_to_waypoint(
                self.grid,
                next_wp[0],
                next_wp[1],
                step_m=step_m,
                speed=self.current_speed,
                drive_time=drive_time
            )
            if reached:
                self.current_waypoint_index += 1
                self._snap_robot_to_grid('waypoint')
            rgx, rgy = self.grid.robot_grid
            if not self.path_trace or self.path_trace[-1] != (rgx, rgy):
                self.path_trace.append((rgx, rgy))
            if (rgx, rgy) != self._last_robot_grid:
                self._last_robot_grid = (rgx, rgy)
                self._last_progress_ts = time.time()

            # broadcast status
            controller_status = {
                'state': self.state,
                'current_waypoint': self.current_waypoint_index,
                'path_length': len(self.current_path)
            }
            status = build_status(self.grid, snapshot, controller_status)
            try:
                emit_status_via_socketio(status)
            except Exception:
                pass

            self._sleep_cycle(loop_start)

    def get_status(self):
        snapshot = self.sensors.get_snapshot()
        controller_status = {
            'state': self.state,
            'current_waypoint': self.current_waypoint_index,
            'path_length': len(self.current_path)
        }
        status = build_status(self.grid, snapshot, controller_status)
        speed = float(self.current_speed) if self.state == 'executing' else 0.0
        status.update({
            'status': self.state,
            'current_waypoint': self.current_waypoint_index,
            'total_waypoints': len(self.current_path),
            'path': [[int(x), int(y)] for x, y in self.current_path],
            'path_trace': [[int(x), int(y)] for x, y in self.path_trace],
            'robot_position': list(self.grid.robot_grid),
            'robot_heading_deg': float(self.robot_heading_deg),
            'nearest_obstacle_cm': self.last_nearest_obstacle_cm,
            'obstacle_log': list(self.obstacle_log),
            'paused': bool(self.paused),
            'pause_reason': self.pause_reason,
            'autonomous_speed': speed,
            'min_speed': self.min_speed,
            'max_speed': self.max_speed,
            'eta_seconds': None,
            'localization': {
                'imu_heading_deg': float(self.imu_heading_deg),
                'snap_count': self.localization_corrections
            },
            'memory': {
                'obstacles': len(self.memory_obstacles),
                'hazards': len(self.memory_hazards),
                'failed_paths': len(self.failed_paths)
            },
            'safety': {
                'dynamic_stop_cm': float(self.last_dynamic_stop_cm),
                'micro_avoidance_attempts': self.micro_avoidance_attempts,
                'hold': bool(self._safety_hold),
                'reason': self._safety_reason
            },
            'local_planner': {
                'dwa_enabled': bool(self.dwa is not None and self.dwa_enabled),
                'dwa_attempts': self.dwa_bypass_attempts
            },
            'power': {
                'voltage': self.last_voltage,
                'limited': self.power_limited
            },
            'event_log': list(self.event_log)
        })
        return status
