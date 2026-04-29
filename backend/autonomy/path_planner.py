"""Simple A* path planner on a grid.
"""
import heapq
import math
from typing import List, Tuple, Optional


class PathPlanner:
    def __init__(self, grid_manager):
        self.grid = grid_manager

    def _heuristic(self, a: Tuple[int,int], b: Tuple[int,int]) -> float:
        return math.hypot(a[0]-b[0], a[1]-b[1])

    def plan(self, start: Tuple[int,int], goal: Tuple[int,int]) -> List[Tuple[int,int]]:
        # Validate
        if not (self.grid.is_valid(*start) and self.grid.is_valid(*goal)):
            return []
        if start == goal:
            return [start]

        open_heap = []
        heapq.heappush(open_heap, (0.0, start))
        came_from = {start: None}
        gscore = {start: 0.0}

        while open_heap:
            _, current = heapq.heappop(open_heap)
            if current == goal:
                # reconstruct path
                path = []
                node = current
                while node is not None:
                    path.append(node)
                    node = came_from.get(node)
                path.reverse()
                return path

            for (nx, ny), move_cost in self.grid.get_neighbors(*current):
                neighbor = (nx, ny)
                tentative_g = gscore[current] + move_cost
                if tentative_g < gscore.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    gscore[neighbor] = tentative_g
                    f = tentative_g + self._heuristic(neighbor, goal)
                    heapq.heappush(open_heap, (f, neighbor))

        # No path
        return []

    def smooth_path(self, path: List[Tuple[int,int]]) -> List[Tuple[int,int]]:
        # Simple collinearity-based reducer
        if len(path) <= 2:
            return path
        out = [path[0]]
        for i in range(1, len(path)-1):
            x0,y0 = out[-1]
            x1,y1 = path[i]
            x2,y2 = path[i+1]
            # check collinearity (vector cross product near zero)
            if (x1-x0)*(y2-y1) == (y1-y0)*(x2-x1):
                # skip intermediate point
                continue
            out.append(path[i])
        out.append(path[-1])
        return out
