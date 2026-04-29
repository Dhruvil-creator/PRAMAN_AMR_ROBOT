from mq_sensors import read_channel
import time

while True:
    raw0 = read_channel(0)
    raw1 = read_channel(1)

    print(f"RAW MQ2: {raw0} | RAW MQ135: {raw1}")
    time.sleep(1)