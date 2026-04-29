import io
import os
import time
import threading
from collections import deque
from flask import Flask, request, Response

try:
    from flask_socketio import SocketIO, emit
    SOCKETIO_AVAILABLE = True
except ImportError:
    SocketIO = None
    SOCKETIO_AVAILABLE = False

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    Picamera2 = None
    PICAMERA2_AVAILABLE = False

try:
    import cv2
    OPENCV_AVAILABLE = True
except Exception:
    cv2 = None
    OPENCV_AVAILABLE = False

from backend.data_model import get_system_data
from backend.pathfinding import GridMap, AStarPathfinder
from backend.autonomous import AutonomousModeManager
import motor
import imu
from backend import watchdog as motor_watchdog
try:
    from backend.camera import capture as camera_capture
except Exception:
    camera_capture = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_url_path='',
    static_folder=FRONTEND_DIR
)

socketio = SocketIO(app, cors_allowed_origins='*') if SOCKETIO_AVAILABLE else None

# -------------------------------
# GLOBAL STATE
# -------------------------------
current_speed = 70
current_command = 'stop'
current_servo_angle = 75
prev_error = 0
sensor_buffer = deque(maxlen=120)
metal_servo_enabled = False  # Enable/disable metal sensor -> servo connection

# Autonomous navigation state
autonomous_grid = GridMap(width=20, height=15)
autonomous_path = None
autonomous_status = 'idle'  # idle, planning, executing, paused
current_waypoint_index = 0
autonomous_manager = None  # Initialized after system startup

camera = None
use_picamera2 = False
use_cv2 = False
safety_prev_ultra = {'center': None, 'left': None, 'right': None}
safety_last_near_ts = 0.0
safety_last_trip_ts = 0.0

# -------------------------------
# CAMERA SUPPORT
# -------------------------------

def initialize_camera():
    global camera, use_picamera2, use_cv2
    if PICAMERA2_AVAILABLE:
        try:
            camera = Picamera2()
            config = camera.create_preview_configuration(main={'size': (640, 480)})
            camera.configure(config)
            camera.start()
            use_picamera2 = True
            print('Picamera2 initialized')
            return
        except Exception as exc:
            print('Picamera2 init failed:', exc)
            camera = None

    if OPENCV_AVAILABLE:
        try:
            camera = cv2.VideoCapture(0)
            if camera.isOpened():
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                use_cv2 = True
                print('OpenCV camera initialized')
                return
            camera.release()
            camera = None
        except Exception as exc:
            print('OpenCV init failed:', exc)
            camera = None

    print('Camera not available in backend; install picamera2 or opencv-python-headless on Raspberry Pi')


def generate_camera_stream():
    if camera is None:
        return
    while True:
        try:
            if use_picamera2:
                if OPENCV_AVAILABLE:
                    frame = camera.capture_array()
                    if frame is None:
                        continue
                    ret, jpeg = cv2.imencode('.jpg', frame)
                    if not ret:
                        continue
                    frame_bytes = jpeg.tobytes()
                else:
                    frame_file = '/tmp/camera_feed.jpg'
                    camera.capture_file(frame_file)
                    with open(frame_file, 'rb') as f:
                        frame_bytes = f.read()
            elif use_cv2:
                ret, frame = camera.read()
                if not ret or frame is None:
                    continue
                ret, jpeg = cv2.imencode('.jpg', frame)
                if not ret:
                    continue
                frame_bytes = jpeg.tobytes()
            else:
                break

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
        except Exception as exc:
            print('Camera stream error:', exc)
            time.sleep(0.1)


# -------------------------------
# BACKGROUND LOOPS
# -------------------------------

def speed_loop():
    while True:
        motor.update_speed()
        time.sleep(0.05)


def command_loop():
    global current_command, current_speed, prev_error, autonomous_manager

    while True:
        cmd = current_command

        try:
            gz = imu.get_gyro_z()
        except Exception:
            gz = 0

        sensor_buffer.append({
            'gyro_z': gz,
            'speed': current_speed,
            'command': current_command,
            'time': time.time()
        })

        # In autonomous mode, manual command loop must not override autonomous motor control.
        if autonomous_manager and autonomous_manager.is_autonomous:
            if autonomous_manager.is_executing:
                time.sleep(0.05)
                continue
            if cmd != 'stop':
                current_command = 'stop'
            motor.stop()
            prev_error = 0
            time.sleep(0.05)
            continue

        if cmd == 'forward':
            # Manual forward must drive both sides equally; IMU-based differential
            # correction can zero one side on noisy gyro values.
            motor.set_speed(current_speed)
            motor.forward()
            prev_error = 0

        elif cmd == 'backward':
            motor.set_speed(current_speed)
            motor.backward()

        elif cmd == 'left':
            motor.set_speed(current_speed)
            motor.left()

        elif cmd == 'right':
            motor.set_speed(current_speed)
            motor.right()

        elif cmd == 'stop':
            motor.stop()
            prev_error = 0

        time.sleep(0.05)


