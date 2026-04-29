"""Grid map representation and utilities for A* pathfinding."""

from typing import Tuple, List, Dict
import numpy as np


class GridMap:
    """
    Represents a 2D occupancy grid for path planning.
    
    Cell states:
    - 0: Free/navigable
    - 1: Obstacle/wall
    - 2: Start position
    - 3: Goal position
    - 4: Hazard (non-blocking, visual marker)
    - 5: Visited (visual, non-blocking)
    """
    
    def __init__(self, width: int = 20, height: int = 15):
        """Initialize grid map.
        
        Args:
            width: Grid width in cells (default 20)
            height: Grid height in cells (default 15)
        """
        self.width = width
        self.height = height
        self.grid = np.zeros((height, width), dtype=np.uint8)
        self.start = None
        self.goal = None
    
    def set_start(self, x: int, y: int):
        """Set start position."""
        if self._valid_coords(x, y):
            if self.start:
                self.grid[self.start[1], self.start[0]] = 0
            self.start = (x, y)
            self.grid[y, x] = 2
            return True
        return False
    
    def set_goal(self, x: int, y: int):
        """Set goal position."""
        if self._valid_coords(x, y):
            if self.goal:
                self.grid[self.goal[1], self.goal[0]] = 0
            self.goal = (x, y)
            self.grid[y, x] = 3
            return True
        return False
    
    def set_obstacle(self, x: int, y: int, value: bool = True):
        """Set obstacle at position."""
        if self._valid_coords(x, y):
            if value:
                self.grid[y, x] = 1
            elif self.grid[y, x] == 1:
                self.grid[y, x] = 0
            return True
        return False

    def set_hazard(self, x: int, y: int):
        """Mark a hazard at position (visual marker, not blocking).

        Uses cell value 4 for hazard so it remains walkable but visible in the UI.
        Avoids overwriting start (2) or goal (3).
        """
        if self._valid_coords(x, y):
            if self.grid[y, x] not in (2, 3):
                self.grid[y, x] = 4
            return True
        return False

    def set_visited(self, x: int, y: int):
        """Mark a cell as visited (visual) using value 5. Does not overwrite obstacles, start, goal, or hazards."""
        if self._valid_coords(x, y):
            # Only mark free cells (0) as visited; do not overwrite obstacles/hazards/start/goal
            if self.grid[y, x] == 0:
                self.grid[y, x] = 5
            return True
        return False
    
    def is_walkable(self, x: int, y: int) -> bool:
        """Check if cell is walkable (not obstacle, within bounds)."""
        if not self._valid_coords(x, y):
            return False
        return self.grid[y, x] != 1
    
    def get_neighbors(self, x: int, y: int) -> List[Tuple[int, int]]:
        """Get 8-directional neighbors (4-connected if no diagonal through walls)."""
        neighbors = []
        # 8-directional: up, down, left, right, diagonals
        directions = [
            (0, -1), (0, 1), (-1, 0), (1, 0),      # orthogonal
            (-1, -1), (1, -1), (-1, 1), (1, 1)     # diagonal
        ]
        
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if self.is_walkable(nx, ny):
                neighbors.append((nx, ny))
        
        return neighbors
    
    def get_distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Calculate Euclidean distance between two positions."""
        x1, y1 = pos1
        x2, y2 = pos2
        # For 8-directional movement, use Euclidean distance
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    
    def get_movement_cost(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Get cost to move from pos1 to pos2. Hazards add a penalty but remain walkable."""
        x1, y1 = pos1
        x2, y2 = pos2
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        # Base movement cost (diagonal vs straight)
        if dx == 1 and dy == 1:
            base = 1.414
        else:
            base = 1.0

        # Add penalty for hazard cells to prefer avoiding them when possible
        penalty = 0.0
        try:
            cell_val = int(self.grid[y2, x2])
            if cell_val == 4:
                penalty += 5.0
        except Exception:
            pass

        return base + penalty
    
    def clear(self):
        """Reset grid to empty state."""
        self.grid = np.zeros((self.height, self.width), dtype=np.uint8)
        self.start = None
        self.goal = None
    
    def get_grid_copy(self) -> np.ndarray:
        """Get a copy of the current grid state."""
        return self.grid.copy()
    
    def to_dict(self) -> Dict:
        """Convert grid to dictionary for JSON serialization."""
        return {
            'width': self.width,
            'height': self.height,
            'grid': self.grid.tolist(),
            'start': self.start,
            'goal': self.goal
        }
    
    def _valid_coords(self, x: int, y: int) -> bool:
        """Check if coordinates are within bounds."""
        return 0 <= x < self.width and 0 <= y < self.height
