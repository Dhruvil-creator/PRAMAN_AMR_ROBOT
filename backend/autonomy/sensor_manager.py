"""SensorManager: non-blocking sensor snapshot provider.

Tries to use backend.data_model.get_system_data() if available, otherwise falls back to direct sensor calls.
"""
import threading
import time
from typing import Dict, Any


class SensorManager:
    def __init__(self, poll_interval: float = 0.1, get_system_data_func=None):
        self.poll_interval = poll_interval
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._latest: Dict[str, Any] = {}

        if get_system_data_func:
            self._get_fn = get_system_data_func
        else:
            try:
                from backend.data_model import get_system_data
                self._get_fn = get_system_data
            except Exception:
                # Fallback: import sensor modules lazily
                self._get_fn = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name='SensorManager')
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _loop(self):
        while self._running:
            try:
                if self._get_fn:
                    data = self._get_fn()
                else:
                    # naive fallback: try to import sensors directly
                    data = {}
                    try:
                        from backend.sensors import ultrasonic
                        data['ultrasonic'] = ultrasonic.read_all()
                    except Exception:
                        data['ultrasonic'] = {'left': None, 'center': None, 'right': None}
                    try:
                        from backend.sensors import metal
                        data['metal'] = metal.get_hazard()
                    except Exception:
                        data['metal'] = {'detected': False}
                    try:
                        from backend.sensors import pir
                        data['pir'] = pir.get_motion()
                    except Exception:
                        data['pir'] = {'detected': False}
                with self._lock:
                    self._latest = data
            except Exception as e:
                # swallow exceptions to keep sensor loop alive
                print(f"[SensorManager] read failed: {e}")
            time.sleep(self.poll_interval)

    def get_snapshot(self):
        with self._lock:
            return dict(self._latest)
