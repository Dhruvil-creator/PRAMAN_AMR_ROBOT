"""
Phase 2: Autonomous Navigation Manager - CLEAN IMPLEMENTATION
- A* path planning
- 100ms sensor monitoring (ultrasonic)
- Dynamic path replanning on obstacle detection
- Servo automation on proximity/metal detection
- Real-time status reporting
- Manual mode always takes priority

NO Phase 3 DWA code. NO experimental features.
"""

import threading
import time
import math
from typing import List, Tuple, Optional, Dict
from backend.pathfinding import GridMap, AStarPathfinder
import motor
import imu

IMU_AVAILABLE = getattr(imu, "_HAS_SMBUS", False)


class AutonomousModeManager:
    """
    Phase 2 Autonomous Mode Manager.
    Manages path planning, execution, sensor monitoring, and replanning.
    """

    def __init__(self, grid_map: GridMap, get_sensor_data_func):
        """Initialize autonomous manager."""
        self.grid = grid_map
        self.get_sensor_data = get_sensor_data_func

        # State: mode and execution
        self.is_autonomous = False
        self.is_executing = False
        self.status = 'idle'  # idle, planning, executing, paused, error

        # Path tracking
        self.current_path: List[Tuple[int, int]] = []
        self.current_waypoint_index = 0
        self.robot_position = [0.0, 0.0]

        # Configuration
        self.proximity_threshold = 30  # cm
        self.waypoint_tolerance = 0.75  # grid cells
        self.min_speed = 40  # PWM
        self.max_speed = 75  # PWM
        # Safety: increase stop distance so robot halts earlier when obstacle detected
        self.obstacle_stop_distance = 20  # cm (was 12)
        self.obstacle_slow_distance = 50  # cm

        # Runtime state
        self.current_speed = 0
        self.latest_distances = {'center': 999, 'left': 999, 'right': 999}
        self.last_error: Optional[str] = None
        self.obstacle_log: List[Dict] = []
        self.servo_enabled = True

        # Obstacle persistence (coord -> timestamp)
        self._obstacle_timestamps: Dict[Tuple[int,int], float] = {}
        self.obstacle_ttl = 1.0  # seconds to keep an obstacle after last detection
        # Inflation radius (cells) — mark neighboring cells as hazards/obstacles
        self.obstacle_inflation = 1  # cells to inflate around detected obstacle

        # Metal drop behavior (edge-triggered only)
        self.metal_drop_pause = 1.5  # seconds to pause for marker drop (1-2s)
        self.metal_drop_cooldown = 3.0  # seconds between marker drops to avoid repeat
        self.last_metal_drop_time = 0.0
        # Track last metal sensor state for rising-edge detection
        self._last_metal_state = False

        # IMU-derived short-term heading estimate (integrated gyro)
        self.yaw = 0.0                # degrees, updated by integrating gyro_z
        self._last_gyro_time = None  # timestamp of last gyro integration
        self._aligned_waypoint_index = None  # waypoint index we already aligned to
        self.alignment_threshold_deg = 8.0  # acceptable heading error before moving

        # Heading PID controller for motion stability (used during path execution)
        self.heading_pid_kp = 1.0
        self.heading_pid_ki = 0.0
        self.heading_pid_kd = 0.1
        self._heading_pid_integral = 0.0
        self._heading_pid_last_error = 0.0
        self._heading_pid_last_time = None
        self._heading_pid_max = 30.0  # max PWM differential to apply

        # Threads
        self.lock = threading.Lock()
        self.execution_thread: Optional[threading.Thread] = None
        self.sensor_thread: Optional[threading.Thread] = None

        # Timing
        self.sensor_update_interval = 0.1  # 100ms
        self.last_replan_time = 0.0
        self.replan_cooldown = 0.8  # sec

    # ========== PUBLIC API ==========

    def switch_to_autonomous(self):
        """Switch to autonomous mode."""
        with self.lock:
            self.is_autonomous = True
            self.status = 'idle'
        print("📍 Switched to autonomous mode")
        return {'mode': 'autonomous'}

    def switch_to_manual(self):
        """Switch to manual mode (stop any execution)."""
        with self.lock:
            if self.is_executing:
                self.is_executing = False
                motor.stop()
                self.current_speed = 0
            self.is_autonomous = False
            self.status = 'idle'
        print("🎮 Switched to manual mode")
        return {'mode': 'manual'}

    def start_autonomous_execution(self, path: List[Tuple[int, int]]):
        """Start executing a path."""
        with self.lock:
            if self.is_executing:
                return {'error': 'Already executing'}
            if not self.is_autonomous:
                return {'error': 'Not in autonomous mode'}
            if not path or len(path) < 2:
                return {'error': 'Invalid path'}

            self.current_path = path
            self.current_waypoint_index = 1  # Start moving toward waypoint 1
            self.is_executing = True
            self.status = 'executing'
            self.current_speed = self.min_speed
            self.robot_position = [float(path[0][0]), float(path[0][1])]
            self.last_replan_time = 0.0

        # Start background threads
        self.sensor_thread = threading.Thread(
            target=self._sensor_monitor_loop, daemon=True, name='SensorMonitor'
        )
        self.sensor_thread.start()

        self.execution_thread = threading.Thread(
            target=self._execution_loop, daemon=True, name='PathExecution'
        )
        self.execution_thread.start()

        return {
            'status': 'executing',
            'path_length': len(path),
            'first_waypoint': list(path[self.current_waypoint_index]) if self.current_waypoint_index < len(path) else None
        }

    def stop_autonomous_execution(self):
        """Stop execution immediately."""
        with self.lock:
            self.is_executing = False
            self.status = 'idle'
            self.current_speed = 0

        motor.stop()
        print("⏹️ Stopped autonomous execution")
        return {'status': 'stopped'}

    def get_status(self) -> Dict:
        """Get current status including grid snapshot and additional diagnostics."""
        with self.lock:
            progress = 0.0
            total_waypoints = len(self.current_path)
            if total_waypoints > 0:
                progress = (self.current_waypoint_index / total_waypoints) * 100

            # Grid snapshot and overlays
            grid_dict = self.grid.to_dict() if hasattr(self.grid, 'to_dict') else None
            obstacles = []
            hazards = []
            try:
                for y in range(self.grid.height):
                    for x in range(self.grid.width):
                        val = int(self.grid.grid[y, x])
                        if val == 1:
                            obstacles.append([x, y])
                        elif val == 4:
                            hazards.append([x, y])
            except Exception:
                pass

            # ETA estimation (very rough)
            eta_seconds = None
            try:
                if self.current_path and self.current_waypoint_index < len(self.current_path):
                    rem_dist_cells = 0.0
                    rx, ry = self.robot_position
                    wp_idx = self.current_waypoint_index
                    prev = (rx, ry)
                    for p in self.current_path[wp_idx:]:
                        rem_dist_cells += self.grid.get_distance((int(round(prev[0])), int(round(prev[1]))), p)
                        prev = p
                    cell_size_m = 0.10
                    total_m = rem_dist_cells * cell_size_m
                    speed_mps = (max(self.current_speed, self.min_speed) / 100.0) * 0.5
                    if speed_mps > 0:
                        eta_seconds = total_m / speed_mps
            except Exception:
                eta_seconds = None

            return {
                'mode': 'autonomous' if self.is_autonomous else 'manual',
                'status': self.status,
                'robot_position': [round(self.robot_position[0], 2), round(self.robot_position[1], 2)],
                'robot_heading_deg': round(self.yaw, 1),
                'current_waypoint': self.current_waypoint_index,
                'total_waypoints': total_waypoints,
                'progress': round(progress, 1),
                'autonomous_speed': self.current_speed,
                'min_speed': self.min_speed,
                'max_speed': self.max_speed,
                'nearest_obstacle_cm': self._nearest_obstacle(self.latest_distances),
                'obstacle_log': self.obstacle_log[-20:],
                'path': [[int(x), int(y)] for x, y in self.current_path],
                'servo_enabled': self.servo_enabled,
                'grid': grid_dict,
                'obstacles': obstacles,
                'hazards': hazards,
                'eta_seconds': eta_seconds,
                'paused': str(self.status).startswith('paused')
            }

    def set_servo_enabled(self, enabled: bool):
        """Enable/disable servo automation."""
        self.servo_enabled = bool(enabled)
        return {'servo_enabled': self.servo_enabled}

    def set_speed_limits(self, min_speed: int, max_speed: int):
        """Set autonomous speed limits."""
        with self.lock:
            self.min_speed = max(0, min(100, int(min_speed)))
            self.max_speed = max(0, min(100, int(max_speed)))
        return {'min_speed': self.min_speed, 'max_speed': self.max_speed}

    def recenter_start(self):
        """Set grid start to robot's current position."""
        with self.lock:
            x, y = map(int, self.robot_position)
            if self.grid._valid_coords(x, y):
                self.grid.set_start(x, y)
        return self.grid.to_dict()

    def resume_autonomous(self):
        """Resume after pause."""
        with self.lock:
            if self.status == 'paused':
                self.status = 'executing'
        return {'status': self.status}

    # ========== INTERNAL LOOPS ==========

    def _sensor_monitor_loop(self):
        """Monitor sensors in background (100ms cycle)."""
        while True:
            with self.lock:
                if not self.is_executing:
                    break

            try:
                data = self.get_sensor_data()

                # ---------- IMU integration (short-term yaw estimate) ----------
                imu_data = data.get('imu', {}) or {}
                gz = imu_data.get('gyro_z', 0)
                now = time.time()
                with self.lock:
                    if getattr(self, '_last_gyro_time', None) is None:
                        self._last_gyro_time = now
                    else:
                        dt = now - self._last_gyro_time
                        try:
                            self.yaw += float(gz) * dt
                        except Exception:
                            pass
                        # normalize yaw to [-180, 180]
                        self.yaw = ((self.yaw + 180.0) % 360.0) - 180.0
                        self._last_gyro_time = now

                ultrasonic = data.get('ultrasonic', {})
                center = ultrasonic.get('center', 999)
                left = ultrasonic.get('left', 999)
                right = ultrasonic.get('right', 999)

                with self.lock:
                    self.latest_distances = {'center': center, 'left': left, 'right': right}

                print(f"[AUTONOMY SENSOR] center={center:.1f}cm left={left:.1f}cm right={right:.1f}cm yaw={self.yaw:.1f}°")

                # Update grid obstacles from sensors
                try:
                    added = self._update_grid_from_sensors(center, left, right)
                    if added:
                        print(f"[AUTONOMY GRID] Added obstacles: {len(added)}")
                except Exception as e:
                    print(f"⚠️ Grid update error: {e}")

                # Check metal detection (edge-triggered only)
                metal = data.get('metal', {}).get('detected', False)
                last_metal = getattr(self, '_last_metal_state', False)
                # On rising edge of metal detection -> stop, drop marker, mark grid, resume
                if metal and not last_metal and self.servo_enabled and (time.time() - getattr(self, 'last_metal_drop_time', 0.0)) > getattr(self, 'metal_drop_cooldown', 3.0):
                    self.last_metal_drop_time = time.time()
                    print(f"🔔 Metal detected at robot position: pausing for marker drop")

                    # Immediate stop
                    motor.stop()
                    with self.lock:
                        self._prev_speed = self.current_speed
                        self.current_speed = 0
                        self.status = 'paused_for_metal'

                    # Log the metal drop event
                    self._log_obstacle_event('Metal detected', action='drop')

                    # Trigger servo action in a background thread (non-blocking)
                    try:
                        threading.Thread(target=lambda: motor.pulse_servo(120, duration=0.4), daemon=True).start()
                    except Exception as e:
                        print(f"⚠️ Servo trigger error: {e}")

                    # Pause briefly to allow drop to complete
                    time.sleep(getattr(self, 'metal_drop_pause', 1.5))

                    # Mark hazard on grid at current robot position
                    try:
                        hx = int(round(self.robot_position[0]))
                        hy = int(round(self.robot_position[1]))
                        if self.grid._valid_coords(hx, hy):
                            try:
                                if hasattr(self.grid, 'set_hazard'):
                                    self.grid.set_hazard(hx, hy)
                                else:
                                    # fallback: place marker value 4 if not start/goal
                                    if self.grid.grid[hy, hx] not in (2, 3):
                                        self.grid.grid[hy, hx] = 4
                                print(f"🟥 Hazard marked at {(hx, hy)}")
                            except Exception as e:
                                print(f"⚠️ Failed to mark hazard: {e}")
                    except Exception as e:
                        print(f"⚠️ Hazard marking failed: {e}")

                    # After marking, resume executing (if still executing)
                    with self.lock:
                        if self.is_executing:
                            self.current_speed = max(self.min_speed, getattr(self, '_prev_speed', self.min_speed))
                            self.status = 'executing'

                    # update last metal state
                    self._last_metal_state = True

                    # small sleep to avoid busy-loop
                    time.sleep(0.05)
                    continue

                # Immediate proximity handling: stop and replan (no servo action)
                nearest = self._nearest_obstacle({'center': center, 'left': left, 'right': right})
                if nearest is not None and nearest <= self.obstacle_stop_distance:
                    motor.stop()
                    with self.lock:
                        self.current_speed = 0
                        self.status = 'paused'
                    print(f"⏹️ Immediate stop due to close obstacle ({nearest}cm) — no servo action")
                    # request replan (will respect cooldown)
                    self._request_replan('Immediate proximity stop')
                    # small sleep to avoid busy-looping
                    time.sleep(0.05)
                    continue

                # Update last metal state for next cycle
                self._last_metal_state = metal

                # Check proximity threshold and request replan
                if self._check_proximity(center, left, right):
                    self._request_replan('Obstacle proximity')

            except Exception as e:
                print(f"❌ Sensor monitor error: {e}")

            time.sleep(self.sensor_update_interval)

    def _execution_loop(self):
        """Follow path waypoints (50ms cycle)."""
        while True:
            with self.lock:
                if not self.is_executing:
                    break

                # Handle state transitions
                if self.status == 'replanning' or self.status == 'paused':
                    time.sleep(0.1)
                    continue

                # Check if path complete
                if self.current_waypoint_index >= len(self.current_path):
                    self.is_executing = False
                    self.status = 'idle'
                    motor.stop()
                    print("✅ Path complete!")
                    break

                waypoint = self.current_path[self.current_waypoint_index]

            # Move toward waypoint
            try:
                self._move_toward_waypoint(waypoint)

                # Check if waypoint reached
                if self._is_waypoint_reached(waypoint):
                    with self.lock:
                        self.current_waypoint_index += 1
                        print(f"📍 Waypoint {self.current_waypoint_index - 1} reached")

            except Exception as e:
                print(f"❌ Execution error: {e}")
                motor.stop()
                with self.lock:
                    self.status = 'error'
                    self.last_error = str(e)
                break

            time.sleep(0.05)  # 20Hz

    # ========== MOTION CONTROL ==========

    def _move_toward_waypoint(self, waypoint: Tuple[int, int]):
        """Move robot toward waypoint with speed control."""
        wx, wy = waypoint
        rx, ry = self.robot_position
        dx = wx - rx
        dy = wy - ry
        dist = math.hypot(dx, dy)

        if dist <= 0:
            motor.stop()
            return

        # Before moving, ensure robot is oriented toward the waypoint (one-time per waypoint)
        current_index = self.current_waypoint_index
        aligned_index = getattr(self, '_aligned_waypoint_index', None)
        if aligned_index != current_index:
            if IMU_AVAILABLE:
                ok = self._align_to_waypoint(waypoint, timeout=3.0)
                if not ok:
                    # Could not align in time, pause and let execution loop retry
                    motor.stop()
                    with self.lock:
                        self.status = 'paused'
                        self.current_speed = 0
                    return
            else:
                # No IMU available: skip alignment but mark as aligned
                with self.lock:
                    self._aligned_waypoint_index = current_index

        # Calculate target speed based on nearest obstacle
        target_speed = self._calculate_target_speed()

        if target_speed <= 0:
            motor.stop()
            self.current_speed = 0
            return

        # Smooth speed ramp
        ramp_step = 3
        if self.current_speed < target_speed:
            self.current_speed = min(target_speed, self.current_speed + ramp_step)
        elif self.current_speed > target_speed:
            self.current_speed = max(target_speed, self.current_speed - ramp_step)

        self.current_speed = max(self.min_speed, min(self.max_speed, self.current_speed))

        # Heading correction (PID) & send differential motor commands
        # Compute target bearing and heading error
        try:
            target_bearing = math.degrees(math.atan2(dy, dx))
        except Exception:
            target_bearing = 0.0
        error = self._normalize_angle_deg(target_bearing - getattr(self, 'yaw', 0.0))

        now_pid = time.time()
        if getattr(self, '_heading_pid_last_time', None) is None:
            dt_pid = 0.05
        else:
            dt_pid = max(0.001, now_pid - self._heading_pid_last_time)

        correction = self._heading_pid(error, dt_pid)

        base_speed = int(self.current_speed)
        left_pwm = int(max(0, min(100, base_speed - correction)))
        right_pwm = int(max(0, min(100, base_speed + correction)))

        try:
            motor.forward()
            motor.set_motor_speed(left_pwm, right_pwm)
        except Exception as e:
            print(f"⚠️ Motor drive error: {e}")

        # Update position estimate
        if dist > 0.05:
            step = 0.05 + (self.current_speed / 100.0) * 0.05
            move_x = (dx / dist) * step
            move_y = (dy / dist) * step
            with self.lock:
                self.robot_position[0] += move_x
                self.robot_position[1] += move_y
                # Mark visited cell on the grid for visualization (non-blocking)
                try:
                    hx = int(round(self.robot_position[0]))
                    hy = int(round(self.robot_position[1]))
                    if hasattr(self.grid, 'set_visited') and self.grid._valid_coords(hx, hy):
                        self.grid.set_visited(hx, hy)
                except Exception:
                    pass

    def _is_waypoint_reached(self, waypoint: Tuple[int, int]) -> bool:
        """Check if waypoint reached."""
        wx, wy = waypoint
        rx, ry = self.robot_position
        dist = math.hypot(wx - rx, wy - ry)
        return dist <= self.waypoint_tolerance

    # ========== SENSOR INTEGRATION ==========

    def _update_grid_from_sensors(self, center: float, left: float, right: float):
        """Update grid obstacles from sensor readings with short persistence.

        Returns set of obstacle coordinates newly (or currently) detected.
        """
        cell_size = 10  # 10cm per cell
        now = time.time()

        # Clean up stale obstacles
        stale = []
        for coord, ts in list(self._obstacle_timestamps.items()):
            if (now - ts) > self.obstacle_ttl:
                stale.append(coord)

        for coord in stale:
            try:
                self.grid.set_obstacle(coord[0], coord[1], False)
            except Exception:
                pass
            del self._obstacle_timestamps[coord]

        obs = set()

        # Center sensor (forward)
        if 0 < center < self.proximity_threshold:
            grid_dist = int(center / cell_size)
            for i in range(1, min(grid_dist + 1, 6)):
                base_candidate = (int(self.robot_position[0]), int(self.robot_position[1]) - i)
                for dx in range(-self.obstacle_inflation, self.obstacle_inflation + 1):
                    for dy in range(-self.obstacle_inflation, self.obstacle_inflation + 1):
                        candidate = (base_candidate[0] + dx, base_candidate[1] + dy)
                        if not self.grid._valid_coords(candidate[0], candidate[1]):
                            continue
                        # Skip start/goal cells
                        if (self.grid.start and candidate == self.grid.start) or (self.grid.goal and candidate == self.grid.goal):
                            continue
                        obs.add(candidate)
                        try:
                            self.grid.set_obstacle(candidate[0], candidate[1], True)
                        except Exception:
                            pass
                        self._obstacle_timestamps[candidate] = now

        # Left sensor
        if 0 < left < self.proximity_threshold:
            grid_dist = int(left / cell_size)
            for i in range(1, min(grid_dist + 1, 6)):
                base_candidate = (int(self.robot_position[0]) - i, int(self.robot_position[1]))
                for dx in range(-self.obstacle_inflation, self.obstacle_inflation + 1):
                    for dy in range(-self.obstacle_inflation, self.obstacle_inflation + 1):
                        candidate = (base_candidate[0] + dx, base_candidate[1] + dy)
                        if not self.grid._valid_coords(candidate[0], candidate[1]):
                            continue
                        if (self.grid.start and candidate == self.grid.start) or (self.grid.goal and candidate == self.grid.goal):
                            continue
                        obs.add(candidate)
                        try:
                            self.grid.set_obstacle(candidate[0], candidate[1], True)
                        except Exception:
                            pass
                        self._obstacle_timestamps[candidate] = now

        # Right sensor
        if 0 < right < self.proximity_threshold:
            grid_dist = int(right / cell_size)
            for i in range(1, min(grid_dist + 1, 6)):
                base_candidate = (int(self.robot_position[0]) + i, int(self.robot_position[1]))
                for dx in range(-self.obstacle_inflation, self.obstacle_inflation + 1):
                    for dy in range(-self.obstacle_inflation, self.obstacle_inflation + 1):
                        candidate = (base_candidate[0] + dx, base_candidate[1] + dy)
                        if not self.grid._valid_coords(candidate[0], candidate[1]):
                            continue
                        if (self.grid.start and candidate == self.grid.start) or (self.grid.goal and candidate == self.grid.goal):
                            continue
                        obs.add(candidate)
                        try:
                            self.grid.set_obstacle(candidate[0], candidate[1], True)
                        except Exception:
                            pass
                        self._obstacle_timestamps[candidate] = now

        return obs

    def _check_proximity(self, center: float, left: float, right: float) -> bool:
        """Check if any sensor is below proximity threshold."""
        return (
            (0 < center < self.proximity_threshold) or
            (0 < left < self.proximity_threshold) or
            (0 < right < self.proximity_threshold)
        )

    def _request_replan(self, reason: str = 'Obstacle'):
        """Request path replanning."""
        now = time.time()
        with self.lock:
            if (now - self.last_replan_time) < self.replan_cooldown:
                return

            self.last_replan_time = now
            self.status = 'replanning'
            self.current_speed = 0
            self._log_obstacle_event(reason)
            print(f"🔄 Replanning due to: {reason}")

        motor.stop()
        self._replan_path()

    def _replan_path(self):
        """Recalculate path from current position."""
        try:
            with self.lock:
                if not self.grid.goal:
                    self.status = 'idle'
                    return
                start = tuple(map(int, self.robot_position))

            # Temporarily update grid start
            old_start = self.grid.start
            self.grid.set_start(start[0], start[1])

            pathfinder = AStarPathfinder(self.grid)
            new_path, stats = pathfinder.find_path()

            with self.lock:
                if new_path:
                    self.current_path = pathfinder.smooth_path(new_path)
                    self.current_waypoint_index = 1 if len(self.current_path) > 1 else 0
                    self.status = 'executing'
                    print(f"✅ Replanned: {len(self.current_path)} waypoints")
                else:
                    self.status = 'paused'
                    print("⚠️ No viable path, paused")

            # Restore original start
            self.grid.set_start(old_start[0], old_start[1])

        except Exception as e:
            print(f"❌ Replan error: {e}")
            with self.lock:
                self.status = 'error'
                self.last_error = str(e)

    def _calculate_target_speed(self) -> int:
        """Calculate speed based on nearest obstacle."""
        nearest = self._nearest_obstacle(self.latest_distances)

        if nearest is None:
            return self.max_speed

        if nearest <= self.obstacle_stop_distance:
            return 0

        if nearest >= self.obstacle_slow_distance:
            return self.max_speed

        # Linear interpolation
        ratio = (nearest - self.obstacle_stop_distance) / (self.obstacle_slow_distance - self.obstacle_stop_distance)
        speed = self.min_speed + ratio * (self.max_speed - self.min_speed)
        return int(max(self.min_speed, min(self.max_speed, speed)))

    def _nearest_obstacle(self, distances: Dict[str, float]) -> Optional[float]:
        """Get nearest obstacle distance."""
        values = [v for v in distances.values() if isinstance(v, (int, float)) and 0 < v < 999]
        return min(values) if values else None

    def _log_obstacle_event(self, reason: str, action: Optional[str] = None):
        """Log obstacle event."""
        entry = {
            'ts': time.time(),
            'reason': reason,
            'distance_cm': self._nearest_obstacle(self.latest_distances)
        }
        if action:
            entry['action'] = action
        self.obstacle_log.append(entry)
        if len(self.obstacle_log) > 50:
            self.obstacle_log = self.obstacle_log[-50:]

    def _trigger_servo_action(self):
        """Trigger servo: 75° → 120° → 75°."""
        try:
            print("🔔 Servo triggered")
            threading.Thread(
                target=lambda: motor.pulse_servo(120, duration=0.2),
                daemon=True
            ).start()
        except Exception as e:
            print(f"⚠️ Servo error: {e}")

    def _normalize_angle_deg(self, angle: float) -> float:
        """Normalize angle to [-180, 180] degrees."""
        return ((angle + 180.0) % 360.0) - 180.0

    def _align_to_waypoint(self, waypoint: Tuple[int, int], timeout: float = 5.0) -> bool:
        """Rotate robot in-place to face the waypoint before forward motion.

        Uses short-term integrated IMU yaw (self.yaw). Returns True if aligned
        within self.alignment_threshold_deg before timeout, False otherwise.
        """
        wx, wy = waypoint
        rx, ry = self.robot_position
        dx = wx - rx
        dy = wy - ry
        # target bearing in degrees
        target_bearing = math.degrees(math.atan2(dy, dx))

        start = time.time()
        while time.time() - start < float(timeout):
            with self.lock:
                current_yaw = float(self.yaw)
            error = self._normalize_angle_deg(target_bearing - current_yaw)
            if abs(error) <= getattr(self, 'alignment_threshold_deg', 8.0):
                motor.stop()
                with self.lock:
                    self._aligned_waypoint_index = self.current_waypoint_index
                return True

            # proportional turn speed (clamped)
            turn_speed = int(max(30, min(60, abs(error) * 0.6)))
            try:
                if error > 0:
                    # rotate left
                    motor.left()
                    motor.set_motor_speed(turn_speed, turn_speed)
                else:
                    # rotate right
                    motor.right()
                    motor.set_motor_speed(turn_speed, turn_speed)
            except Exception as e:
                print(f"⚠️ Rotation command failed: {e}")

            time.sleep(0.05)

        motor.stop()
        return False

    def _heading_pid(self, error_deg: float, dt: float) -> float:
        """Compute PID output (PWM differential) for heading error in degrees using PIDController.

        Uses backend.control.pid_controller.PIDController for consistent tuning and testing.
        """
        if dt is None or dt <= 0:
            return 0.0

        try:
            if not hasattr(self, 'heading_pid_controller') or self.heading_pid_controller is None:
                from backend.control.pid_controller import PIDController
                self.heading_pid_controller = PIDController(
                    kp=self.heading_pid_kp,
                    ki=self.heading_pid_ki,
                    kd=self.heading_pid_kd,
                    setpoint=0.0,
                    output_limits=(-self._heading_pid_max, self._heading_pid_max)
                )
            else:
                # update gains in case they were tuned at runtime
                self.heading_pid_controller.kp = self.heading_pid_kp
                self.heading_pid_controller.ki = self.heading_pid_ki
                self.heading_pid_controller.kd = self.heading_pid_kd
                self.heading_pid_controller.output_limits = (-self._heading_pid_max, self._heading_pid_max)
        except Exception as e:
            print(f"⚠️ PID controller init/update error: {e}")
            return 0.0

        # PIDController computes (setpoint - measurement). We want output ~= Kp * error_deg.
        # Use setpoint=0 and pass measurement = -error_deg so (0 - (-error)) = +error.
        try:
            self.heading_pid_controller.setpoint = 0.0
            corr = self.heading_pid_controller.compute(-error_deg, dt=dt)
        except Exception as e:
            print(f"⚠️ PID compute error: {e}")
            corr = 0.0

        return float(corr)
