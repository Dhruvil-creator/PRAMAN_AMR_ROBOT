import time
from backend.sensors import ultrasonic

# -------------------------
# CONFIG
# -------------------------
MAX_DISTANCE = 400  # cm

def get_status(dist):
    if dist == 999:
        return "NO SIGNAL"
    elif dist < 20:
        return "DANGER"
    elif dist < 50:
        return "NEAR"
    elif dist < MAX_DISTANCE:
        return "SAFE"
    else:
        return "OUT OF RANGE"

# -------------------------
# MAIN LOOP
# -------------------------
print("=== ULTRASONIC BASIC TEST ===\n")

while True:
    data = ultrasonic.read_all()

    print("\n-------------------------")

    for name, dist in data.items():

        # Clamp to max range
        if dist > MAX_DISTANCE:
            dist = MAX_DISTANCE

        status = get_status(dist)

        print(f"{name.upper():6} : {dist:6.1f} cm → {status}")

    print("-------------------------")

    time.sleep(0.5)