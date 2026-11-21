"""Quick check on the QNX Pi: libraries, hand models, camera.

Run from the pickvision folder:  python3 python/pi_test.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import cv2
import numpy as np

print("== versions")
print("python", sys.version.split()[0], "| numpy", np.__version__, "| opencv", cv2.__version__)
try:
    import tflite_runtime
    print("tflite_runtime", getattr(tflite_runtime, "__version__", "?"))
except ImportError as e:
    print("tflite_runtime MISSING", e)

print("== hand models (TFLite)")
from handtrack_tflite import HandTracker
t = HandTracker(os.path.join(ROOT, "models"), backend="tflite", tracking=False)
print("backend:", t.backend)
img = np.zeros((480, 640, 3), np.uint8)
times = []
for _ in range(5):
    s = time.perf_counter()
    t.detect(img, 1)
    times.append((time.perf_counter() - s) * 1000)
print("palm detector on a blank frame: %.0f ms (first), %.0f ms (avg of rest)"
      % (times[0], sum(times[1:]) / len(times[1:])))
# Landmark model directly, to time the per-hand step too
x = np.zeros((1, 224, 224, 3), np.float32)
s = time.perf_counter()
for _ in range(5):
    t.lm.run(x)
print("landmark model: %.0f ms per run" % ((time.perf_counter() - s) * 200))

print("== camera via OpenCV")
try:
    print("camera backends built in:",
          [cv2.videoio_registry.getBackendName(b) for b in cv2.videoio_registry.getCameraBackends()])
except Exception as e:
    print("could not list backends:", e)
got = None
for i in range(4):
    c = cv2.VideoCapture(i)
    ok, f = (c.read() if c.isOpened() else (False, None))
    print(f"VideoCapture({i}): opened={c.isOpened()} frame={'%dx%d' % (f.shape[1], f.shape[0]) if ok else 'none'}")
    if ok and got is None:
        got = f
    c.release()
if got is not None:
    out = os.path.join(ROOT, "pi_camera_test.jpg")
    cv2.imwrite(out, got)
    print("saved a camera frame to", out)
    hands = t.detect(got, 2)
    print("hands in that frame:", len(hands))
else:
    print("RESULT: OpenCV cannot open the camera from Python on this QNX -> need the camapi bridge")
print("== done")
