"""Event manager: handles obstacle/hazard/gas events and coordinates marking and simple actions.
"""
import threading
import time


class EventManager:
    def __init__(self, grid_manager, use_hardware=False):
        self.grid = grid_manager
        self.use_hardware = bool(use_hardware)
        try:
            if self.use_hardware:
                import motor
                self.motor = motor
            else:
                self.motor = None
        except Exception:
            self.motor = None

    def handle_obstacle(self, gx, gy):
        try:
            self.grid.set_obstacle(gx, gy)
            return True
        except Exception:
            return False

    def handle_hazard(self, gx, gy, pause_seconds: float = 1.5, servo_action: bool = True, servo_angle: int = 120):
        # Stop and drop marker (servo) if hardware available; otherwise just mark hazard
        try:
            self.grid.set_hazard(gx, gy)
            if self.motor:
                try:
                    if getattr(self.motor, 'hard_stop', None):
                        self.motor.hard_stop()
                    elif getattr(self.motor, 'stop', None):
                        self.motor.stop()
                except Exception:
                    pass
            if servo_action and self.motor and getattr(self.motor, 'pulse_servo', None):
                # run servo pulse in background (matches test_servo timing)
                threading.Thread(target=lambda: self.motor.pulse_servo(servo_angle, duration=0.2), daemon=True).start()
            time.sleep(pause_seconds)
            return True
        except Exception:
            return False

    def handle_gas(self, gx, gy):
        self.grid.set_hazard(gx, gy)
        # Additional alerting to dashboard handled elsewhere
        return True
