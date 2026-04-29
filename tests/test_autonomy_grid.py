#!/usr/bin/env python3
from backend.autonomy.grid_manager import GridManager


def run():
    g = GridManager(50,50,10)
    cx,cy = g.cx,g.cy
    gx,gy = g.world_to_grid(0.0,0.0)
    assert (gx,gy) == (cx,cy), f'origin mismatch {(gx,gy)} != {(cx,cy)}'
    x_m,y_m = g.grid_to_world(cx,cy)
    assert abs(x_m) < 1e-6 and abs(y_m) < 1e-6

    # set obstacle one cell forward
    gx2,gy2 = g.world_to_grid(g.cell_size_m, 0.0)
    g.set_obstacle(gx2,gy2)
    assert g.grid[gy2][gx2] == g.OBSTACLE

    # neighbors should not include the obstacle
    neighbors = [n for n,_ in g.get_neighbors(cx,cy)]
    assert (gx2,gy2) not in neighbors, 'obstacle present in neighbors'

    print('grid tests passed')


if __name__ == '__main__':
    run()
