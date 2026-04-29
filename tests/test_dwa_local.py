from importlib import util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "backend" / "pathfinding" / "dwa.py"
_spec = util.spec_from_file_location("dwa", _MODULE_PATH)
_dwa = util.module_from_spec(_spec)
_spec.loader.exec_module(_dwa)
DynamicWindowApproach = _dwa.DynamicWindowApproach


def test_dwa_command_basic():
    dwa = DynamicWindowApproach()
    dwa.odometry.set_position(0.0, 0.0, 0.0)
    goal = (1.0, 0.0)
    obstacles = [(0.5, 0.5)]
    v, w = dwa.calculate_velocity_command(goal, obstacles)
    assert isinstance(v, float)
    assert isinstance(w, float)
    assert dwa.config.MIN_LINEAR_VELOCITY <= v <= dwa.config.MAX_LINEAR_VELOCITY
    assert abs(w) <= dwa.config.MAX_ANGULAR_VELOCITY
