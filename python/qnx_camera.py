"""Camera on QNX: reads frames from the pv_cam bridge (qnx/pv_cam.c).

OpenCV's VideoCapture can't open cameras on QNX, so pv_cam uses QNX's own
camera API and streams frames on a pipe. This class looks like cv2.VideoCapture
(isOpened / read / release) so the rest of the app doesn't care which one it has.

Only the newest frame is kept: if the app is slower than the camera, old frames
are dropped instead of piling up (no growing delay).
"""
import os
import struct
import subprocess
import threading
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BRIDGE = os.path.join(os.path.dirname(HERE), "qnx", "pv_cam")
FMT_NV12, FMT_YUYV, FMT_RGB8888 = 1, 2, 3


def on_qnx():
    return os.uname().sysname.upper().startswith("QNX") if hasattr(os, "uname") else False


class QnxCamera:
    def __init__(self, unit=None, size=(640, 480), bridge=DEFAULT_BRIDGE):
        args = [bridge, "-r", f"{size[0]}x{size[1]}"]
        if unit is not None and unit >= 0:
            args += ["-u", str(unit)]
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, bufsize=0)
        self.cv = threading.Condition()
        self.frame = None
        self.seq = 0
        self.last_read = 0
        self.alive = True
        threading.Thread(target=self._reader, daemon=True).start()

    def _read_exact(self, n):
        buf = bytearray(n)
        view = memoryview(buf)
        got = 0
        while got < n:
            k = self.proc.stdout.readinto(view[got:])
            if not k:
                return None
            got += k
        return buf

    def _reader(self):
        try:
            while True:
                hdr = self._read_exact(16)
                if hdr is None or hdr[:4] != b"PVF1":
                    break
                fmt, _, w, h = struct.unpack("<HHII", hdr[4:])
                n = {FMT_NV12: w * h * 3 // 2, FMT_YUYV: w * h * 2, FMT_RGB8888: w * h * 4}.get(fmt)
                if n is None:
                    break
                data = self._read_exact(n)
                if data is None:
                    break
                a = np.frombuffer(data, np.uint8)
                if fmt == FMT_NV12:
                    bgr = cv2.cvtColor(a.reshape(h * 3 // 2, w), cv2.COLOR_YUV2BGR_NV12)
                elif fmt == FMT_YUYV:
                    bgr = cv2.cvtColor(a.reshape(h, w, 2), cv2.COLOR_YUV2BGR_YUY2)
                else:
                    bgr = np.ascontiguousarray(a.reshape(h, w, 4)[:, :, :3])
                with self.cv:
                    self.frame = bgr
                    self.seq += 1
                    self.cv.notify_all()
        finally:
            with self.cv:
                self.alive = False
                self.cv.notify_all()

    def isOpened(self, timeout=5.0):
        """True once the first frame has arrived (waits up to `timeout` s)."""
        with self.cv:
            self.cv.wait_for(lambda: self.seq > 0 or not self.alive, timeout)
            return self.seq > 0

    def read(self, timeout=2.0):
        """Waits for a frame newer than the last one returned."""
        with self.cv:
            self.cv.wait_for(lambda: self.seq != self.last_read or not self.alive, timeout)
            if self.frame is None or self.seq == self.last_read:
                return False, None
            self.last_read = self.seq
            return True, self.frame

    def set(self, *_):  # cv2.VideoCapture compatibility; size is chosen at start
        return False

    def release(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


if __name__ == "__main__":
    import sys
    unit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    cam = QnxCamera(unit)
    if not cam.isOpened():
        raise SystemExit("no frames from pv_cam")
    t0, n = time.time(), 0
    while time.time() - t0 < 3:
        ok, f = cam.read()
        n += ok
    print(f"{n / 3:.1f} fps, frame {f.shape[1]}x{f.shape[0]}")
    cv2.imwrite("qnx_camera_test.jpg", f)
    print("saved qnx_camera_test.jpg")
    cam.release()
