"""
Dynamic Window Approach (DWA) - Local Path Planner & Motion Controller
For smooth trajectory generation and real-time obstacle avoidance
"""

import math
import threading
from typing import Tuple, List, Dict, Optional
from collections import deque


class DWAConfig:
    """Configuration parameters for DWA controller"""
    
    # Robot constraints
    MAX_LINEAR_VELOCITY = 0.5      # m/s (safe for mine detection)
    MIN_LINEAR_VELOCITY = 0.0       # m/s
    MAX_ANGULAR_VELOCITY = 1.0      # rad/s (57.3 deg/s)
    
    # Acceleration constraints
    MAX_LINEAR_ACCELERATION = 0.2   # m/s² (smooth acceleration)
    MAX_ANGULAR_ACCELERATION = 0.5  # rad/s²
    
    # DWA parameters
    PREDICT_TIME = 0.5              # seconds (predict 0.5s ahead)
    DT = 0.1                        # time step (100ms)
    VELOCITY_RESOLUTION = 0.05      # m/s (resolution of velocity sampling)
    YAW_RESOLUTION = 0.1            # rad (resolution of angular velocity)
    
    # Scoring weights
    HEADING_WEIGHT = 1.0            # Weight for heading to goal
    DISTANCE_WEIGHT = 2.0           # Weight for distance to obstacle
    VELOCITY_WEIGHT = 0.5           # Weight for velocity magnitude
    
    # Safety constraints
    OBSTACLE_THRESHOLD = 0.3        # m (collision detection distance)
    GOAL_THRESHOLD = 0.1            # m (goal reached tolerance)
    COLLISION_CHECK_RESOLUTION = 0.05  # m (resolution for collision checking)


class SimpleOdometry:
    """Simple odometry tracker - placeholder for real IMU/encoder integration"""
    
    def __init__(self, start_x: float = 0.0, start_y: float = 0.0, start_yaw: float = 0.0):
        self.x = start_x
        self.y = start_y
        self.yaw = start_yaw  # radians
        self.lock = threading.Lock()
    
    def update(self, linear_vel: float, angular_vel: float, dt: float = 0.1):
        """Update position based on velocity commands (wheel odometry)"""
        with self.lock:
            # Simple kinematic model
            if abs(angular_vel) > 0.01:  # Turning
                radius = linear_vel / angular_vel
                delta_yaw = angular_vel * dt
                delta_x = radius * (math.sin(self.yaw + delta_yaw) - math.sin(self.yaw))
                delta_y = radius * (math.cos(self.yaw) - math.cos(self.yaw + delta_yaw))
                self.yaw += delta_yaw
            else:  # Straight line
                delta_x = linear_vel * math.cos(self.yaw) * dt
                delta_y = linear_vel * math.sin(self.yaw) * dt
            
            self.x += delta_x
            self.y += delta_y
    
    def get_position(self) -> Tuple[float, float, float]:
        """Get current position (x, y, yaw)"""
        with self.lock:
            return (self.x, self.y, self.yaw)
    
    def set_position(self, x: float, y: float, yaw: float = 0.0):
        """Set position (useful for re-localization)"""
        with self.lock:
            self.x = x
            self.y = y
            self.yaw = yaw


