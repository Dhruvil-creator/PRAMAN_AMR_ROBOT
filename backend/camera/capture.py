"""Safe camera capture helper used by metal/PIR triggers.

Provides capture_image(save_path=None) that returns filename or None.
"""
import time
import os

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    Picamera2 = None
    PICAMERA2_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except Exception:
    cv2 = None
    CV2_AVAILABLE = False


def capture_image(save_path: str = None, resolution=(640, 480)):
    """Capture a single image and return the path, or None on failure."""
    ts = int(time.time())
    if save_path is None:
        save_path = f"/tmp/capture_{ts}.jpg"

    try:
        if PICAMERA2_AVAILABLE and Picamera2 is not None:
            cam = Picamera2()
            config = cam.create_preview_configuration(main={'size': resolution})
            cam.configure(config)
            cam.start()
            frame = cam.capture_array()
            cam.stop()
            try:
                import imageio
                imageio.imwrite(save_path, frame)
            except Exception:
                # try fallback using cv2
                try:
                    import cv2 as _cv
                    _cv.imwrite(save_path, frame)
                except Exception:
                    pass
            return save_path

        if CV2_AVAILABLE and cv2 is not None:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return None
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return None
            cv2.imwrite(save_path, frame)
            return save_path

    except Exception as e:
        print(f"[CAMERA] capture failed: {e}")
        try:
            if os.path.exists(save_path):
                os.remove(save_path)
        except Exception:
            pass
        return None

    return None
