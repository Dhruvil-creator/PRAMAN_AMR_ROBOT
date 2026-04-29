# backend/sensors/imu_wrapper.py

try:
    import imu
    ENABLED = True
except:
    ENABLED = False


def read():
    if not ENABLED:
        return {"gyro_z": 0}

    try:
        return {
            "gyro_z": imu.get_gyro_z()
        }
    except:
        return {"gyro_z": 0}


def get_imu_data():
    """Return unified IMU data for the backend."""
    return read()