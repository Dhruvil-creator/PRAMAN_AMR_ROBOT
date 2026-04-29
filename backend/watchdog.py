"""Motor watchdog: stops motors if motor update heartbeat is stale.

This is intentionally conservative: it only stops motors when "_last_update_time" in motor
module is older than the configured timeout and the motor appears to be driving.
"""
import threading
import time

import motor


def start_watchdog(timeout=1.0, check_interval=0.25):
    """Start a background watchdog thread.

    Returns: Thread object
    """
    def _loop():
        while True:
            try:
                last = getattr(motor, '_last_update_time', None)
                now = time.time()
                if last is not None and (now - last) > timeout:
                    m = getattr(motor, '_motor', None)
                    cur_speed = 0
                    if m is not None:
                        try:
                            cur_speed = getattr(m, 'current_speed', 0)
                        except Exception:
                            cur_speed = 0
                    # If motors appear active, stop them
                    if cur_speed and cur_speed > 0:
                        print(f"[WATCHDOG] No motor update for {now-last:.2f}s -> stopping motors")
                        try:
                            motor.stop()
                        except Exception as e:
                            print(f"[WATCHDOG] motor.stop() failed: {e}")
                time.sleep(check_interval)
            except Exception as e:
                print(f"[WATCHDOG ERROR] {e}")
                time.sleep(1.0)

    t = threading.Thread(target=_loop, daemon=True, name='MotorWatchdog')
    t.start()
    return t