def sensor_dispatch_loop():
    while True:
        data = get_system_data()
        if SOCKETIO_AVAILABLE and socketio:
            socketio.emit('sensor_update', data, namespace='/dashboard')
        time.sleep(1.0)


def metal_sensor_loop():
    """Monitor metal sensor and trigger servo action when metal detected."""
    global metal_servo_enabled
    from backend.sensors.metal import read as read_metal_sensor
    last_metal_state = False
    last_trigger_time = 0
    COOLDOWN_SECONDS = 1  # Prevent rapid retriggering
    
    while True:
        try:
            # Check current flag (updated by toggle)
            if metal_servo_enabled:
                metal_detected = read_metal_sensor()
                current_time = time.time()
                
                # Rising edge detection + cooldown
                if metal_detected and not last_metal_state and (current_time - last_trigger_time) > COOLDOWN_SECONDS:
                    print("🔔 Metal detected! Triggering servo action...")
                    last_trigger_time = current_time
                    # Capture image if camera helper available (non-blocking)
                    try:
                        if camera_capture:
                            img = camera_capture.capture_image()
                            print(f"[CAMERA] Captured image: {img}")
                    except Exception as e:
                        print(f"[CAMERA] capture failed: {e}")
                    threading.Thread(target=lambda: motor.pulse_servo(120, duration=0.2), daemon=True).start()
                
                last_metal_state = metal_detected
        except Exception as e:
            print(f"Metal sensor loop error: {e}")
        
        time.sleep(0.1)


def autonomous_safety_loop():
    """Independent hard-stop guard for autonomous mode using raw ultrasonic readings."""
    global current_command, safety_last_near_ts, safety_last_trip_ts, safety_prev_ultra

    while True:
        try:
            am = autonomous_manager
            if not am or not am.is_autonomous or not am.is_executing:
                time.sleep(0.03)
                continue

            payload = get_system_data()
            raw_ultra = payload.get('ultrasonic_raw') or payload.get('ultrasonic') or {}
            now = time.time()
            reasons = []
            invalid = False
            unsafe = False
            values = []
            prev_center = safety_prev_ultra.get('center')

            for key in ('center', 'left', 'right'):
                raw = raw_ultra.get(key)
                if not isinstance(raw, (int, float)):
                    continue
                val = float(raw)
                values.append(val)
                safety_prev_ultra[key] = val

            center = raw_ultra.get('center')
            center = float(center) if isinstance(center, (int, float)) else None
            if center is not None and 0 < center <= 25:
                safety_last_near_ts = now

            valid_vals = [v for v in values if 0 < v <= 400]
            nearest = min(valid_vals) if valid_vals else None

            if center is None:
                invalid = True
                reasons.append('center_missing')
            elif center <= 0:
                invalid = True
                reasons.append('center_invalid')
            elif center > 400:
                invalid = True
                reasons.append('center_over_max')

            if center is not None and center < 5:
                unsafe = True
                reasons.append('center_too_close')
            if center is not None and 0 < center <= 20:
                unsafe = True
                reasons.append('stop_distance')

            if (
                center is not None
                and prev_center is not None
                and abs(center - prev_center) > 120
                and prev_center <= 25
            ):
                invalid = True
                reasons.append('center_jump')
            if (
                center is not None
                and prev_center is not None
                and center >= 400
                and prev_center <= 25
            ):
                invalid = True
                unsafe = True
                reasons.append('center_max_spike')

            if invalid and (now - safety_last_near_ts) <= 1.0:
                unsafe = True
                reasons.append('blind_zone_recent_near')

            if invalid or unsafe:
                current_command = 'stop'
                try:
                    if getattr(motor, 'hard_stop', None):
                        motor.hard_stop()
                    else:
                        motor.stop()
                except Exception:
                    pass

                # Prefer pausing controller execution; fallback to full stop.
                paused = False
                try:
                    controller = getattr(am, '_controller', None)
                    if controller and getattr(controller, '_pause', None):
                        controller._pause('emergency_stop')
                        paused = True
                except Exception:
                    paused = False
                if not paused:
                    try:
                        am.stop_autonomous_execution()
                    except Exception:
                        pass

                if (now - safety_last_trip_ts) > 0.3:
                    try:
                        print(f"[SAFETY-GUARD] hard stop nearest={nearest} reasons={','.join(reasons)} raw={raw_ultra}")
                    except Exception:
                        pass
                    safety_last_trip_ts = now

        except Exception as e:
            print(f"[SAFETY-GUARD] loop error: {e}")

        time.sleep(0.03)


