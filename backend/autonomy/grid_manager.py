"""Grid manager for center-based occupancy grid (50x50 default).
"""
import threading
import time
import math
from typing import Tuple, List, Dict


class GridManager:
    FREE = 0
    OBSTACLE = 1
    START = 2
    GOAL = 3
    HAZARD = 4
    VISITED = 5

    def __init__(self, width: int = 50, height: int = 50, cell_size_cm: int = 10):
        self.width = width
        self.height = height
        self.cell_size_cm = cell_size_cm
        self.cell_size_m = float(cell_size_cm) / 100.0
        self.cx = width // 2
        self.cy = height // 2
        self.lock = threading.Lock()

        # grid[y][x]  (row-major)
        self.grid = [[self.FREE for _ in range(self.width)] for _ in range(self.height)]

        # Robot pose in world meters and cached grid cell
        self.robot_world = (0.0, 0.0)
        self.robot_grid = (self.cx, self.cy)

        self.start = None
        self.goal = None

        # optional transient obstacles with timestamps
        self._obstacle_timestamps: Dict[Tuple[int,int], float] = {}

    # -------------------- coordinate conversions --------------------
    def world_to_grid(self, x_m: float, y_m: float) -> Tuple[int, int]:
        gx = int(round(x_m / self.cell_size_m)) + self.cx
        gy = int(round(y_m / self.cell_size_m)) + self.cy
        return gx, gy

    def grid_to_world(self, gx: int, gy: int) -> Tuple[float, float]:
        x_m = (gx - self.cx) * self.cell_size_m
        y_m = (gy - self.cy) * self.cell_size_m
        return x_m, y_m

    def is_valid(self, gx: int, gy: int) -> bool:
        return 0 <= gx < self.width and 0 <= gy < self.height

    # -------------------- grid operations --------------------
    def set_obstacle(self, gx: int, gy: int):
        with self.lock:
            if self.is_valid(gx, gy):
                self.grid[gy][gx] = self.OBSTACLE
                self._obstacle_timestamps[(gx, gy)] = time.time()

    def clear_obstacle(self, gx: int, gy: int):
        """Remove obstacle at grid cell and clear its timestamp."""
        with self.lock:
            if self.is_valid(gx, gy) and self.grid[gy][gx] == self.OBSTACLE:
                self.grid[gy][gx] = self.FREE
                self._obstacle_timestamps.pop((gx, gy), None)

    def set_hazard(self, gx: int, gy: int):
        with self.lock:
            if self.is_valid(gx, gy):
                self.grid[gy][gx] = self.HAZARD

    def set_visited(self, gx: int, gy: int):
        with self.lock:
            if self.is_valid(gx, gy):
                if self.grid[gy][gx] == self.FREE:
                    self.grid[gy][gx] = self.VISITED

    def set_start(self, gx: int, gy: int):
        with self.lock:
            if self.is_valid(gx, gy):
                self.start = (gx, gy)
                self.grid[gy][gx] = self.START

    def set_goal(self, gx: int, gy: int):
        with self.lock:
            if self.is_valid(gx, gy):
                self.goal = (gx, gy)
                self.grid[gy][gx] = self.GOAL

    def clear(self):
        with self.lock:
            self.grid = [[self.FREE for _ in range(self.width)] for _ in range(self.height)]
            self._obstacle_timestamps.clear()

    def set_robot_position(self, x_m: float, y_m: float):
        with self.lock:
            self.robot_world = (float(x_m), float(y_m))
            self.robot_grid = self.world_to_grid(x_m, y_m)

    def get_neighbors(self, gx: int, gy: int) -> List[Tuple[Tuple[int,int], float]]:
        # 8-connected neighbors with cost
        neighbors = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = gx + dx
                ny = gy + dy
                if not self.is_valid(nx, ny):
                    continue
                if self.grid[ny][nx] in (self.OBSTACLE, self.HAZARD):
                    continue
                cost = math.hypot(dx, dy)
                neighbors.append(((nx, ny), cost))
        return neighbors

    def to_dict(self) -> Dict:
        with self.lock:
            start = list(self.start) if self.start is not None else None
            goal = list(self.goal) if self.goal is not None else None
            return {
                'width': self.width,
                'height': self.height,
                'cell_size_cm': self.cell_size_cm,
                'cell_size_m': self.cell_size_m,
                'robot_world': [self.robot_world[0], self.robot_world[1]],
                'robot_grid': [self.robot_grid[0], self.robot_grid[1]],
                'start': start,
                'goal': goal,
                'grid': [row[:] for row in self.grid]
            }
