import smbus
import time

MPU_ADDR = 0x68
PWR_MGMT_1 = 0x6B
GYRO_ZOUT_H = 0x47

OFFSET = -0.9195   # 🔥 your calibrated value

bus = smbus.SMBus(1)
bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

def read_word(reg):
    high = bus.read_byte_data(MPU_ADDR, reg)
    low = bus.read_byte_data(MPU_ADDR, reg + 1)
    value = (high << 8) + low
    if value > 32768:
        value -= 65536
    return value

print("=== CALIBRATED IMU TEST ===")

try:
    while True:
        raw = read_word(GYRO_ZOUT_H) / 131.0
        gyro_z = raw - OFFSET   # 🔥 correction applied

        if abs(gyro_z) < 0.5:
            status = "STABLE"
        elif gyro_z > 0:
            status = "ROTATING LEFT"
        else:
            status = "ROTATING RIGHT"

        print(f"Gyro Z: {gyro_z:.2f} → {status}")

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopped")