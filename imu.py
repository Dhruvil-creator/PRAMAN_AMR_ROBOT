import time

try:
    import smbus2 as smbus
    _HAS_SMBUS = True
except Exception:
    smbus = None
    _HAS_SMBUS = False

bus = None
address = 0x68

if _HAS_SMBUS:
    try:
        bus = smbus.SMBus(1)
        bus.write_byte_data(address, 0x6B, 0)
    except Exception:
        bus = None
        _HAS_SMBUS = False

# Global variables for calibration and steady-state baseline
offset_z = 0
baseline_z = 0  # Steady-state baseline when robot is still
prev_z = 0
calibrated = False

# -------------------------------
# READ RAW DATA
# -------------------------------

def read_word(reg):
    if not _HAS_SMBUS or bus is None:
        return 0

    high = bus.read_byte_data(address, reg)
    low = bus.read_byte_data(address, reg + 1)
    value = (high << 8) + low

    if value > 32768:
        value -= 65536

    return value


def get_gyro():
    if not _HAS_SMBUS or bus is None:
        return 0, 0, 0

    gx = read_word(0x43)
    gy = read_word(0x45)
    gz = read_word(0x47)
    return gx, gy, gz

# -------------------------------
# CALIBRATION (IMPROVED)
# -------------------------------

def calibrate():
    global offset_z, baseline_z, calibrated

    if not _HAS_SMBUS or bus is None:
        offset_z = 0
        baseline_z = 0
        calibrated = True
        print("Mock calibration: MPU6050 not available")
        return

    print("Calibrating... Keep robot still")
    samples = []

    for _ in range(200):
        _, _, gz = get_gyro()
        samples.append(gz)
        time.sleep(0.005)

    offset_z = sum(samples) / len(samples)
    baseline_z = offset_z  # Set baseline to the offset value
    calibrated = True

    print("Calibration complete")
    print(f"Offset Z: {offset_z:.4f}")
    print(f"Baseline Z: {baseline_z:.4f}")


# -------------------------------
# FILTERED GYRO OUTPUT WITH BASELINE
# -------------------------------

def get_gyro_z():
    """
    Returns gyro Z rotation relative to baseline (steady position).
    - Returns 0 when robot is still (at baseline)
    - Returns positive when rotating left
    - Returns negative when rotating right
    """
    global prev_z

    _, _, gz = get_gyro()

    # Remove hardware offset
    raw_gyro_z = (gz - offset_z) / 131.0
    
    # Apply deadzone filter (ignore small movements < 0.5 deg/s)
    if abs(raw_gyro_z) < 0.5:
        raw_gyro_z = 0
    
    # Low-pass filter (smooth noise)
    alpha = 0.85
    filtered = alpha * prev_z + (1 - alpha) * raw_gyro_z

    prev_z = filtered

    return round(filtered, 2)

