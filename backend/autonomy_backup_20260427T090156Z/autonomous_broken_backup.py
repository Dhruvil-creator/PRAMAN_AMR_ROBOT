"""
Autonomous Navigation Manager - Phase 2 implementation

This module implements the Phase 2 autonomous manager: A* planning,
100ms sensor monitoring, grid updates from ultrasonic sensors,
servo trigger on detection (75->120->75), and simple waypoint execution.

This implementation intentionally avoids Phase 3 DWA motion control and
keeps manual control behavior untouched.
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
    Phase 2 Autonomous manager. Features:
    - Mode switching (manual/autonomous)
    - Plan & execute A* path
    - Sensor monitor (100ms) updates grid and triggers replans
    - Servo automation on proximity/metal detection (75->120->75)
    - Simple speed control (min/max PWM, linear slowdown near obstacles)
    """

    def __init__(self, grid_map: GridMap, get_sensor_data_func):
        self.grid = grid_map
        self.get_sensor_data = get_sensor_data_func

        # State
        self.is_autonomous = False
        self.is_executing = False
        self.current_path: List[Tuple[int, int]] = []
        self.current_waypoint_index = 0
        self.robot_position = [0.0, 0.0]
        self.robot_heading = 0.0

        # Threads & locking
        self.lock = threading.Lock()
        self.execution_thread: Optional[threading.Thread] = None
        self.sensor_thread: Optional[threading.Thread] = None

        # Config
        self.sensor_update_interval = 0.1  # seconds
        self.proximity_threshold = 30      # cm -> trigger replan
        self.waypoint_tolerance = 0.75
        self.min_autonomous_speed = 40
        self.max_autonomous_speed = 75
        self.obstacle_stop_distance = 12
        self.obstacle_slow_distance = 50

        # Runtime
        self.current_speed = 0
        self.latest_distances = {"center": 999, "left": 999, "right": 999}
        self.status = 'idle'
        self.last_error: Optional[str] = None
        self.obstacle_log: List[Dict] = []
        self.replan_cooldown = 0.8
        self.last_replan_time = 0.0
        self.servo_enabled = True

    # Public API
    def switch_to_autonomous(self):
        with self.lock:
            self.is_autonomous = True
            self.status = 'idle'
        print("📍 Switched to autonomous mode")
        return {'mode': 'autonomous'}

    def switch_to_manual(self):
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
        with self.lock:
            if self.is_executing:
                return {'error': 'Already executing'}
            if not self.is_autonomous:
                return {'error': 'Switch to autonomous mode before executing path'}
            if not path or len(path) < 2:
                return {'error': 'Invalid path'}

            self.current_path = path
            self.current_waypoint_index = 1
            self.is_executing = True
            self.status = 'executing'
            self.current_speed = self.min_autonomous_speed
            # Start robot position at first waypoint
            self.robot_position = [float(path[0][0]), float(path[0][1])]
            self.last_replan_time = 0.0

        # Start background threads
        self.sensor_thread = threading.Thread(target=self._sensor_monitor_loop, daemon=True)
        self.sensor_thread.start()
        self.execution_thread = threading.Thread(target=self._execution_loop, daemon=True)
        self.execution_thread.start()

        return {'status': 'executing', 'path_length': len(path), 'first_waypoint': list(path[self.current_waypoint_index])}

    def stop_autonomous_execution(self):
        with self.lock:
            self.is_executing = False
            self.status = 'idle'
            self.current_speed = 0
        motor.stop()
        print("⏹️ Stopped autonomous execution")
        return {'status': 'stopped'}

    def get_status(self) -> Dict:
        with self.lock:
            progress = 0.0
            if self.current_path:
                progress = (self.current_waypoint_index / max(1, len(self.current_path))) * 100
            return {
                'mode': 'autonomous' if self.is_autonomous else 'manual',
                'status': self.status,
                'robot_position': [round(self.robot_position[0], 2), round(self.robot_position[1], 2)],
                'current_waypoint': self.current_waypoint_index,
                'total_waypoints': len(self.current_path),
                'progress': progress,
                'autonomous_speed': self.current_speed,
                'min_autonomous_speed': self.min_autonomous_speed,
                'max_autonomous_speed': self.max_autonomous_speed,
                'nearest_obstacle_cm': self._nearest_obstacle_distance(self.latest_distances),
                'obstacle_log': self.obstacle_log[-10:],
                'path': [[x, y] for x, y in self.current_path]
            }

    def set_servo_enabled(self, enabled: bool):
        self.servo_enabled = bool(enabled)
        return {'servo_enabled': self.servo_enabled}

    # Internal loops
    def _sensor_monitor_loop(self):
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

                # Metal detector handling
                metal = data.get('metal_detector', {}).get('detected', False)
                if metal and self.servo_enabled:
                    self._trigger_servo()
                    self._request_replan('Metal detected')

                # Proximity handling
                if self._check_proximity_threshold(center, left, right):
                    self._request_replan('Obstacle detected')

            except Exception as e:
                print(f"❌ Sensor monitor error: {e}")
            time.sleep(self.sensor_update_interval)

    def _execution_loop(self):
        while True:
            with self.lock:
                if not self.is_executing:
                    break
                if self.status == 'replanning' or self.status == 'paused':
                    time.sleep(0.1)
                    continue
                if self.current_waypoint_index >= len(self.current_path):
                    self.is_executing = False
                    self.status = 'idle'
                    motor.stop()
                    print("✅ Path execution complete!")
                    break
                waypoint = self.current_path[self.current_waypoint_index]

            # Move toward waypoint
            try:
                self._move_toward_waypoint(waypoint)
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
            time.sleep(0.05)

    # Motion helpers (simple)
    def _move_toward_waypoint(self, waypoint: Tuple[int, int]):
        wx, wy = waypoint
        rx, ry = self.robot_position
        dx = wx - rx
        dy = wy - ry
        dist = math.hypot(dx, dy)
        if dist <= 0:
            motor.stop()
            return

        target_speed = self._calculate_target_speed()
        if target_speed <= 0:
            motor.stop()
            return

        # Smooth step toward target
        if self.current_speed < target_speed:
            self.current_speed = min(target_speed, self.current_speed + 5)
        elif self.current_speed > target_speed:
            self.current_speed = max(target_speed, self.current_speed - 5)

        motor.set_speed(int(self.current_speed))
        motor.forward()

        # Simple position estimate (grid cells per cycle)
        step = 0.05 + (self.current_speed / 100.0) * 0.05
        move_x = (dx / dist) * step
        move_y = (dy / dist) * step
        with self.lock:
            self.robot_position[0] += move_x
            self.robot_position[1] += move_y

    def _is_waypoint_reached(self, waypoint: Tuple[int, int]) -> bool:
        wx, wy = waypoint
        rx, ry = self.robot_position
        return math.hypot(wx - rx, wy - ry) <= self.waypoint_tolerance

    # Sensor integration
    def _update_grid_from_sensors(self, center_dist: float, left_dist: float, right_dist: float):
        cell_cm = 10
        obs = set()
        # center
        if 0 < center_dist < self.proximity_threshold:
            grid_dist = int(center_dist / cell_cm)
            for i in range(1, min(grid_dist + 1, 6)):
                candidate = (int(self.robot_position[0]), int(self.robot_position[1]) - i)
                if self.grid._valid_coords(candidate[0], candidate[1]):
                    obs.add(candidate)
                    self.grid.set_obstacle(candidate[0], candidate[1], True)
        # left
        if 0 < left_dist < self.proximity_threshold:
            grid_dist = int(left_dist / cell_cm)
            for i in range(1, min(grid_dist + 1, 6)):
                candidate = (int(self.robot_position[0]) - i, int(self.robot_position[1]))
                if self.grid._valid_coords(candidate[0], candidate[1]):
                    obs.add(candidate)
                    self.grid.set_obstacle(candidate[0], candidate[1], True)
        # right
        if 0 < right_dist < self.proximity_threshold:
            grid_dist = int(right_dist / cell_cm)
            for i in range(1, min(grid_dist + 1, 6)):
                candidate = (int(self.robot_position[0]) + i, int(self.robot_position[1]))
                if self.grid._valid_coords(candidate[0], candidate[1]):
                    obs.add(candidate)
                    self.grid.set_obstacle(candidate[0], candidate[1], True)
        return obs

    def _check_proximity_threshold(self, center, left, right) -> bool:
        return (
            (0 < center < self.proximity_threshold) or
            (0 < left < self.proximity_threshold) or
            (0 < right < self.proximity_threshold)
        )

    def _request_replan(self, reason: str = 'Obstacle detected'):
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
        try:
            with self.lock:
                if not self.grid.goal:
                    self.status = 'idle'
                    return
                start = tuple(map(int, self.robot_position))
            # Temporarily set grid start to current position
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
                    # keep paused
                    self.status = 'paused'
                    print("⚠️ No viable path found during replan")
            # restore old start
            self.grid.set_start(old_start[0], old_start[1])
        except Exception as e:
            print(f"❌ Replan error: {e}")
            with self.lock:
                self.status = 'idle'
                self.last_error = str(e)

    def set_speed_limits(self, min_speed: int, max_speed: int):
        with self.lock:
            self.min_autonomous_speed = max(0, min(100, int(min_speed)))
            self.max_autonomous_speed = max(0, min(100, int(max_speed)))
        return {'min_autonomous_speed': self.min_autonomous_speed, 'max_autonomous_speed': self.max_autonomous_speed}

    def recenter_start(self):
        with self.lock:
            x, y = map(int, self.robot_position)
            if self.grid._valid_coords(x, y):
                self.grid.set_start(x, y)
            return self.grid.to_dict()

    def resume_autonomous(self):
        with self.lock:
            if not self.is_executing:
                return {'error': 'Not executing'}
            if self.status != 'paused':
                return {'error': 'Not paused'}
            self.status = 'replanning'
        self._replan_path()
        return {'status': self.status}

    def _calculate_target_speed(self) -> int:
        nearest = self._nearest_obstacle_distance(self.latest_distances)
        if nearest is None:
            return self.max_autonomous_speed
        if nearest <= self.obstacle_stop_distance:
            return 0
        if nearest >= self.obstacle_slow_distance:
            return self.max_autonomous_speed
        # linear interpolation
        ratio = (nearest - self.obstacle_stop_distance) / (self.obstacle_slow_distance - self.obstacle_stop_distance)
        val = self.min_autonomous_speed + ratio * (self.max_autonomous_speed - self.min_autonomous_speed)
        return int(max(self.min_autonomous_speed, min(self.max_autonomous_speed, val)))

    def _nearest_obstacle_distance(self, distances: Dict[str, float]) -> Optional[float]:
        vals = [v for v in distances.values() if isinstance(v, (int, float)) and 0 < v < 999]
        return min(vals) if vals else None

    def _log_obstacle_event(self, reason: str):
        entry = {'ts': time.time(), 'reason': reason, 'distance_cm': self._nearest_obstacle_distance(self.latest_distances)}
        self.obstacle_log.append(entry)
        if len(self.obstacle_log) > 50:
            self.obstacle_log = self.obstacle_log[-50:]

    def _trigger_servo(self):
        try:
            print("�� Servo triggered")
            # Use pulse_servo helper in motor module; ensure servo follows 75->120->75
            threading.Thread(target=lambda: motor.pulse_servo(120, duration=0.2), daemon=True).start()
        except Exception as e:
            print(f"⚠️ Servo error: {e}")

# end of file