# -------------------------------
# BASIC OBSTACLE GUARD
# -------------------------------


def basic_obstacle_guard_loop():
    """Simple obstacle guard: read front ultrasonic continuously and hard-stop on detection.

    Rules (minimal):
    - If center <= 25 cm -> immediate stop
    - If center <= 5 cm -> immediate emergency stop
    - If previous center < 20 cm and current reading is an invalid spike (0 or very large)
      treat as obstacle and stop

    This loop enforces a motor.hard_stop() to override any other commands and blocks
    further motor commands via the safety interlock.
    """
    global current_command
    prev_center = None
    last_safe_print = 0.0
    SAFE_PRINT_INTERVAL = 0.5
    STOP_DISTANCE = 25.0
    EMERGENCY_DISTANCE = 5.0
    PREV_SMALL_THRESHOLD = 20.0
    MAX_SPIKE = 400.0
    MAX_DEFAULT = 999.0

    while True:
        try:
            payload = get_system_data()
            ultra_raw = payload.get('ultrasonic_raw') or payload.get('ultrasonic') or {}
            center = ultra_raw.get('center')
            center_val = None
            if isinstance(center, (int, float)):
                center_val = float(center)

            obstacle = False
            reason = None

            # Immediate emergency
            if center_val is not None and center_val <= EMERGENCY_DISTANCE:
                obstacle = True
                reason = 'center_too_close'

            # Normal stop threshold
            elif center_val is not None and center_val <= STOP_DISTANCE:
                obstacle = True
                reason = 'within_stop_distance'

            else:
                # Spike detection following a recent near reading
                if prev_center is not None and prev_center < PREV_SMALL_THRESHOLD:
                    if center is None or (isinstance(center, (int, float)) and (center_val == 0.0 or center_val >= MAX_SPIKE or center_val >= MAX_DEFAULT)):
                        obstacle = True
                        reason = 'spike_after_near'

            now = time.time()

            if obstacle:
                try:
                    print(f"[OBSTACLE-GUARD] center={center} prev={prev_center} -> OBSTACLE DETECTED ({reason}) -> STOP")
                except Exception:
                    pass
                # enforce immediate hard stop and block further motor commands
                try:
                    if getattr(motor, 'hard_stop', None):
                        motor.hard_stop()
                    else:
                        motor.stop()
                except Exception:
                    pass
                # also set global command to stop for coherence with manual loop
                try:
                    current_command = 'stop'
                except Exception:
                    pass
            else:
                if now - last_safe_print >= SAFE_PRINT_INTERVAL:
                    try:
                        print(f"[OBSTACLE-GUARD] center={center_val} prev={prev_center} status=SAFE")
                    except Exception:
                        pass
                    last_safe_print = now

            prev_center = center_val
        except Exception as e:
            try:
                print(f"[OBSTACLE-GUARD] loop error: {e}")
            except Exception:
                pass
        time.sleep(0.05)


# -------------------------------
# INITIALIZATION
# -------------------------------

