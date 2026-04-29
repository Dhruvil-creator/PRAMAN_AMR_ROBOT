"""Simple simulator skeleton for offline testing and replay.

Provides a light-weight Simulation class that can feed synthetic sensor data
or replay recorded logs to the planner/executor for offline testing.
"""
import time
import threading


class Simulator:
    def __init__(self, grid_map=None, update_interval=0.1):
        self.grid_map = grid_map
        self.update_interval = update_interval
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _loop(self):
        while self._running:
            # Placeholder: publish synthetic sensor data or replay logs
            time.sleep(self.update_interval)

    def step(self):
        # Single-step simulator (for unit tests)
        pass
