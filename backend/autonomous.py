"""backend/autonomous.py

Fresh rewrite skeleton for AutonomousModeManager.
Provides a minimal, safe implementation compatible with current server endpoints.
This file is intentionally simple so it can be extended according to your new plan.
"""

import threading
import time
from typing import List, Tuple, Dict, Optional

try:
    import motor
except Exception:
    motor = None


class AutonomousModeManager:
    """Compatibility wrapper that proxies to backend.autonomy.controller.AutonomousController when available.

    Keeps the API expected by backend/server.py while leveraging the new autonomy package when present.
    """

    def __init__(self, grid_map, get_sensor_data_func):
        self.grid = grid_map
        self.get_sensor_data = get_sensor_data_func

        # Mode & execution state
        self.is_autonomous = False
        self.is_executing = False
        self.status = 'idle'  # idle, planning, executing, paused, error

        # Runtime parameters (exposed via /autonomous/params)
        self.proximity_threshold = 30
        self.min_speed = 40
        self.max_speed = 75
        self.obstacle_stop_distance = 20
        self.obstacle_slow_distance = 50
        self.metal_drop_pause = 1.5
        self.metal_drop_cooldown = 3.0
        self.alignment_threshold_deg = 8.0
        self.heading_pid_kp = 1.0
        self.heading_pid_ki = 0.0
        self.heading_pid_kd = 0.1

        # Servo / hazard
        self.servo_enabled = True

        # Path state
        self.current_path: List[Tuple[int, int]] = []
        self.current_waypoint_index: int = 0

        # Lock & threads
        self.lock = threading.Lock()
        self.sensor_thread: Optional[threading.Thread] = None
        self.execution_thread: Optional[threading.Thread] = None

        # Try to use the new AutonomousController when available
        try:
            from backend.autonomy.controller import AutonomousController
            self._controller = AutonomousController(use_hardware=True)
            # best-effort copy of start/goal if old grid exposes them
            try:
                if hasattr(grid_map, 'start') and grid_map.start:
                    self._controller.grid.start = tuple(grid_map.start)
                if hasattr(grid_map, 'goal') and grid_map.goal:
                    self._controller.grid.goal = tuple(grid_map.goal)
            except Exception:
                pass
            self._sync_controller_params()
        except Exception:
            self._controller = None

    def _sync_controller_params(self):
        if not self._controller:
            return
        self._controller.min_speed = self.min_speed
        self._controller.max_speed = self.max_speed
        try:
            self._controller._base_max_speed = self.max_speed
        except Exception:
            pass
        self._controller.obstacle_stop_distance = float(self.obstacle_stop_distance)
        self._controller.obstacle_slow_distance = float(self.obstacle_slow_distance)
        self._controller.metal_drop_pause = float(self.metal_drop_pause)
        self._controller.metal_drop_cooldown = float(self.metal_drop_cooldown)
        self._controller.alignment_threshold_deg = float(self.alignment_threshold_deg)
        try:
            self._controller.set_heading_pid(self.heading_pid_kp, self.heading_pid_ki, self.heading_pid_kd)
        except Exception:
            pass
        self._controller.servo_enabled = bool(self.servo_enabled)

    # -------------------------
    # Public API (compatibility)
    # -------------------------
    def switch_to_autonomous(self):
        with self.lock:
            self.is_autonomous = True
            self.status = 'idle'
        if self._controller:
            try:
                self._sync_controller_params()
                self._controller.start()
            except Exception:
                pass
        return {'mode': 'autonomous'}

    def switch_to_manual(self):
        with self.lock:
            self.is_autonomous = False
            self.is_executing = False
            self.status = 'idle'
        if self._controller:
            try:
                self._controller.stop()
            except Exception:
                pass
        if motor:
            try:
                motor.stop()
            except Exception:
                pass
        return {'mode': 'manual'}

    def start_autonomous_execution(self, path: List[Tuple[int, int]]):
        """Start executing a planned path (delegates to new controller when available).

        Returns an error dict when preconditions are not met to match previous API.
        """
        with self.lock:
            if self.is_executing:
                return {'error': 'Already executing'}
            if not self.is_autonomous:
                return {'error': 'Not in autonomous mode'}
            if not path or len(path) < 2:
                return {'error': 'Invalid path'}

            self.current_path = [tuple(p) for p in path]
            self.current_waypoint_index = 1
            self.is_executing = True
            self.status = 'executing'

        if self._controller:
            try:
                self._sync_controller_params()
                self._controller.current_path = [tuple(p) for p in path]
                self._controller.current_waypoint_index = 1
                self._controller.start()
                return self._controller.execute_plan()
            except Exception as e:
                return {'error': str(e)}

        # Fallback legacy behavior
        self.sensor_thread = threading.Thread(target=self._sensor_loop, daemon=True)
        self.execution_thread = threading.Thread(target=self._execution_loop, daemon=True)
        self.sensor_thread.start()
        self.execution_thread.start()

        return {
            'status': 'executing',
            'path_length': len(path),
            'first_waypoint': list(self.current_path[self.current_waypoint_index]) if self.current_waypoint_index < len(self.current_path) else None
        }

    def stop_autonomous_execution(self):
        with self.lock:
            self.is_executing = False
            self.status = 'idle'
        if self._controller:
            try:
                self._controller.stop()
            except Exception:
                pass
        if motor:
            try:
                motor.stop()
            except Exception:
                pass
        return {'status': 'stopped'}

    def get_status(self) -> Dict:
        # Prefer controller status when available
        if self._controller:
            try:
                self._sync_controller_params()
                st = self._controller.get_status()
                st['mode'] = 'autonomous' if self.is_autonomous else 'manual'
                st.setdefault('status', st.get('controller', {}).get('state', self.status))
                st.setdefault('autonomous_speed', 0)
                st['min_speed'] = self.min_speed
                st['max_speed'] = self.max_speed
                st['servo_enabled'] = self.servo_enabled
                status = st.get('status')
                self.status = status or self.status
                if status in ('executing', 'paused', 'fail_safe'):
                    self.is_executing = True
                elif status in ('idle', 'complete', 'stopped'):
                    self.is_executing = False
                return st
            except Exception:
                pass

        with self.lock:
            total_waypoints = len(self.current_path)
            progress = 0.0
            if total_waypoints > 0:
                progress = (self.current_waypoint_index / total_waypoints) * 100

            grid_dict = self.grid.to_dict() if hasattr(self.grid, 'to_dict') else None

            return {
                'mode': 'autonomous' if self.is_autonomous else 'manual',
                'status': self.status,
                'robot_position': [0.0, 0.0],
                'robot_heading_deg': 0.0,
                'current_waypoint': self.current_waypoint_index,
                'total_waypoints': total_waypoints,
                'progress': round(progress, 1),
                'autonomous_speed': 0,
                'min_speed': self.min_speed,
                'max_speed': self.max_speed,
                'nearest_obstacle_cm': None,
                'obstacle_log': [],
                'path': [[int(x), int(y)] for x, y in self.current_path],
                'servo_enabled': self.servo_enabled,
                'grid': grid_dict,
                'obstacles': [],
                'hazards': [],
                'eta_seconds': None,
                'paused': False
            }

    def set_servo_enabled(self, enabled: bool):
        self.servo_enabled = bool(enabled)
        if self._controller:
            try:
                self._controller.servo_enabled = self.servo_enabled
            except Exception:
                pass
        return {'servo_enabled': self.servo_enabled}

    def set_speed_limits(self, min_speed: int, max_speed: int):
        with self.lock:
            self.min_speed = max(0, min(100, int(min_speed)))
            self.max_speed = max(0, min(100, int(max_speed)))
        if self._controller:
            try:
                self._controller.min_speed = self.min_speed
                self._controller.max_speed = self.max_speed
                self._controller._base_max_speed = self.max_speed
            except Exception:
                pass
        return {'min_speed': self.min_speed, 'max_speed': self.max_speed}

    def recenter_start(self):
        try:
            if self._controller and hasattr(self._controller, 'grid'):
                rgx, rgy = self._controller.grid.robot_grid
                self._controller.grid.set_start(rgx, rgy)
                return self._controller.grid.to_dict()
            if hasattr(self.grid, 'set_start'):
                self.grid.set_start(0, 0)
        except Exception:
            pass
        return self.grid.to_dict() if hasattr(self.grid, 'to_dict') else {}

    def resume_autonomous(self):
        with self.lock:
            if self.status == 'paused':
                self.status = 'executing'
        if self._controller:
            try:
                result = self._controller.resume()
                if isinstance(result, dict) and result.get('status'):
                    self.status = result.get('status')
                return result
            except Exception:
                pass
        return {'status': self.status}

    # -------------------------
    # Internal minimal loops
    # -------------------------
    def _sensor_loop(self):
        while self.is_executing:
            try:
                _ = self.get_sensor_data()
            except Exception:
                pass
            time.sleep(0.1)

    def _execution_loop(self):
        while self.is_executing:
            with self.lock:
                if self.current_waypoint_index >= len(self.current_path):
                    self.is_executing = False
                    self.status = 'idle'
                    break
                self.current_waypoint_index += 1
            time.sleep(0.2)
