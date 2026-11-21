"""Hand tracker without mediapipe: runs on QNX.

Python port of the QNX AI Workshop's handtracking.cpp (Apache-2.0, BlackBerry):
the same two models (palm_detection_lite + hand_landmark_lite), the same
anchors, thresholds, crop maths and tracking. Only the inference engine is
picked at runtime:

  - tflite_runtime  (the QNX package python3-tflite-runtime)  <- on the Pi
  - ai_edge_litert / tensorflow.lite, if installed
  - OpenCV DNN's TFLite reader                                 <- laptop fallback

Returns hands in the same shape pointing.py already uses: 21 (x, y) pixels per
hand plus 21 (x, y, z) 3D "world" points (metres) for the pointing check.
"""
import math
import os

import cv2
import numpy as np

DET_SIZE = 192
LM_SIZE = 224
NMS_TH = 0.3
ROI_SCALE = 2.6
ROI_SHIFT_Y = -0.5


# ---------------------------------------------------------------- engines
class _TfliteModel:
    def __init__(self, path, threads, Interpreter):
        self.it = Interpreter(model_path=path, num_threads=threads)
        self.it.allocate_tensors()
        self.inp = self.it.get_input_details()[0]["index"]
        self.outs = [d["index"] for d in self.it.get_output_details()]
        self.name = "tflite"

    def run(self, x):  # x: 1 x H x W x 3 float32 (NHWC)
        self.it.set_tensor(self.inp, x)
        self.it.invoke()
        return [self.it.get_tensor(i).reshape(-1) for i in self.outs]


class _CvDnnModel:
    """OpenCV reads .tflite too (verified with these models): it wants an NCHW
    blob and outputs requested by their TFLite names Identity, Identity_1, ..."""

    def __init__(self, path):
        engine = getattr(cv2.dnn, "ENGINE_CLASSIC", None)
        self.net = (cv2.dnn.readNetFromTFLite(path, engine=engine) if engine is not None
                    else cv2.dnn.readNetFromTFLite(path))
        have = set(self.net.getLayerNames())
        self.names = []
        i = 0
        while True:
            n = "Identity" if i == 0 else f"Identity_{i}"
            if n not in have:
                break
            self.names.append(n)
            i += 1
        if not self.names:
            self.names = list(self.net.getUnconnectedOutLayersNames())
        self.name = "opencv-dnn " + cv2.__version__

    def run(self, x):
        self.net.setInput(np.ascontiguousarray(x.transpose(0, 3, 1, 2)))
        return [o.reshape(-1) for o in self.net.forward(self.names)]


def _load(path, threads, backend):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if backend in ("auto", "tflite"):
        for mod in ("tflite_runtime.interpreter", "ai_edge_litert.interpreter"):
            try:
                m = __import__(mod, fromlist=["Interpreter"])
                return _TfliteModel(path, threads, m.Interpreter)
            except ImportError:
                pass
        try:
            import tensorflow as tf  # noqa: F401
            return _TfliteModel(path, threads, tf.lite.Interpreter)
        except ImportError:
            if backend == "tflite":
                raise
    return _CvDnnModel(path)


# ---------------------------------------------------------------- helpers
def _anchors():
    a = []
    strides = [8, 16, 16, 16]
    layer = 0
    while layer < len(strides):
        last, per = layer, 0
        while last < len(strides) and strides[last] == strides[layer]:
            per += 2
            last += 1
        fm = (DET_SIZE + strides[layer] - 1) // strides[layer]
        for y in range(fm):
            for x in range(fm):
                a += [((x + 0.5) / fm, (y + 0.5) / fm)] * per
        layer = last
    return np.array(a, np.float32)  # 2016 x 2


def _iou(a, b):  # boxes as (cx, cy, w, h)
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    uni = a[2] * a[3] + b[2] * b[3] - inter
    return inter / uni if uni > 0 else 0.0


def _roi_from_landmarks(pts, track_scale):
    wrist, mid = pts[0], pts[9]
    angle = math.pi / 2 - math.atan2(-(mid[1] - wrist[1]), mid[0] - wrist[0])
    ca, sa = math.cos(-angle), math.sin(-angle)
    P = np.array(pts, np.float64)
    rx = P[:, 0] * ca - P[:, 1] * sa
    ry = P[:, 0] * sa + P[:, 1] * ca
    cxr, cyr = (rx.min() + rx.max()) / 2, (ry.min() + ry.max()) / 2
    cb, sb = math.cos(angle), math.sin(angle)
    center = (cxr * cb - cyr * sb, cxr * sb + cyr * cb)
    size = max(rx.max() - rx.min(), ry.max() - ry.min()) * track_scale
    return center, angle, size


