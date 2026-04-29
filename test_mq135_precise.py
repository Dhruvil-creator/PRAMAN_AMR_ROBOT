from backend.sensors.mcp3204 import read_channel
import time
import math

# -------------------------
# SYSTEM CONSTANTS (YOUR SETUP)
# -------------------------
VREF = 3.3           # MCP3204 reference
ADC_MAX = 4095.0     # 12-bit ADC
RL = 1.0            # 10kΩ load resistor (your divider)

# TEMP calibration (will refine later)
R0 = 1.1


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

    # MQ135 approximation curve
    ppm = 10 ** ((-0.42 * math.log10(ratio)) + 1.92)
    return round(ppm)


# -------------------------
# MAIN LOOP
# -------------------------
print("\n===== MQ135 PRECISION TEST =====")
print("Using MCP3204 CH1")
print("Warm up sensor for 2–5 minutes...\n")

try:
    while True:
        raw = read_channel(1)  # CH1

        voltage = raw_to_voltage(raw)
        rs = voltage_to_rs(voltage)
        ratio = rs_to_ratio(rs)
        ppm = ratio_to_ppm(ratio)

        print("------")
        print(f"RAW ADC     : {raw}")
        print(f"Voltage     : {voltage:.3f} V")
        print(f"Rs          : {rs:.2f} kΩ")
        print(f"Rs/R0       : {ratio:.2f}")
        print(f"PPM (est.)  : {ppm}")

        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopped")