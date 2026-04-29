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
        self.obstacle_stop_distance = 12  # cm
        self.obstacle_slow_distance = 50  # cm

        # Runtime state
        self.current_speed = 0
        self.latest_distances = {'center': 999, 'left': 999, 'right': 999}
        self.last_error: Optional[str] = None
        self.obstacle_log: List[Dict] = []
        self.servo_enabled = True

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
        """Get current status."""
        with self.lock:
            progress = 0.0
            if self.current_path and len(self.current_path) > 0:
                progress = (self.current_waypoint_index / len(self.current_path)) * 100

            return {
                'mode': 'autonomous' if self.is_autonomous else 'manual',
                'status': self.status,
                'robot_position': [round(self.robot_position[0], 2), round(self.robot_position[1], 2)],
                'current_waypoint': self.current_waypoint_index,
                'total_waypoints': len(self.current_path),
                'progress': round(progress, 1),
                'autonomous_speed': self.current_speed,
                'min_speed': self.min_speed,
                'max_speed': self.max_speed,
                'nearest_obstacle_cm': self._nearest_obstacle(self.latest_distances),
                'obstacle_log': self.obstacle_log[-10:],
                'path': [[int(x), int(y)] for x, y in self.current_path],
                'servo_enabled': self.servo_enabled,
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
                ultrasonic = data.get('ultrasonic', {})
                center = ultrasonic.get('center', 999)
                left = ultrasonic.get('left', 999)
                right = ultrasonic.get('right', 999)

                with self.lock:
                    self.latest_distances = {'center': center, 'left': left, 'right': right}

                print(f"[AUTONOMY SENSOR] center={center:.1f}cm left={left:.1f}cm right={right:.1f}cm")

                # Check metal detection
                metal = data.get('metal_detector', {}).get('detected', False)
                if metal and self.servo_enabled:
                    self._trigger_servo_action()
                    self._request_replan('Metal detected')

                # Check proximity threshold
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

        # Apply motor command
        motor.set_speed(int(self.current_speed))
        motor.forward()

        # Update position estimate
        if dist > 0.05:
            step = 0.05 + (self.current_speed / 100.0) * 0.05
            move_x = (dx / dist) * step
            move_y = (dy / dist) * step
            with self.lock:
                self.robot_position[0] += move_x
                self.robot_position[1] += move_y

    def _is_waypoint_reached(self, waypoint: Tuple[int, int]) -> bool:
        """Check if waypoint reached."""
        wx, wy = waypoint
        rx, ry = self.robot_position
        dist = math.hypot(wx - rx, wy - ry)
        return dist <= self.waypoint_tolerance

    # ========== SENSOR INTEGRATION ==========

    def _update_grid_from_sensors(self, center: float, left: float, right: float):
        """Update grid obstacles from sensor readings."""
        cell_size = 10  # 10cm per cell

        obs = set()

        # Center sensor (forward)
        if 0 < center < self.proximity_threshold:
            grid_dist = int(center / cell_size)
            for i in range(1, min(grid_dist + 1, 6)):
                candidate = (int(self.robot_position[0]), int(self.robot_position[1]) - i)
                if self.grid._valid_coords(candidate[0], candidate[1]):
                    obs.add(candidate)
                    self.grid.set_obstacle(candidate[0], candidate[1], True)

        # Left sensor
        if 0 < left < self.proximity_threshold:
            grid_dist = int(left / cell_size)
            for i in range(1, min(grid_dist + 1, 6)):
                candidate = (int(self.robot_position[0]) - i, int(self.robot_position[1]))
                if self.grid._valid_coords(candidate[0], candidate[1]):
                    obs.add(candidate)
                    self.grid.set_obstacle(candidate[0], candidate[1], True)

        # Right sensor
        if 0 < right < self.proximity_threshold:
            grid_dist = int(right / cell_size)
            for i in range(1, min(grid_dist + 1, 6)):
                candidate = (int(self.robot_position[0]) + i, int(self.robot_position[1]))
                if self.grid._valid_coords(candidate[0], candidate[1]):
                    obs.add(candidate)
                    self.grid.set_obstacle(candidate[0], candidate[1], True)

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

    def _log_obstacle_event(self, reason: str):
        """Log obstacle event."""
        entry = {
            'ts': time.time(),
            'reason': reason,
            'distance_cm': self._nearest_obstacle(self.latest_distances)
        }
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