# ---------------------------------------------------------------- tracker
class HandTracker:
    def __init__(self, models_dir, det_th=0.7, presence_th=0.5, track_scale=2.0,
                 tracking=True, redetect_every=15, threads=3, backend="auto"):
        self.det = _load(os.path.join(models_dir, "palm_detection_lite.tflite"), threads, backend)
        self.lm = _load(os.path.join(models_dir, "hand_landmark_lite.tflite"), threads, backend)
        self.backend = self.det.name
        self.det_th, self.presence_th = det_th, presence_th
        self.track_scale, self.tracking = track_scale, tracking
        self.redetect_every = redetect_every
        self.anchors = _anchors()
        self.tracked = []
        self.since_detect = 0
        self.ran_detector = False

    def detect(self, bgr, max_hands=2):
        """Returns a list of hands: {"pts": [(x,y)]*21, "world": [(x,y,z)]*21 or None, "score": p}."""
        self.ran_detector = False
        self.since_detect += 1
        sweep_due = len(self.tracked) < max_hands and self.since_detect >= self.redetect_every

        # Fast path: follow last frame's hands instead of running the palm detector.
        if self.tracking and self.tracked and not sweep_due:
            hands = []
            for roi in self.tracked:
                h = self._landmarks(bgr, *roi)
                if h:
                    hands.append(h)
                if len(hands) >= max_hands:
                    break
            if hands:
                self.tracked = [_roi_from_landmarks(h["pts"], self.track_scale) for h in hands]
                return hands
            self.tracked = []

        self.ran_detector = True
        self.since_detect = 0
        H, W = bgr.shape[:2]

        # ---- palm detection: letterbox to 192x192 RGB in [0,1] ----
        scale = min(DET_SIZE / W, DET_SIZE / H)
        nw, nh = round(W * scale), round(H * scale)
        px, py = (DET_SIZE - nw) // 2, (DET_SIZE - nh) // 2
        canvas = np.zeros((DET_SIZE, DET_SIZE, 3), np.uint8)
        canvas[py:py + nh, px:px + nw] = cv2.resize(bgr, (nw, nh))
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32)[None] / 255.0
        out = self.det.run(x)
        boxes = out[0].reshape(-1, 18)
        scores = 1.0 / (1.0 + np.exp(-np.clip(out[1].reshape(-1), -100, 100)))

        keep_idx = np.where(scores >= self.det_th)[0]
        dets = []
        for i in keep_idx:
            b = boxes[i]
            ax, ay = self.anchors[i]
            dets.append({
                "score": float(scores[i]),
                "box": (b[0] / DET_SIZE + ax, b[1] / DET_SIZE + ay, b[2] / DET_SIZE, b[3] / DET_SIZE),
                "kp": [(b[4 + 2 * k] / DET_SIZE + ax, b[5 + 2 * k] / DET_SIZE + ay) for k in range(7)],
            })
        dets.sort(key=lambda d: -d["score"])
        keep = []
        for d in dets:
            if all(_iou(d["box"], k["box"]) <= NMS_TH for k in keep):
                keep.append(d)
            if len(keep) >= max_hands:
                break

        def to_px(u, v):
            return ((u * DET_SIZE - px) / scale, (v * DET_SIZE - py) / scale)

        hands = []
        for d in keep:
            kp0, kp2 = to_px(*d["kp"][0]), to_px(*d["kp"][2])
            cx, cy = to_px(d["box"][0], d["box"][1])
            bw, bh = d["box"][2] * DET_SIZE / scale, d["box"][3] * DET_SIZE / scale
            angle = math.pi / 2 - math.atan2(-(kp2[1] - kp0[1]), kp2[0] - kp0[0])
            long_side = max(bw, bh)
            cx += long_side * (-ROI_SHIFT_Y * math.sin(angle))
            cy += long_side * (ROI_SHIFT_Y * math.cos(angle))
            h = self._landmarks(bgr, (cx, cy), angle, long_side * ROI_SCALE)
            if h:
                hands.append(h)

        self.tracked = ([_roi_from_landmarks(h["pts"], self.track_scale) for h in hands]
                        if self.tracking else [])
        return hands

    def _landmarks(self, bgr, center, angle, size):
        s = LM_SIZE / size
        ca, sa = math.cos(-angle) * s, math.sin(-angle) * s
        M = np.array([[ca, -sa, LM_SIZE / 2 - (ca * center[0] - sa * center[1])],
                      [sa, ca, LM_SIZE / 2 - (sa * center[0] + ca * center[1])]], np.float64)
        crop = cv2.warpAffine(bgr, M, (LM_SIZE, LM_SIZE), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
        x = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32)[None] / 255.0
        out = self.lm.run(x)
        presence = float(out[1][0])  # already a probability in this export
        if presence < self.presence_th:
            return None
        lms = out[0].reshape(21, 3)
        Minv = cv2.invertAffineTransform(M)
        pts = [(Minv[0, 0] * u + Minv[0, 1] * v + Minv[0, 2],
                Minv[1, 0] * u + Minv[1, 1] * v + Minv[1, 2]) for u, v, _ in lms]
        world = [tuple(map(float, p)) for p in out[3].reshape(21, 3)] if len(out) > 3 else None
        return {"pts": pts, "world": world, "score": presence}
