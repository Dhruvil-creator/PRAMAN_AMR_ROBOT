#!/usr/bin/env python3
from backend.autonomy.grid_manager import GridManager
from backend.autonomy.path_planner import PathPlanner


def run():
    g = GridManager(20,20,10)
    cx,cy = g.cx,g.cy
    start = (cx,cy)
    goal = (cx+4,cy)
    planner = PathPlanner(g)
    p = planner.plan(start,goal)
    assert len(p) > 0, 'planner returned empty path'

    # place an obstacle directly in front and replan
    g.set_obstacle(cx+1,cy)
    p2 = planner.plan(start,goal)
    assert len(p2) > 0, 'planner failed with obstacle present'
    assert all(node != (cx+1,cy) for node in p2), 'path includes obstacle cell'

    # smoothing preserves endpoints
    s = planner.smooth_path(p2)
    assert s[0] == p2[0] and s[-1] == p2[-1]

    print('planner tests passed')


if __name__ == '__main__':
    run()
