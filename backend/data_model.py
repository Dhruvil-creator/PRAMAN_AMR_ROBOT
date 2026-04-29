import time
import random
import psutil
import os

# Mode control - set to TRUE to force simulation, HYBRID to attempt real sensors first,
# or FALSE to use real sensors when available.
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "FALSE").upper()
if SIMULATION_MODE in ("TRUE", "1", "YES"):
    SIMULATION_MODE = True
elif SIMULATION_MODE == "HYBRID":
    SIMULATION_MODE = "HYBRID"
else:
    SIMULATION_MODE = False

# Import sensors safely and allow partial hardware availability.
mq = None
ultrasonic = None
pir = None
metal = None
imu_wrapper = None
SENSORS_AVAILABLE = False

try:
    from backend.sensors import mq
    mq = mq
except Exception as e:
    print("⚠️ MQ import error:", e)

try:
    from backend.sensors import ultrasonic
    ultrasonic = ultrasonic
except Exception as e:
    print("⚠️ Ultrasonic import error:", e)

try:
    from backend.sensors import pir
    pir = pir
except Exception as e:
    print("⚠️ PIR import error:", e)

try:
    from backend.sensors import metal
    metal = metal
except Exception as e:
    print("⚠️ Metal import error:", e)

try:
    from backend.sensors import imu_wrapper
    imu_wrapper = imu_wrapper
except Exception as e:
    print("⚠️ IMU import error:", e)

if mq or ultrasonic or pir or metal or imu_wrapper:
    SENSORS_AVAILABLE = True


# -------------------------
# STATUS FUNCTIONS
# -------------------------

def gas_status(ppm):
    if ppm < 200:
        return "safe"
    elif ppm < 600:
        return "warning"
    return "danger"


def ultrasonic_status(center):
    if center < 20:
        return "obstacle"
    elif center < 50:
        return "near"
    return "safe"


def build_payload(gas_data, ultrasonic_data, pir_data, metal_data, imu_data):
    return {
        "timestamp": time.time(),
        "gas": {
            "mq2": {
                **gas_data["mq2"],
                "status": gas_status(gas_data["mq2"].get("ppm", 0))
            },
            "mq135": {
                **gas_data["mq135"],
                "status": gas_status(gas_data["mq135"].get("ppm", 0))
            }
        },
        "ultrasonic": {
            **ultrasonic_data,
            "status": ultrasonic_status(ultrasonic_data.get("center", 999))
        },
        "ultrasonic_raw": dict(ultrasonic_data),
        "pir": {
            "value": bool(pir_data.get("detected", False)),
            "alert": bool(pir_data.get("detected", False))
        },
        "metal": {
            "detected": bool(metal_data.get("detected", False))
        },
        "imu": imu_data,
        "system": get_system_metrics(),
        "pathfinding": {
            "enabled": False,
            "status": "disabled"
        }
    }


# -------------------------
# SYSTEM METRICS
# -------------------------

def get_system_metrics():
    try:
        cpu = psutil.cpu_percent()
        temp_raw = os.popen("vcgencmd measure_temp").readline()
        temp = float(temp_raw.replace("temp=", "").replace("'C\n", ""))
        return {
            "cpu": cpu,
            "temp": temp,
            "voltage": 5.0
        }
    except:
        return {
            "cpu": 0,
            "temp": 0,
            "voltage": 0
        }


# -------------------------
# HELPER READERS
# -------------------------

def default_gas_data():
    return {
        "mq2": {"raw": 0, "rs": 0, "ppm": 0},
        "mq135": {"raw": 0, "rs": 0, "ppm": 0}
    }


def read_gas_data():
    if mq is None:
        return default_gas_data()
    try:
        return mq.read_all()
    except Exception as e:
        print("⚠️ MQ read error:", e)
        return default_gas_data()


def default_ultrasonic_data():
    return {"center": 999, "left": 999, "right": 999}


def read_ultrasonic_data():
    if ultrasonic is None:
        return default_ultrasonic_data()
    try:
        return ultrasonic.get_distance()
    except Exception as e:
        print("⚠️ Ultrasonic read error:", e)
        return default_ultrasonic_data()


def default_pir_data():
    return {"detected": False}


def read_pir_data():
    if pir is None:
        return default_pir_data()
    try:
        return pir.get_motion()
    except Exception as e:
        print("⚠️ PIR read error:", e)
        return default_pir_data()


def default_metal_data():
    return {"detected": False}


def read_metal_data():
    if metal is None:
        return default_metal_data()
    try:
        return metal.get_hazard()
    except Exception as e:
        print("⚠️ Metal read error:", e)
        return default_metal_data()


def default_imu_data():
    return {"gyro_z": 0}


def read_imu_data():
    if imu_wrapper is None:
        return default_imu_data()
    try:
        return imu_wrapper.get_imu_data()
    except Exception as e:
        print("⚠️ IMU read error:", e)
        return default_imu_data()


# -------------------------
# MAIN DATA FUNCTION
# -------------------------

def get_system_data():
    # Prefer snapshot from SensorHub and convert to the standardized payload
    try:
        from backend.sensors.manager import sensor_hub
        if sensor_hub and sensor_hub.is_running():
            snap = sensor_hub.get_snapshot()
            # Extract components with safe defaults
            gas_data = snap.get('gas', default_gas_data())
            ultrasonic_data = snap.get('ultrasonic', default_ultrasonic_data())
            pir_data = snap.get('pir', default_pir_data())
            metal_data = snap.get('metal', default_metal_data())
            imu_data = snap.get('imu', default_imu_data())
            # Convert SensorHub snapshot into the enriched payload the frontend expects
            payload = build_payload(gas_data, ultrasonic_data, pir_data, metal_data, imu_data)
            if 'ultrasonic_raw' in snap:
                payload['ultrasonic_raw'] = snap.get('ultrasonic_raw', payload.get('ultrasonic_raw'))
            return payload
    except Exception:
        pass

    if SIMULATION_MODE == True:
        return simulate_data()
    return real_data()


# -------------------------
# REAL DATA
# -------------------------

def real_data():
    gas_data = read_gas_data()
    ultrasonic_data = read_ultrasonic_data()
    pir_data = read_pir_data()
    metal_data = read_metal_data()
    imu_data = read_imu_data()
    return build_payload(gas_data, ultrasonic_data, pir_data, metal_data, imu_data)


# -------------------------
# HYBRID MODE
# -------------------------

def hybrid_data():
    return real_data()


# -------------------------
# SIMULATION
# -------------------------

def simulate_data():
    mq2_v = round(random.uniform(1.2, 2.5), 2)
    mq135_v = round(random.uniform(1.0, 2.3), 2)
    center = round(random.uniform(10, 100), 2)
    gas_data = {
        "mq2": {
            "raw": random.randint(1500, 3000),
            "voltage": mq2_v,
            "rs": round(((VCC - mq2_v) / mq2_v) * RL, 2),
            "ppm": round(mq2_v * 100)
        },
        "mq135": {
            "raw": random.randint(1200, 2800),
            "voltage": mq135_v,
            "rs": round(((VCC - mq135_v) / mq135_v) * RL, 2),
            "ppm": round(mq135_v * 100)
        }
    }
    ultrasonic_data = {
        "center": center,
        "left": round(random.uniform(10, 100), 2),
        "right": round(random.uniform(10, 100), 2)
    }
    pir_data = {"detected": random.choice([True, False])}
    metal_data = {"detected": random.choice([True, False])}
    imu_data = {"gyro_z": round(random.uniform(-2, 2), 2)}
    return build_payload(gas_data, ultrasonic_data, pir_data, metal_data, imu_data)
