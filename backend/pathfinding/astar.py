"""A* pathfinding algorithm implementation."""

from typing import List, Tuple, Dict, Optional
from heapq import heappush, heappop
from .map_utils import GridMap


class Node:
    """Represents a node in the A* search space."""
    
    def __init__(self, pos: Tuple[int, int], parent: Optional['Node'] = None):
        self.pos = pos
        self.parent = parent
        self.g = 0.0  # cost from start
        self.h = 0.0  # heuristic cost to goal
        self.f = 0.0  # f = g + h
    
    def __lt__(self, other):
        """Comparison for priority queue (min heap by f value)."""
        if self.f == other.f:
            # Tie-breaker: prefer nodes with higher g (closer to start)
            return self.g > other.g
        return self.f < other.f
    
    def __eq__(self, other):
        return self.pos == other.pos
    
    def __hash__(self):
        return hash(self.pos)


class AStarPathfinder:
    """A* pathfinding algorithm for grid-based maps."""
    
    def __init__(self, grid_map: GridMap):
        """
        Initialize A* pathfinder.
        
        Args:
            grid_map: GridMap instance to search
        """
        self.grid = grid_map
        self.open_set = []
        self.closed_set = set()
        self.node_map = {}  # Track nodes by position
        self.visited_path = []  # For visualization
        self.expanded_nodes = 0
    
    def find_path(self) -> Tuple[Optional[List[Tuple[int, int]]], Dict]:
        """
        Find optimal path from start to goal using A* algorithm.
        
        Returns:
            Tuple of (path, metadata)
            - path: List of (x, y) coordinates or None if no path exists
            - metadata: Dict with statistics (nodes_expanded, path_length, visited_cells)
        """
        if not self.grid.start or not self.grid.goal:
            return None, {'error': 'Start or goal not set'}
        
        self.open_set = []
        self.closed_set = set()
        self.node_map = {}
        self.visited_path = []
        self.expanded_nodes = 0
        
        start_node = Node(self.grid.start)
        start_node.g = 0
        start_node.h = self.grid.get_distance(self.grid.start, self.grid.goal)
        start_node.f = start_node.h
        
        heappush(self.open_set, start_node)
        self.node_map[self.grid.start] = start_node
        
        while self.open_set:
            current = heappop(self.open_set)
            self.expanded_nodes += 1
            self.visited_path.append(current.pos)
            
            if current.pos == self.grid.goal:
                # Path found - reconstruct
                path = self._reconstruct_path(current)
                return path, {
                    'nodes_expanded': self.expanded_nodes,
                    'path_length': len(path),
                    'visited_cells': len(self.visited_path)
                }
            
            self.closed_set.add(current.pos)
            
            # Explore neighbors
            for neighbor_pos in self.grid.get_neighbors(current.pos[0], current.pos[1]):
                if neighbor_pos in self.closed_set:
                    continue
                
                # Calculate costs
                movement_cost = self.grid.get_movement_cost(current.pos, neighbor_pos)
                tentative_g = current.g + movement_cost
                
                # Check if neighbor already in open set
                neighbor = self.node_map.get(neighbor_pos)
                
                if neighbor is None:
                    # New node
                    neighbor = Node(neighbor_pos, parent=current)
                    neighbor.g = tentative_g
                    neighbor.h = self.grid.get_distance(neighbor_pos, self.grid.goal)
                    neighbor.f = neighbor.g + neighbor.h
                    
                    heappush(self.open_set, neighbor)
                    self.node_map[neighbor_pos] = neighbor
                
                elif tentative_g < neighbor.g:
                    # Found better path to neighbor
                    neighbor.parent = current
                    neighbor.g = tentative_g
                    neighbor.f = neighbor.g + neighbor.h
                    # Note: heapq doesn't support update, so we rely on f-value for ordering
        
        # No path found
        return None, {
            'nodes_expanded': self.expanded_nodes,
            'path_length': 0,
            'visited_cells': len(self.visited_path),
            'status': 'No path found'
        }
    
    def _reconstruct_path(self, node: Node) -> List[Tuple[int, int]]:
        """Reconstruct path from start to goal node."""
        path = []
        current = node
        while current is not None:
            path.append(current.pos)
            current = current.parent
        path.reverse()
        return path
    
    def smooth_path(self, path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        Smooth path by removing unnecessary waypoints (line-of-sight optimization).
        
        Args:
            path: Original path from A*
            
        Returns:
            Smoothed path with fewer waypoints
        """
        if len(path) <= 2:
            return path
        
        smoothed = [path[0]]
        
        for i in range(1, len(path) - 1):
            # Check if we can skip waypoint i by going directly from current to i+1
            if not self._has_line_of_sight(smoothed[-1], path[i + 1]):
                smoothed.append(path[i])
        
        smoothed.append(path[-1])
        return smoothed
    
    def _has_line_of_sight(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> bool:
        """Check if there's a clear line between two positions (Bresenham line)."""
        x1, y1 = pos1
        x2, y2 = pos2
        
        # Simple line-of-sight using Bresenham's algorithm
        points = self._bresenham_line(x1, y1, x2, y2)
        
        for x, y in points[1:-1]:  # Skip start and end
            if not self.grid.is_walkable(x, y):
                return False
        
        return True
    
    def _bresenham_line(self, x1: int, y1: int, x2: int, y2: int) -> List[Tuple[int, int]]:
        """Generate points on a line using Bresenham algorithm."""
        points = []
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        x, y = x1, y1
        while True:
            points.append((x, y))
            if x == x2 and y == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        
        return points
    
    def get_visited_cells(self) -> List[Tuple[int, int]]:
        """Return list of visited cells for visualization."""
        return self.visited_path
