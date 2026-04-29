"""
SensorHub
Background sensor fusion thread that reads individual sensor modules at a fixed interval,
applies light smoothing/hysteresis, and exposes a snapshot/payload for use by the
autonomy manager and the /sensor-data endpoint.

This is intentionally defensive: imports are optional and failures are tolerated.
"""

import threading
import time
import copy

# Optional imports for sensors (handled gracefully)
try:
    from backend.sensors import ultrasonic as _ultrasonic
except Exception:
    _ultrasonic = None

try:
    from backend.sensors import mq as _mq
except Exception:
    _mq = None

try:
    from backend.sensors import pir as _pir
except Exception:
    _pir = None

try:
    from backend.sensors import metal as _metal
except Exception:
    _metal = None

try:
    from backend.sensors import imu_wrapper as _imu
except Exception:
    _imu = None


class SensorHub:
    def __init__(self, update_interval: float = 0.1):
        self.update_interval = float(update_interval)

        # Smoothing factors (0..1). Higher = more inertia (less noisy)
        self.ultrasonic_alpha = 0.6
        self.gas_alpha = 0.6

        # Internal snapshot
        self._snapshot = {
            "timestamp": time.time(),
            "gas": {
                "mq2": {"raw": 0, "rs": 0, "ppm": 0},
                "mq135": {"raw": 0, "rs": 0, "ppm": 0}
            },
            "ultrasonic": {"center": 400.0, "left": 400.0, "right": 400.0},
            "ultrasonic_raw": {"center": 400.0, "left": 400.0, "right": 400.0},
            "pir": {"detected": False, "alert": False},
            "metal": {"detected": False},
            "imu": {"gyro_z": 0},
            "system": self._get_system_metrics()
        }

        self._lock = threading.Lock()
        self._thread = None
        self._running = False

    # Public control
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SensorHub")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def is_running(self) -> bool:
        return self._running

    # Snapshot API
    def get_snapshot(self):
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def get_payload(self):
        """Return a payload compatible with backend.data_model.build_payload.
        The payload includes gas, ultrasonic, pir, metal, imu and system metrics.
        """
        return self.get_snapshot()

    # Internal loop
    def _loop(self):
        while self._running:
            now = time.time()
            results = {}

            # Read sensors in parallel to minimize blocking
            def _read_ultrasonic():
                try:
                    if _ultrasonic:
                        raw = _ultrasonic.get_distance()
                        results['ultrasonic_raw'] = raw
                        results['ultrasonic'] = raw
                    else:
                        results['ultrasonic'] = {"center": 999, "left": 999, "right": 999}
                        results['ultrasonic_raw'] = results['ultrasonic']
                except Exception:
                    results['ultrasonic'] = {"center": 999, "left": 999, "right": 999}
                    results['ultrasonic_raw'] = results['ultrasonic']

            def _read_gas():
                try:
                    if _mq:
                        results['gas'] = _mq.read_all()
                    else:
                        results['gas'] = {
                            "mq2": {"raw": 0, "rs": 0, "ppm": 0},
                            "mq135": {"raw": 0, "rs": 0, "ppm": 0}
                        }
                except Exception:
                    results['gas'] = {
                        "mq2": {"raw": 0, "rs": 0, "ppm": 0},
                        "mq135": {"raw": 0, "rs": 0, "ppm": 0}
                    }

            def _read_pir():
                try:
                    results['pir'] = _pir.get_motion() if _pir else {"detected": False}
                except Exception:
                    results['pir'] = {"detected": False}

            def _read_metal():
                try:
                    results['metal'] = _metal.get_hazard() if _metal else {"detected": False}
                except Exception:
                    results['metal'] = {"detected": False}

            def _read_imu():
                try:
                    results['imu'] = _imu.get_imu_data() if _imu else {"gyro_z": 0}
                except Exception:
                    results['imu'] = {"gyro_z": 0}

            threads = []
            for fn in (_read_ultrasonic, _read_gas, _read_pir, _read_metal, _read_imu):
                t = threading.Thread(target=fn)
                t.start()
                threads.append(t)

            # Wait for sensor reads (increase timeout so ultrasonic readings can complete when no echo)
            # Ultrasonic stable_read may take several hundred ms in worst-case (no echo); use up to 1.2s timeout
            for t in threads:
                t.join(timeout=1.2)

            # Apply smoothing and update snapshot
            with self._lock:
                u = results.get('ultrasonic', {"center": 999, "left": 999, "right": 999})
                u_raw = results.get('ultrasonic_raw', u)
                self._snapshot["ultrasonic_raw"] = {
                    "center": float(u_raw.get("center", 999.0)),
                    "left": float(u_raw.get("left", 999.0)),
                    "right": float(u_raw.get("right", 999.0))
                }
                for k in ("center", "left", "right"):
                    prev = float(self._snapshot["ultrasonic"].get(k, 999.0))
                    new = float(u.get(k, 999.0) or 999.0)
                    sm = (self.ultrasonic_alpha * prev) + ((1 - self.ultrasonic_alpha) * new)
                    self._snapshot["ultrasonic"][k] = round(sm, 2)

                gas = results.get('gas', {"mq2": {"raw": 0, "rs": 0, "ppm": 0}, "mq135": {"raw": 0, "rs": 0, "ppm": 0}})
                for sensor in ("mq2", "mq135"):
                    prev = self._snapshot["gas"].get(sensor, {"raw": 0, "rs": 0, "ppm": 0})
                    new = gas.get(sensor, {"raw": 0, "rs": 0, "ppm": 0})
                    sm_raw = (self.gas_alpha * prev.get("raw", 0)) + ((1 - self.gas_alpha) * new.get("raw", 0))
                    sm_rs = (self.gas_alpha * prev.get("rs", 0)) + ((1 - self.gas_alpha) * new.get("rs", 0))
                    sm_ppm = (self.gas_alpha * prev.get("ppm", 0)) + ((1 - self.gas_alpha) * new.get("ppm", 0))
                    self._snapshot["gas"][sensor] = {"raw": int(round(sm_raw)), "rs": round(sm_rs, 2), "ppm": int(round(sm_ppm))}

                pir_data = results.get('pir', {"detected": False})
                self._snapshot["pir"] = {"detected": bool(pir_data.get("detected", False)), "alert": bool(pir_data.get("detected", False))}

                metal_data = results.get('metal', {"detected": False})
                self._snapshot["metal"] = {"detected": bool(metal_data.get("detected", False))}

                imu_data = results.get('imu', {"gyro_z": 0})
                self._snapshot["imu"] = {"gyro_z": imu_data.get("gyro_z", 0)}
                self._snapshot["timestamp"] = now
                self._snapshot["system"] = self._get_system_metrics()

            time.sleep(self.update_interval)

    # ----------------------------
    # System helpers
    # ----------------------------
    def _get_system_metrics(self):
        try:
            import psutil, os
            cpu = psutil.cpu_percent()
            temp_raw = os.popen("vcgencmd measure_temp").readline()
            temp = 0.0
            if temp_raw:
                try:
                    temp = float(temp_raw.replace("temp=", "").replace("'C\n", ""))
                except Exception:
                    temp = 0.0
            return {"cpu": cpu, "temp": temp, "voltage": 5.0}
        except Exception:
            return {"cpu": 0, "temp": 0, "voltage": 0}


# Singleton instance
sensor_hub = SensorHub()
