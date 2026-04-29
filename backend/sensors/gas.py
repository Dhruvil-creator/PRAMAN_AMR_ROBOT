# backend/sensors/gas.py

from backend.sensors.mcp3204 import read_channel
import math
import time

# -------------------------
# HARDWARE CONSTANTS
# -------------------------
VCC = 3.3               # MCP reference voltage
ADC_MAX = 4095.0        # 12-bit ADC
RL = 10.0               # Load resistor (kΩ)

# -------------------------
# CALIBRATION VALUES (INITIAL)
# -------------------------
# ⚠️ These are DEFAULT values → should be calibrated later
R0_MQ2 = 9.8
R0_MQ135 = 3.6

# -------------------------
# LOW LEVEL CALCULATION
# -------------------------
def calculate_rs(raw):
    voltage = (raw / ADC_MAX) * VCC

    if voltage <= 0:
        return 0

    rs = ((VCC - voltage) / voltage) * RL
    return rs


# -------------------------
# PPM CONVERSION CURVES
# -------------------------
def mq2_ppm(rs):
    if rs == 0:
        return 0

    ratio = rs / R0_MQ2

    # LPG / smoke approximation curve
    ppm = 10 ** ((-0.47 * math.log10(ratio)) + 1.92)
    return round(ppm)


def mq135_ppm(rs):
    if rs == 0:
        return 0

    ratio = rs / R0_MQ135

    # CO2 / air quality approximation
    ppm = 10 ** ((-0.42 * math.log10(ratio)) + 1.92)
    return round(ppm)


# -------------------------
# MAIN PROCESS FUNCTION
# -------------------------
def process(raw, sensor_type):
    voltage = (raw / ADC_MAX) * VCC
    rs = calculate_rs(raw)

    if sensor_type == "mq2":
        ppm = mq2_ppm(rs)
    else:
        ppm = mq135_ppm(rs)

    return {
        "raw": raw,
        "voltage": round(voltage, 3),
        "rs": round(rs, 2),
        "ppm": ppm
    }


# -------------------------
# PUBLIC SENSOR FUNCTIONS
# -------------------------
def read_mq2():
    raw = read_channel(0)  # CH0
    return process(raw, "mq2")


def read_mq135():
    raw = read_channel(1)  # CH1
    return process(raw, "mq135")


# -------------------------
# OPTIONAL: CALIBRATION TOOL
# -------------------------
def calibrate(sensor="mq2", samples=50):
    print(f"Calibrating {sensor}... Keep in clean air")

    values = []

    for _ in range(samples):
        raw = read_channel(0 if sensor == "mq2" else 1)
        rs = calculate_rs(raw)
        values.append(rs)
        time.sleep(0.1)

    avg_rs = sum(values) / len(values)

    if sensor == "mq2":
        r0 = avg_rs / 9.8
    else:
        r0 = avg_rs / 3.6

    print(f"Calibration complete for {sensor}")
    print(f"Estimated R0 = {round(r0, 2)}")

    return r0