def initialize_system():
    global autonomous_manager
    print('Initializing system...')
    
    # Initialize camera
    try:
        initialize_camera()
    except Exception as e:
        print(f'Camera init failed (non-critical): {e}')
    
    # Initialize IMU with timeout
    try:
        print('Calibrating IMU...')
        imu.calibrate()
        print('IMU calibrated')
    except Exception as e:
        print(f'IMU calibration failed (non-critical): {e}')
    
    # Initialize motor
    try:
        motor.set_speed(current_speed)
        motor.set_servo_angle(75)  # Initialize servo to center (75°)
        print('Motor initialized')
    except Exception as e:
        print(f'Motor init failed: {e}')
    
    # Start sensor hub (background sensor fusion)
    try:
        from backend.sensors.manager import sensor_hub
        sensor_hub.start()
        print('Sensor hub started')
    except Exception as e:
        print(f'Sensor hub start failed (non-critical): {e}')

    # Initialize autonomous mode manager with sensor data function
    try:
        autonomous_manager = AutonomousModeManager(
            autonomous_grid,
            get_system_data
        )
        print('Autonomous mode manager initialized')
    except Exception as e:
        print(f'Autonomous manager init failed (non-critical): {e}')
    
    # Start background threads
    threading.Thread(target=speed_loop, daemon=True).start()
    threading.Thread(target=command_loop, daemon=True).start()
    threading.Thread(target=autonomous_safety_loop, daemon=True).start()
    # Start the minimal basic obstacle guard loop (always-on safety)
    threading.Thread(target=basic_obstacle_guard_loop, daemon=True).start()

    # Start motor watchdog (non-critical)
    try:
        motor_watchdog.start_watchdog(timeout=1.0, check_interval=0.25)
        print('Motor watchdog started')
    except Exception as e:
        print(f'Motor watchdog start failed (non-critical): {e}')

    if SOCKETIO_AVAILABLE:
        threading.Thread(target=sensor_dispatch_loop, daemon=True).start()
        threading.Thread(target=metal_sensor_loop, daemon=True).start()
    print('System ready')


# -------------------------------
# ROUTES
# -------------------------------

@app.route('/')
def home():
    return app.send_static_file('dashboard.html')


@app.route('/control', methods=['POST'])
def control():
    global current_command, autonomous_manager
    command = request.form.get('command', 'stop')
    if autonomous_manager and autonomous_manager.is_autonomous and command != 'stop':
        return {'error': 'Manual control disabled in autonomous mode. Switch to manual mode first.'}, 409
    current_command = command
    return ('', 204)


@app.route('/speed', methods=['POST'])
def set_speed():
    global current_speed
    try:
        current_speed = int(request.form.get('speed', current_speed))
    except ValueError:
        pass
    motor.set_speed(current_speed)
    return ('', 204)


@app.route('/emergency')
def emergency():
    global current_command
    current_command = 'stop'
    if getattr(motor, 'hard_stop', None):
        motor.hard_stop()
    else:
        motor.stop()
    return {'status': 'emergency', 'command': current_command}


@app.route('/servo', methods=['POST'])
def servo_control():
    global metal_servo_enabled
    action = request.form.get('action', '')

    if action == 'open':
        print('Servo open command received')
        threading.Thread(target=lambda: motor.pulse_servo(180), daemon=True).start()
    elif action == 'close':
        print('Servo close command received')
        threading.Thread(target=lambda: motor.pulse_servo(0), daemon=True).start()
    elif action == 'restore':
        print('Servo restore command received')
        threading.Thread(target=lambda: motor.pulse_servo(75), daemon=True).start()
    elif action == 'action':
        print('Servo action command received (120° swing)')
        threading.Thread(target=lambda: motor.pulse_servo(120, duration=0.2), daemon=True).start()
    elif action == 'hold_toggle':
        try:
            res = motor.toggle_servo_hold_mode()
            print(f"Servo hold mode toggled -> {res.get('servo_hold_mode')}")
            return res
        except Exception as e:
            return {'error': str(e)}, 500
    elif action == 'metal_detect_toggle':
        # Use global declaration to properly modify the flag
        metal_servo_enabled = not metal_servo_enabled
        status = 'enabled' if metal_servo_enabled else 'disabled'
        print(f'Metal detector -> servo connection {status}')
        return {'metal_servo': metal_servo_enabled}

    return ('', 204)


@app.route('/data')
def data():
    return {'history': list(sensor_buffer)}


@app.route('/sensor-data')
def sensor_data():
    try:
        return get_system_data()
    except Exception:
        return {'error': 'sensor read failed'}


