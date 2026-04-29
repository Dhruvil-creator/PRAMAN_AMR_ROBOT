from backend.autonomy.controller import AutonomousController


def test_controller_plan_and_pid_update():
    controller = AutonomousController(use_hardware=False)
    gx, gy = controller.grid.robot_grid
    controller.set_goal_grid(gx + 3, gy)
    path = controller.plan_path()
    assert isinstance(path, list)
    assert len(path) >= 1

    controller.set_heading_pid(1.2, 0.1, 0.02)
    assert controller.motion.heading_pid.kp == 1.2
    assert controller.motion.heading_pid.ki == 0.1
    assert controller.motion.heading_pid.kd == 0.02

    status = controller.get_status()
    assert 'power' in status
    assert 'event_log' in status
