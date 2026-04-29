"""
Autonomous Navigation Mode Manager
Handles real-time sensor integration, path replanning, and servo automation
Integrates DWA for smooth motion control
"""

import threading
import time
import math
from typing import List, Tuple, Optional, Dict
from backend.pathfinding import GridMap, AStarPathfinder
from backend.pathfinding.dwa import DynamicWindowApproach, VelocityController, convert_grid_to_obstacles, convert_waypoint_to_goal
import motor


class AutonomousModeManager:
    """
    Manages autonomous navigation with real-time sensor integration.
    - Auto-populates grid from ultrasonic sensors
    - Replans path when new obstacles detected
    - Triggers servo on proximity/metal detection
    """
    
    def __init__(self, grid_map: GridMap, get_sensor_data_func):
        """
        Initialize autonomous mode manager.
        
        Args:
            grid_map: GridMap instance for pathfinding
            get_sensor_data_func: Function to retrieve current sensor data
        """
        self.grid = grid_map
        self.get_sensor_data = get_sensor_data_func
        
        # Status
        self.status = 'idle'  # idle, planning, executing, paused, replanning
        self.current_waypoint_index = 0
        self.current_path = []
        self.previous_obstacles = set()
        
        # Threading
        self.execution_thread = None
        self.sensor_monitor_thread = None
        self.is_running = False
        self.lock = threading.Lock()
        
        # Configuration
        self.sensor_update_interval = 0.1  # 100ms
        self.proximity_threshold = 30  # cm (trigger replanning if obstacle < 30cm)
        self.servo_enabled_on_detection = True
        
        # DWA Motion Controller
        self.dwa = DynamicWindowApproach()
        self.velocity_controller = VelocityController(self.dwa)
        
    def start_autonomous_execution(self, path: List[Tuple[int, int]]):
        """Start executing a planned path with real-time sensor monitoring."""
        with self.lock:
            if self.is_running:
                return {'error': 'Already executing'}
            
            self.current_path = path
            self.current_waypoint_index = 0
            self.status = 'executing'
            self.is_running = True
        
        # Start sensor monitoring thread
        self.sensor_monitor_thread = threading.Thread(
            target=self._sensor_monitor_loop,
            daemon=True
        )
        self.sensor_monitor_thread.start()
        
        # Start execution thread
        self.execution_thread = threading.Thread(
            target=self._execution_loop,
            daemon=True
        )
        self.execution_thread.start()
        
        return {
            'status': 'executing',
            'path_length': len(path),
            'first_waypoint': path[0] if path else None
        }
    
    def stop_autonomous_execution(self):
        """Stop autonomous execution."""
        with self.lock:
            self.is_running = False
            self.status = 'idle'
        
        # Stop motor
        motor.stop()
        
        return {'status': 'stopped'}
    
    def _sensor_monitor_loop(self):
        """Monitor sensors and update grid in real-time."""
        while self.is_running:
            try:
                sensor_data = self.get_sensor_data()
                
                # Extract ultrasonic data
                ultrasonic = sensor_data.get('ultrasonic', {})
                center = ultrasonic.get('center', 999)
                left = ultrasonic.get('left', 999)
                right = ultrasonic.get('right', 999)
                
                # Get metal detection
                metal_detected = sensor_data.get('metal_detector', {}).get('detected', False)
                
                # Update grid with obstacles from ultrasonic
                self._update_grid_from_sensors(center, left, right)
                
                # Check for metal detection during execution
                if metal_detected and self._should_trigger_servo():
                    self._trigger_servo_on_detection()
                
                # Check proximity threshold
                if self._check_proximity_threshold(center, left, right):
                    # Trigger replanning
                    self._request_replan()
                
                time.sleep(self.sensor_update_interval)
            
            except Exception as e:
                print(f"✗ SENSOR MONITOR ERROR: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(self.sensor_update_interval)
    
    def _execution_loop(self):
        """Execute path waypoints with velocity control."""
        while self.is_running:
            try:
                current_waypoint = None
                
                # Atomic check and get waypoint
                with self.lock:
                    if self.status == 'replanning' or not self.current_path:
                        time.sleep(0.1)
                        continue
                    
                    if self.current_waypoint_index >= len(self.current_path):
                        # Path complete
                        self.status = 'idle'
                        motor.stop()
                        self.is_running = False
                        break
                    
                    current_waypoint = self.current_path[self.current_waypoint_index]
                
                # Move toward waypoint (released lock during execution)
                if current_waypoint:
                    self._move_toward_waypoint(current_waypoint)
                    
                    # Check if waypoint reached (with lock for state check)
                    if self._is_waypoint_reached(current_waypoint):
                        with self.lock:
                            self.current_waypoint_index += 1
                            print(f"✓ Waypoint {self.current_waypoint_index - 1} reached, moving to next")
                
                time.sleep(0.05)
            
            except Exception as e:
                print(f"✗ EXECUTION LOOP ERROR: {e}")
                import traceback
                traceback.print_exc()
                with self.lock:
                    self.status = 'error'
                motor.stop()
                time.sleep(0.1)
    
    def _update_grid_from_sensors(self, center_dist: float, left_dist: float, right_dist: float):
        """
        Update grid obstacles based on ultrasonic sensor readings.
        
        Maps sensor distances to grid cells and marks as obstacles.
        Uses robot's estimated position to place obstacles correctly.
        """
        # Cell size in cm (assuming 10cm per cell)
        cell_size_cm = 10
        
        current_obstacles = set()
        
        # Center sensor: updates forward obstacle
        if center_dist < 999 and center_dist < self.proximity_threshold:
            # Mark obstacles in front
            grid_dist = int(center_dist / cell_size_cm)
            for i in range(1, min(grid_dist + 1, 5)):
                # Assuming robot at grid center, moving forward
                obstacle_cell = (10, 7 - i)  # Adjust based on actual robot position
                if self.grid._valid_coords(obstacle_cell[0], obstacle_cell[1]):
                    current_obstacles.add(obstacle_cell)
                    self.grid.set_obstacle(*obstacle_cell, value=True)
        
        # Left sensor: updates left-side obstacles
        if left_dist < 999 and left_dist < self.proximity_threshold:
            grid_dist = int(left_dist / cell_size_cm)
            for i in range(1, min(grid_dist + 1, 5)):
                obstacle_cell = (10 - i, 7)  # Left of robot
                if self.grid._valid_coords(obstacle_cell[0], obstacle_cell[1]):
                    current_obstacles.add(obstacle_cell)
                    self.grid.set_obstacle(*obstacle_cell, value=True)
        
        # Right sensor: updates right-side obstacles
        if right_dist < 999 and right_dist < self.proximity_threshold:
            grid_dist = int(right_dist / cell_size_cm)
            for i in range(1, min(grid_dist + 1, 5)):
                obstacle_cell = (10 + i, 7)  # Right of robot
                if self.grid._valid_coords(obstacle_cell[0], obstacle_cell[1]):
                    current_obstacles.add(obstacle_cell)
                    self.grid.set_obstacle(*obstacle_cell, value=True)
        
        # Clear obstacles that are no longer detected
        for old_obstacle in self.previous_obstacles - current_obstacles:
            self.grid.set_obstacle(*old_obstacle, value=False)
        
        self.previous_obstacles = current_obstacles
    
    def _check_proximity_threshold(self, center_dist: float, left_dist: float, right_dist: float) -> bool:
        """Check if any sensor detects object closer than threshold."""
        return (
            (center_dist < 999 and center_dist < self.proximity_threshold) or
            (left_dist < 999 and left_dist < self.proximity_threshold) or
            (right_dist < 999 and right_dist < self.proximity_threshold)
        )
    
    def _request_replan(self):
        """Request path replanning due to new obstacles."""
        with self.lock:
            if self.status != 'replanning' and self.current_path:
                self.status = 'replanning'
        
        # Trigger replanning (outside lock)
        self._replan_path()
    
    def _replan_path(self):
        """Recalculate path from current position to goal."""
        try:
            with self.lock:
                if not self.grid.goal:
                    self.status = 'idle'
                    return
                
                # Set current waypoint as temporary start
                current_waypoint = self.current_path[self.current_waypoint_index] \
                    if self.current_waypoint_index < len(self.current_path) \
                    else self.grid.start
            
            # Temporarily update start to current position
            old_start = self.grid.start
            self.grid.set_start(current_waypoint[0], current_waypoint[1])
            
            # Replan path
            pathfinder = AStarPathfinder(self.grid)
            new_path, stats = pathfinder.find_path()
            
            # Update path with lock
            with self.lock:
                if new_path:
                    # Smooth the path
                    self.current_path = pathfinder.smooth_path(new_path)
                    self.current_waypoint_index = 0
                    self.status = 'executing'
                    print(f"✓ Path replanned: {len(self.current_path)} waypoints")
                else:
                    # No path found - stop
                    self.status = 'idle'
                    motor.stop()
                    print("⚠️ No viable path found, stopping autonomous mode")
            
            # Restore original start
            self.grid.set_start(old_start[0], old_start[1])
        
        except Exception as e:
            print(f"✗ Replanning error: {e}")
            import traceback
            traceback.print_exc()
            with self.lock:
                self.status = 'idle'
    
    def _move_toward_waypoint(self, waypoint: Tuple[int, int]):
        """Use DWA to command motor toward waypoint with smooth velocity control."""
        try:
            # Convert waypoint (grid coordinates) to goal (real-world coordinates)
            goal = convert_waypoint_to_goal(waypoint, cell_size=0.1)
            
            # Get current obstacles from grid
            grid_obstacles = list(self.previous_obstacles)
            real_obstacles = convert_grid_to_obstacles(grid_obstacles, cell_size=0.1)
            
            # Calculate optimal velocity command via DWA
            motor_command = self.velocity_controller.get_motor_command(goal, real_obstacles)
            
            # Apply to motors
            left_speed = motor_command['left_speed']
            right_speed = motor_command['right_speed']
            
            # Set motor speeds (percentage: -100 to 100)
            motor.set_motor_speed(left_speed, right_speed)
            
            # Update odometry
            linear_vel = motor_command['linear_vel']
            angular_vel = motor_command['angular_vel']
            self.dwa.odometry.update(linear_vel, angular_vel, dt=0.05)
            
        except Exception as e:
            print(f"✗ DWA MOVEMENT ERROR: {e}")
            import traceback
            traceback.print_exc()
            motor.stop()
    
    def _is_waypoint_reached(self, waypoint: Tuple[int, int]) -> bool:
        """Check if current position reached waypoint using odometry."""
        try:
            # Get current position from odometry
            x, y, _ = self.dwa.odometry.get_position()
            
            # Convert waypoint to real-world coordinates
            goal_x, goal_y = convert_waypoint_to_goal(waypoint, cell_size=0.1)
            
            # Check if within tolerance
            distance = math.sqrt((x - goal_x)**2 + (y - goal_y)**2)
            reached = distance < 0.15  # 15cm tolerance
            
            return reached
        except Exception as e:
            print(f"⚠️ Waypoint check error: {e}")
            return False
    
    def _should_trigger_servo(self) -> bool:
        """Check if servo should trigger on metal detection."""
        with self.lock:
            return self.servo_enabled_on_detection and self.status == 'executing'
    
    def _trigger_servo_on_detection(self):
        """Trigger servo sequence (75° → 120° → 75°) on detection."""
        try:
            print("🔔 Servo triggered on detection")
            # Non-blocking servo trigger
            threading.Thread(
                target=lambda: motor.pulse_servo(120, duration=0.2),
                daemon=True
            ).start()
        except Exception as e:
            print(f"⚠️ Servo trigger error: {e}")
    
    def get_status(self) -> Dict:
        """Get current autonomous mode status."""
        with self.lock:
            return {
                'status': self.status,
                'current_waypoint': self.current_waypoint_index,
                'total_waypoints': len(self.current_path),
                'progress': (self.current_waypoint_index / len(self.current_path) * 100) 
                           if self.current_path else 0,
                'path': self.current_path,
                'obstacles': list(self.previous_obstacles),
                'mode': 'autonomous' if self.is_running or self.status != 'idle' else 'manual'
            }
    
    def set_servo_on_detection(self, enabled: bool):
        """Enable/disable servo triggering on detection."""
        self.servo_enabled_on_detection = enabled
        return {'servo_on_detection': enabled}
