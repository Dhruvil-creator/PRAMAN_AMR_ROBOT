import time
from backend.control.pid_controller import PIDController


def test_pid_basic():
    pid = PIDController(kp=1.0, ki=0.1, kd=0.01, setpoint=10.0, output_limits=(-100,100))
    out1 = pid.compute(0.0)
    time.sleep(0.01)
    out2 = pid.compute(2.0)
    assert isinstance(out1, float)
    assert isinstance(out2, float)


if __name__ == '__main__':
    test_pid_basic()
    print('pid test passed')
