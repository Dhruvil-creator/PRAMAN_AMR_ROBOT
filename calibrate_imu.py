import smbus
import time

MPU_ADDR = 0x68
PWR_MGMT_1 = 0x6B
GYRO_ZOUT_H = 0x47

bus = smbus.SMBus(1)
bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

def read_word(reg):
    high = bus.read_byte_data(MPU_ADDR, reg)
    low = bus.read_byte_data(MPU_ADDR, reg + 1)
    value = (high << 8) + low
    if value > 32768:
        value -= 65536
    return value

print("Keep IMU completely still...")
time.sleep(2)

samples = []

for _ in range(200):
    gyro_z = read_word(GYRO_ZOUT_H) / 131.0
    samples.append(gyro_z)
    time.sleep(0.01)

offset = sum(samples) / len(samples)

print("\n=== CALIBRATION RESULT ===")
print(f"Gyro Z Offset: {offset:.4f}")