class DynamicWindowApproach:
    """
    DWA Local Motion Planner
    Generates optimal (linear_velocity, angular_velocity) for smooth obstacle avoidance
    """
    
    def __init__(self, config: DWAConfig = None):
        self.config = config or DWAConfig()
        self.odometry = SimpleOdometry()
        self.current_linear_vel = 0.0
        self.current_angular_vel = 0.0
        self.lock = threading.Lock()
    
    def calculate_dynamic_window(self) -> Tuple[float, float, float, float]:
        """
        Calculate the dynamic window - reachable velocities
        Returns: (v_min, v_max, w_min, w_max)
        """
        v_min = max(self.config.MIN_LINEAR_VELOCITY,
                   self.current_linear_vel - self.config.MAX_LINEAR_ACCELERATION * self.config.DT)
        v_max = min(self.config.MAX_LINEAR_VELOCITY,
                   self.current_linear_vel + self.config.MAX_LINEAR_ACCELERATION * self.config.DT)
        
        w_min = max(-self.config.MAX_ANGULAR_VELOCITY,
                   self.current_angular_vel - self.config.MAX_ANGULAR_ACCELERATION * self.config.DT)
        w_max = min(self.config.MAX_ANGULAR_VELOCITY,
                   self.current_angular_vel + self.config.MAX_ANGULAR_ACCELERATION * self.config.DT)
        
        return (v_min, v_max, w_min, w_max)
    
    def predict_trajectory(self, v: float, w: float) -> List[Tuple[float, float]]:
        """
        Simulate trajectory for given velocity pair
        Returns list of (x, y) points along predicted path
        """
        trajectory = []
        x, y, yaw = self.odometry.get_position()
        
        for _ in range(int(self.config.PREDICT_TIME / self.config.DT)):
            trajectory.append((x, y))
            
            # Kinematic update
            if abs(w) > 0.01:
                radius = v / w
                delta_yaw = w * self.config.DT
                delta_x = radius * (math.sin(yaw + delta_yaw) - math.sin(yaw))
                delta_y = radius * (math.cos(yaw) - math.cos(yaw + delta_yaw))
                yaw += delta_yaw
            else:
                delta_x = v * math.cos(yaw) * self.config.DT
                delta_y = v * math.sin(yaw) * self.config.DT
            
            x += delta_x
            y += delta_y
        
        return trajectory
    
    def check_collision(self, trajectory: List[Tuple[float, float]], 
                       obstacles: List[Tuple[float, float]]) -> bool:
        """
        Check if trajectory collides with any obstacles
        Returns True if collision detected
        """
        if not obstacles:
            return False
        
        for tx, ty in trajectory:
            for ox, oy in obstacles:
                distance = math.sqrt((tx - ox)**2 + (ty - oy)**2)
                if distance < self.config.OBSTACLE_THRESHOLD:
                    return True
        
        return False
    
    def heading_cost(self, trajectory: List[Tuple[float, float]], 
                    goal: Tuple[float, float]) -> float:
        """
        Cost function for heading toward goal
        Lower is better. Returns angle error (0-pi)
        """
        if not trajectory:
            return math.pi
        
        final_x, final_y = trajectory[-1]
        x, y, yaw = self.odometry.get_position()
        
        # Angle to goal from final position
        goal_angle = math.atan2(goal[1] - final_y, goal[0] - final_x)
        angle_error = abs(goal_angle - yaw)
        
        # Normalize to [0, pi]
        if angle_error > math.pi:
            angle_error = 2 * math.pi - angle_error
        
        return angle_error
    
    def distance_cost(self, trajectory: List[Tuple[float, float]],
                     obstacles: List[Tuple[float, float]]) -> float:
        """
        Cost function for distance to nearest obstacle
        Encourages keeping distance from obstacles
        Returns: minimum distance to any obstacle
        """
        if not obstacles or not trajectory:
            return 100.0  # Large value if no obstacles
        
        min_distance = 100.0
        for tx, ty in trajectory:
            for ox, oy in obstacles:
                distance = math.sqrt((tx - ox)**2 + (ty - oy)**2)
                min_distance = min(min_distance, distance)
        
        return min_distance
    
    def velocity_cost(self, v: float) -> float:
        """
        Cost function preferring higher velocities (faster travel)
        Lower is better. Encourages max safe speed.
        """
        return self.config.MAX_LINEAR_VELOCITY - v
    
    def evaluate_trajectory(self, v: float, w: float, 
                           goal: Tuple[float, float],
                           obstacles: List[Tuple[float, float]]) -> Tuple[float, bool]:
        """
        Score a velocity pair based on trajectory
        Returns: (score, is_safe) - lower score is better
        """
        trajectory = self.predict_trajectory(v, w)
        
        # Check collision first
        if self.check_collision(trajectory, obstacles):
            return (float('inf'), False)
        
        # Calculate cost components
        heading = self.heading_cost(trajectory, goal)
        distance = self.distance_cost(trajectory, obstacles)
        velocity = self.velocity_cost(v)
        
        # Weighted sum
        score = (self.config.HEADING_WEIGHT * heading +
                self.config.DISTANCE_WEIGHT * distance +
                self.config.VELOCITY_WEIGHT * velocity)
        
        return (score, True)
    
    def calculate_velocity_command(self, goal: Tuple[float, float],
                                  obstacles: List[Tuple[float, float]]) -> Tuple[float, float]:
        """
        Calculate optimal (linear_velocity, angular_velocity) command
        Uses DWA to find best velocity pair
        
        Args:
            goal: Target position (x, y)
            obstacles: List of obstacle positions (x, y)
        
        Returns:
            (linear_velocity, angular_velocity)
        """
        v_min, v_max, w_min, w_max = self.calculate_dynamic_window()
        
        best_score = float('inf')
        best_v = 0.0
        best_w = 0.0
        
        # Sample velocity space
        v = v_min
        while v <= v_max:
            w = w_min
            while w <= w_max:
                score, is_safe = self.evaluate_trajectory(v, w, goal, obstacles)
                
                if is_safe and score < best_score:
                    best_score = score
                    best_v = v
                    best_w = w
                
                w += self.config.YAW_RESOLUTION
            v += self.config.VELOCITY_RESOLUTION
        
        # If no safe trajectory found, stop
        if not math.isfinite(best_score):
            best_v = 0.0
            best_w = 0.0
        
        with self.lock:
            self.current_linear_vel = best_v
            self.current_angular_vel = best_w
        
        return (best_v, best_w)
    
    def get_state(self) -> Dict:
        """Get current DWA state"""
        x, y, yaw = self.odometry.get_position()
        with self.lock:
            return {
                'position': {'x': x, 'y': y, 'yaw': yaw},
                'velocity': {'linear': self.current_linear_vel, 'angular': self.current_angular_vel},
                'timestamp': threading.current_thread().ident
            }


class VelocityController:
    """
    High-level velocity controller that converts motor commands to smooth velocity profiles
    Bridges DWA output with actual motor control
    """
    
    def __init__(self, dwa: Optional[DynamicWindowApproach] = None):
        self.dwa = dwa or DynamicWindowApproach()
        self.target_linear_vel = 0.0
        self.target_angular_vel = 0.0
        self.lock = threading.Lock()
    
    def set_target_velocity(self, linear_vel: float, angular_vel: float):
        """Set target velocity (for manual control compatibility)"""
        with self.lock:
            self.target_linear_vel = max(-self.dwa.config.MAX_LINEAR_VELOCITY,
                                        min(self.dwa.config.MAX_LINEAR_VELOCITY, linear_vel))
            self.target_angular_vel = max(-self.dwa.config.MAX_ANGULAR_VELOCITY,
                                         min(self.dwa.config.MAX_ANGULAR_VELOCITY, angular_vel))
    
    def motor_command_from_velocity(self, linear_vel: float, 
                                   angular_vel: float) -> Dict[str, float]:
        """
        Convert velocity commands to motor control signals
        
        Assumes differential drive:
        - left_motor = linear_vel - angular_vel * (wheelbase/2)
        - right_motor = linear_vel + angular_vel * (wheelbase/2)
        
        Returns: {left_speed: -100..100, right_speed: -100..100}
        """
        wheelbase = 0.15  # meters (distance between wheels)
        
        left_speed = linear_vel - angular_vel * (wheelbase / 2)
        right_speed = linear_vel + angular_vel * (wheelbase / 2)
        
        # Normalize to motor range (-100 to 100)
        max_speed = max(abs(left_speed), abs(right_speed), self.dwa.config.MAX_LINEAR_VELOCITY)
        if max_speed > 0:
            left_speed = (left_speed / max_speed) * 100
            right_speed = (right_speed / max_speed) * 100
        
        return {
            'left_speed': left_speed,
            'right_speed': right_speed,
            'linear_vel': linear_vel,
            'angular_vel': angular_vel
        }
    
    def get_motor_command(self, goal: Tuple[float, float],
                         obstacles: List[Tuple[float, float]]) -> Dict[str, float]:
        """
        Get motor command from DWA calculation
        Returns motor control signals ready for execution
        """
        linear_vel, angular_vel = self.dwa.calculate_velocity_command(goal, obstacles)
        return self.motor_command_from_velocity(linear_vel, angular_vel)


def convert_grid_to_obstacles(grid_obstacles: List[Tuple[int, int]], 
                             cell_size: float = 0.1) -> List[Tuple[float, float]]:
    """
    Convert grid cell coordinates to real-world coordinates
    
    Args:
        grid_obstacles: List of (grid_x, grid_y) cell positions
        cell_size: Physical size of each grid cell in meters
    
    Returns:
        List of (real_x, real_y) positions in meters
    """
    real_obstacles = []
    for gx, gy in grid_obstacles:
        real_x = gx * cell_size
        real_y = gy * cell_size
        real_obstacles.append((real_x, real_y))
    return real_obstacles


def convert_waypoint_to_goal(waypoint: Tuple[int, int], 
                            cell_size: float = 0.1) -> Tuple[float, float]:
    """
    Convert grid waypoint to real-world goal position
    
    Args:
        waypoint: (grid_x, grid_y) position
        cell_size: Physical size of each grid cell in meters
    
    Returns:
        (real_x, real_y) in meters
    """
    return (waypoint[0] * cell_size, waypoint[1] * cell_size)