@app.route('/camera_feed')
def camera_feed():
    if camera is None:
        return {'error': 'camera unavailable'}, 503
    return Response(generate_camera_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def system_status():
    global autonomous_manager
    mode = 'manual'
    autonomous = False
    if autonomous_manager:
        autonomous = autonomous_manager.is_autonomous
        mode = 'autonomous' if autonomous else 'manual'
    return {
        'mode': mode,
        'autonomous': autonomous,
        'metal_servo_enabled': metal_servo_enabled
    }


if SOCKETIO_AVAILABLE:

    @socketio.on('connect', namespace='/dashboard')
    def on_connect():
        print('Client connected to SocketIO')
        try:
            emit('sensor_update', get_system_data())
        except Exception:
            emit('sensor_update', {'error': 'init failed'})

    @socketio.on('control_command', namespace='/dashboard')
    def on_control_command(message):
        global current_command, current_speed, autonomous_manager
        cmd = message.get('command')
        speed = message.get('speed')

        if cmd and autonomous_manager and autonomous_manager.is_autonomous and cmd != 'stop':
            emit('control_ack', {
                'command': 'stop',
                'speed': current_speed,
                'rejected': True,
                'reason': 'Manual control disabled in autonomous mode'
            })
            return

        if cmd:
            current_command = cmd
        if speed is not None:
            try:
                current_speed = int(speed)
                motor.set_speed(current_speed)
            except Exception:
                pass
        emit('control_ack', {'command': current_command, 'speed': current_speed})


# ================================
# AUTONOMOUS NAVIGATION ENDPOINTS
# ================================

@app.route('/autonomous/grid', methods=['GET'])
def get_grid():
    """Get current grid state."""
    return autonomous_grid.to_dict()


@app.route('/autonomous/grid/set', methods=['POST'])
def set_grid_element():
    """Set grid element (start, goal, obstacle)."""
    global autonomous_grid
    
    try:
        data = request.get_json(silent=True) or {}
        element_type = data.get('type')  # 'start', 'goal', 'wall'
        x = int(data.get('x'))
        y = int(data.get('y'))
        grid_space = data.get('grid', 'legacy')

        # Controller-grid input (50x50 center) for full-page UI
        if grid_space == 'controller' and autonomous_manager and getattr(autonomous_manager, '_controller', None):
            controller = autonomous_manager._controller
            if element_type == 'start':
                controller.grid.set_start(x, y)
            elif element_type == 'goal':
                controller.grid.set_goal(x, y)
            elif element_type == 'wall':
                controller.grid.set_obstacle(x, y)
            elif element_type == 'clear':
                controller.grid.clear_obstacle(x, y)

            # Best-effort mirror to legacy grid for compatibility
            try:
                Lw, Lh = autonomous_grid.width, autonomous_grid.height
                Nw, Nh = controller.grid.width, controller.grid.height
                lx = int(round(x * (Lw - 1) / max(1, (Nw - 1))))
                ly = int(round(y * (Lh - 1) / max(1, (Nh - 1))))
                if element_type == 'start':
                    autonomous_grid.set_start(lx, ly)
                elif element_type == 'goal':
                    autonomous_grid.set_goal(lx, ly)
                elif element_type == 'wall':
                    autonomous_grid.set_obstacle(lx, ly, True)
                elif element_type == 'clear':
                    autonomous_grid.set_obstacle(lx, ly, False)
            except Exception:
                pass

            return {'status': 'ok', 'grid': controller.grid.to_dict()}

        # Legacy grid input (dashboard panel)
        if element_type == 'start':
            autonomous_grid.set_start(x, y)
        elif element_type == 'goal':
            autonomous_grid.set_goal(x, y)
        elif element_type == 'wall':
            autonomous_grid.set_obstacle(x, y, True)
        elif element_type == 'clear':
            autonomous_grid.set_obstacle(x, y, False)

        # --- Sync to new controller grid (best-effort) ---
        try:
            if autonomous_manager and hasattr(autonomous_manager, '_controller') and autonomous_manager._controller:
                controller = autonomous_manager._controller
                # Map legacy grid coords -> controller grid coords (scale)
                try:
                    Lw, Lh = autonomous_grid.width, autonomous_grid.height
                    Nw, Nh = controller.grid.width, controller.grid.height
                    def _map_coords(ix, iy):
                        nx = int(round(ix * (Nw - 1) / max(1, (Lw - 1))))
                        ny = int(round(iy * (Nh - 1) / max(1, (Lh - 1))))
                        return nx, ny
                except Exception:
                    def _map_coords(ix, iy): 
                        return ix, iy

                if element_type == 'start':
                    gx, gy = _map_coords(x, y)
                    if hasattr(controller.grid, 'set_start'):
                        controller.grid.set_start(gx, gy)
                    else:
                        controller.grid.start = (gx, gy)
                elif element_type == 'goal':
                    gx, gy = _map_coords(x, y)
                    if hasattr(controller.grid, 'set_goal'):
                        controller.grid.set_goal(gx, gy)
                    else:
                        controller.grid.goal = (gx, gy)
                elif element_type == 'wall':
                    gx, gy = _map_coords(x, y)
                    if hasattr(controller.grid, 'set_obstacle'):
                        controller.grid.set_obstacle(gx, gy)
                    else:
                        try:
                            controller.grid.grid[gy][gx] = controller.grid.OBSTACLE
                        except Exception:
                            pass
                elif element_type == 'clear':
                    gx, gy = _map_coords(x, y)
                    if hasattr(controller.grid, 'clear_obstacle'):
                        controller.grid.clear_obstacle(gx, gy)
                    else:
                        try:
                            controller.grid.grid[gy][gx] = controller.grid.FREE
                        except Exception:
                            pass
        except Exception:
            pass

        return {'status': 'ok', 'grid': autonomous_grid.to_dict()}
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/autonomous/grid/clear', methods=['POST'])
def clear_grid():
    """Clear entire grid."""
    global autonomous_grid
    data = request.get_json(silent=True) or {}
    grid_space = data.get('grid', 'legacy')

    if grid_space == 'controller' and autonomous_manager and getattr(autonomous_manager, '_controller', None):
        controller = autonomous_manager._controller
        if hasattr(controller.grid, 'clear'):
            controller.grid.clear()
        try:
            autonomous_grid.clear()
        except Exception:
            pass
        return {'status': 'cleared', 'grid': controller.grid.to_dict()}

    autonomous_grid.clear()
    # also clear controller grid if available (best-effort)
    try:
        if autonomous_manager and hasattr(autonomous_manager, '_controller') and autonomous_manager._controller:
            controller = autonomous_manager._controller
            if hasattr(controller.grid, 'clear'):
                controller.grid.clear()
    except Exception:
        pass
    return {'status': 'cleared', 'grid': autonomous_grid.to_dict()}


@app.route('/autonomous/plan', methods=['POST'])
def plan_path():
    """Plan A* path from start to goal. Prefer new controller planner when available."""
    global autonomous_path, autonomous_status, current_waypoint_index, autonomous_manager
    
    try:
        # Use new controller's planner if present
        if autonomous_manager and hasattr(autonomous_manager, '_controller') and autonomous_manager._controller:
            controller = autonomous_manager._controller
            if controller.grid.goal is None:
                return {'error': 'Start or goal not set (controller)'}, 400
            autonomous_status = 'planning'
            path = controller.plan_path()
            if path:
                autonomous_path = path
                current_waypoint_index = 0
                autonomous_status = 'ready'
                return {
                    'status': 'success',
                    'path': autonomous_path,
                    'stats': {'length': len(autonomous_path)}
                }
            else:
                autonomous_status = 'idle'
                return {'status': 'no_path'}

        # Fallback to legacy pathfinder
        if not autonomous_grid.start or not autonomous_grid.goal:
            return {'error': 'Start or goal not set'}, 400
        autonomous_status = 'planning'
        pathfinder = AStarPathfinder(autonomous_grid)
        path, stats = pathfinder.find_path()
        if path:
            autonomous_path = pathfinder.smooth_path(path)
            current_waypoint_index = 0
            autonomous_status = 'ready'
            return {
                'status': 'success',
                'path': autonomous_path,
                'stats': stats,
                'visited_cells': pathfinder.get_visited_cells()
            }
        else:
            autonomous_status = 'idle'
            return {'status': 'no_path', 'stats': stats}
    except Exception as e:
        autonomous_status = 'idle'
        return {'error': str(e)}, 400


@app.route('/autonomous/execute', methods=['POST'])
def execute_path():
    """Start executing the planned path with sensor monitoring."""
    global autonomous_path, autonomous_manager

    if not autonomous_path:
        err = 'No path planned'
        print(f"[AUTONOMY] Execute failed: {err}")
        return {'error': err}, 400

    if not autonomous_manager:
        err = 'Autonomous manager not initialized'
        print(f"[AUTONOMY] Execute failed: {err}")
        return {'error': err}, 500

    # If already executing but paused, treat Execute as Resume for better UX.
    try:
        st = autonomous_manager.get_status()
        if st.get('status') == 'paused':
            resumed = autonomous_manager.resume_autonomous()
            if isinstance(resumed, dict) and resumed.get('error'):
                return {'error': resumed.get('error')}, 400
            return {'status': 'executing', 'resumed': True}
        if st.get('status') == 'executing':
            running_path = st.get('path') or []
            requested_path = [[int(p[0]), int(p[1])] for p in autonomous_path]
            # If user replanned while running, restart on the newly planned path
            if running_path != requested_path:
                autonomous_manager.stop_autonomous_execution()
                time.sleep(0.05)
            else:
                return {'status': 'executing', 'already_running': True}
    except Exception:
        pass

    # Start autonomous execution with sensor integration
    result = autonomous_manager.start_autonomous_execution(autonomous_path)
    if isinstance(result, dict) and result.get('error'):
        err = result.get('error')
        # More specific status for common conflict
        if 'Already executing' in err or 'already executing' in err.lower():
            # Return current state so frontend can switch to Resume flow instead of error spam
            try:
                st = autonomous_manager.get_status()
                return {
                    'status': st.get('status', 'executing'),
                    'paused': bool(st.get('paused', False)),
                    'pause_reason': st.get('pause_reason')
                }, 200
            except Exception:
                return {'error': err}, 409
        return {'error': err}, 400

    print(f"[AUTONOMY] Execution started: path_length={len(autonomous_path)}")
    return result


@app.route('/autonomous/stop', methods=['POST'])
def stop_autonomous():
    """Stop autonomous execution and return to manual mode."""
    global autonomous_manager, current_command
    
    if autonomous_manager:
        autonomous_manager.stop_autonomous_execution()
    
    current_command = 'stop'
    motor.stop()
    
    return {'status': 'stopped'}


@app.route('/emergency-stop', methods=['POST'])
def emergency_stop():
    """Emergency stop: force-stop autonomous and kill motors immediately."""
    global autonomous_manager, current_command
    try:
        if autonomous_manager:
            # Force immediate stop and clear execution state
            try:
                autonomous_manager.force_stop = True
                autonomous_manager.is_executing = False
                autonomous_manager.is_autonomous = False
                autonomous_manager.status = 'idle'
            except Exception:
                pass
        current_command = 'stop'
        if getattr(motor, 'hard_stop', None):
            motor.hard_stop()
        else:
            motor.stop()
        return {'status': 'emergency-stopped'}
    except Exception as e:
        return {'error': str(e)}, 500



@app.route('/autonomous/status', methods=['GET'])
def autonomous_route_status():
    """Get current autonomous navigation status."""
    global autonomous_manager
    
    if autonomous_manager:
        return autonomous_manager.get_status()
    
    return {
        'status': 'idle',
        'current_waypoint': 0,
        'total_waypoints': 0,
        'progress': 0,
        'path': [],
        'obstacles': []
    }


@app.route('/autonomous/servo-on-detection', methods=['POST'])
def set_servo_on_detection():
    """Enable/disable servo triggering on obstacle detection."""
    global autonomous_manager
    
    try:
        data = request.get_json()
        enabled = data.get('enabled', True)
        
        if autonomous_manager:
            result = autonomous_manager.set_servo_enabled(enabled)
            return result
        
        return {'error': 'Autonomous manager not initialized'}, 500
    
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/autonomous/speed-limits', methods=['GET', 'POST'])
def autonomous_speed_limits():
    """Get or set autonomous speed limits."""
    global autonomous_manager

    if not autonomous_manager:
        return {'error': 'Autonomous manager not initialized'}, 500

    if request.method == 'GET':
        status = autonomous_manager.get_status()
        return {
            'min_autonomous_speed': autonomous_manager.min_speed,
            'max_autonomous_speed': autonomous_manager.max_speed
        }

    try:
        data = request.get_json()
        min_speed = data.get('min_autonomous_speed')
        max_speed = data.get('max_autonomous_speed')
        if min_speed is None or max_speed is None:
            return {'error': 'min_autonomous_speed and max_autonomous_speed are required'}, 400
        return autonomous_manager.set_speed_limits(min_speed, max_speed)
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/autonomous/params', methods=['GET', 'POST'])
def autonomous_params():
    """Get or set runtime autonomous parameters used for safety and tuning.

    GET: returns current parameters
    POST: accepts JSON with any subset of parameters to update
    """
    global autonomous_manager

    if not autonomous_manager:
        return {'error': 'Autonomous manager not initialized'}, 500

    if request.method == 'GET':
        return {
            'obstacle_stop_distance': autonomous_manager.obstacle_stop_distance,
            'obstacle_slow_distance': autonomous_manager.obstacle_slow_distance,
            'proximity_threshold': autonomous_manager.proximity_threshold,
            'metal_drop_pause': getattr(autonomous_manager, 'metal_drop_pause', 1.5),
            'metal_drop_cooldown': getattr(autonomous_manager, 'metal_drop_cooldown', 3.0),
            'alignment_threshold_deg': getattr(autonomous_manager, 'alignment_threshold_deg', 8.0),
            'conservative_localization': getattr(autonomous_manager, 'conservative_localization', False),
            'heading_pid': {
                'kp': getattr(autonomous_manager, 'heading_pid_kp', 1.0),
                'ki': getattr(autonomous_manager, 'heading_pid_ki', 0.0),
                'kd': getattr(autonomous_manager, 'heading_pid_kd', 0.1)
            }
        }

    try:
        data = request.get_json() or {}
        # Apply safely
        if 'obstacle_stop_distance' in data:
            autonomous_manager.obstacle_stop_distance = float(data['obstacle_stop_distance'])
        if 'obstacle_slow_distance' in data:
            autonomous_manager.obstacle_slow_distance = float(data['obstacle_slow_distance'])
        if 'proximity_threshold' in data:
            autonomous_manager.proximity_threshold = float(data['proximity_threshold'])
        if 'metal_drop_pause' in data:
            autonomous_manager.metal_drop_pause = float(data['metal_drop_pause'])
        if 'metal_drop_cooldown' in data:
            autonomous_manager.metal_drop_cooldown = float(data['metal_drop_cooldown'])
        if 'alignment_threshold_deg' in data:
            autonomous_manager.alignment_threshold_deg = float(data['alignment_threshold_deg'])
        if 'conservative_localization' in data:
            try:
                autonomous_manager.conservative_localization = bool(data['conservative_localization'])
                if hasattr(autonomous_manager, '_sync_controller_params'):
                    autonomous_manager._sync_controller_params()
            except Exception:
                pass
        if 'heading_pid' in data:
            hp = data['heading_pid'] or {}
            autonomous_manager.heading_pid_kp = float(hp.get('kp', autonomous_manager.heading_pid_kp))
            autonomous_manager.heading_pid_ki = float(hp.get('ki', autonomous_manager.heading_pid_ki))
            autonomous_manager.heading_pid_kd = float(hp.get('kd', autonomous_manager.heading_pid_kd))

        return {'status': 'ok'}
    except Exception as e:
        print(f"[AUTONOMY] Params update failed: {e}")
        return {'error': str(e)}, 400


@app.route('/autonomous/resume', methods=['POST'])
def autonomous_resume():
    """Resume autonomous execution after auto-pause."""
    global autonomous_manager

    if not autonomous_manager:
        return {'error': 'Autonomous manager not initialized'}, 500
    result = autonomous_manager.resume_autonomous()
    if isinstance(result, dict) and result.get('error'):
        return result, 400
    return result


@app.route('/autonomous/grid/recenter', methods=['POST'])
def autonomous_recenter():
    """Set grid start to current robot position."""
    global autonomous_manager

    if not autonomous_manager:
        return {'error': 'Autonomous manager not initialized'}, 500
    grid = autonomous_manager.recenter_start()
    return {'status': 'recentered', 'grid': grid}


@app.route('/autonomous/obstacle-log', methods=['GET'])
def autonomous_obstacle_log():
    """Return recent obstacle/replan events."""
    global autonomous_manager

    if not autonomous_manager:
        return {'error': 'Autonomous manager not initialized'}, 500
    status = autonomous_manager.get_status()
    return {'log': status.get('obstacle_log', [])}


@app.route('/mode/switch', methods=['POST'])
def switch_mode():
    """Switch between manual and autonomous mode."""
    global autonomous_manager, current_command
    
    try:
        data = request.get_json()
        mode = data.get('mode', 'manual').lower()
        
        if not autonomous_manager:
            return {'error': 'Autonomous manager not initialized'}, 500
        
        if mode == 'autonomous':
            current_command = 'stop'
            motor.stop()
            result = autonomous_manager.switch_to_autonomous()
            return result
        elif mode == 'manual':
            result = autonomous_manager.switch_to_manual()
            current_command = 'stop'
            return result
        else:
            return {'error': f'Unknown mode: {mode}'}, 400
    
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/autonomous/mode', methods=['GET'])
def get_mode():
    """Get current mode (autonomous or manual)."""
    global autonomous_manager
    
    if autonomous_manager:
        status = autonomous_manager.get_status()
        return {'mode': status['mode']}
    
    return {'mode': 'unknown'}


def run(host='0.0.0.0', port=5000, debug=False):
    initialize_system()
    if SOCKETIO_AVAILABLE and socketio:
        socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
    else:
        app.run(host=host, port=port, debug=debug)
