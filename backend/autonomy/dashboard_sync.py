"""Dashboard sync helpers — build a serializable status dict and optionally emit via SocketIO if available.
"""
import time
from typing import Dict


def build_status(grid_manager, sensor_snapshot: dict, controller_status: dict) -> Dict:
    status = {
        'timestamp': time.time(),
        'grid': grid_manager.to_dict(),
        'sensors': sensor_snapshot,
        'controller': controller_status,
    }
    return status


def emit_status_via_socketio(status: Dict):
    try:
        # attempt to import server.socketio if present
        from backend import server
        if getattr(server, 'socketio', None) is not None:
            server.socketio.emit('autonomy_status', status, namespace='/dashboard')
            return True
    except Exception:
        pass
    return False
