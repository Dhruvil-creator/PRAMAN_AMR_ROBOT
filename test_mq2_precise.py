from backend.sensors.mcp3204 import read_channel
import time
import math

# -------------------------
# SYSTEM CONSTANTS (YOUR SETUP)
# -------------------------
VREF = 3.3
ADC_MAX = 4095.0
RL = 1.0   # 🔥 because you used 1kΩ resistor

# Temporary calibration (will refine after test)
R0 = 0.085
buffer = []
BUFFER_SIZE = 5

# -------------------------
# CALCULATIONS
# -------------------------
def raw_to_voltage(raw):
    return (raw / ADC_MAX) * VREF


def voltage_to_rs(voltage):
    if voltage <= 0:
        return 0
    return ((VREF - voltage) / voltage) * RL


def rs_to_ratio(rs):
    if R0 == 0:
        return 0
    return rs / R0


def ratio_to_ppm(ratio):
    if ratio <= 0:
        return 0

    # MQ2 LPG/smoke approximation curve
    ppm = 10 ** ((-0.47 * math.log10(ratio)) + 1.92)
    return round(ppm)


# -------------------------
# MAIN LOOP
# -------------------------
print("\n===== MQ2 PRECISION TEST =====")
print("Using MCP3204 CH0")
print("Warm up sensor for 2–5 minutes...\n")

try:
    while True:
        raw = read_channel(0)

        # -------------------------
        # FILTER (MOVING AVERAGE)
        # -------------------------
        if raw > 50:  # ignore invalid spikes
            buffer.append(raw)

        if len(buffer) > BUFFER_SIZE:
            buffer.pop(0)

        if buffer:
            raw_filtered = sum(buffer) / len(buffer)
        else:
            raw_filtered = raw
        # -------------------------

        voltage = raw_to_voltage(raw_filtered)
        rs = voltage_to_rs(voltage)
        ratio = rs_to_ratio(rs)
        ppm = ratio_to_ppm(ratio)

        print("------")
        print(f"RAW ADC     : {int(raw_filtered)}")
        print(f"Voltage     : {voltage:.3f} V")
        print(f"Rs          : {rs:.2f} kΩ")
        print(f"Rs/R0       : {ratio:.2f}")
        print(f"PPM (est.)  : {ppm}")

        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopped")