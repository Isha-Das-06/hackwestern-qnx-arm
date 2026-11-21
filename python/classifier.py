"""What is sitting in a pocket: empty / egg / cup / block.

Runs the same on the laptop and on the QNX Pi (this Python app is the final version;
the old C++ code in src/ is only a backup).

How it works:
  1. Per pocket, a photo of the EMPTY pocket is stored ("b" key).
  2. Foreground = pixels that differ from that photo. Tiny foreground => Empty.
  3. Otherwise: shape + colour numbers from the biggest blob, compared against
     examples you captured (keys 1/2/3) with k-nearest-neighbours.
"""
import math

import cv2
import numpy as np

EMPTY, EGG, CUP, BLOCK, UNKNOWN = 0, 1, 2, 3, 4
NAMES = {EMPTY: "empty", EGG: "egg", CUP: "cup", BLOCK: "block", UNKNOWN: "unknown"}

NORM_SIDE = 96  # crops are rescaled so the long side is this many pixels
N_SCALAR = 12  # shape/colour numbers (standardised)
H_BINS, S_BINS = 8, 4  # hue x saturation histogram (appended as-is)
HIST_WEIGHT = 4.0

# Tuning knobs
DIFF_TH = 28.0  # Lab colour distance that counts as "changed"
EMPTY_FG_FRAC = 0.04  # less than 4% of the pocket changed -> empty
K = 3  # neighbours that vote
REJECT_DIST = 4.2  # nearest example further than this -> unknown (same object ~1.4-3.5, different ~3.8-6.4)


def _normalize_size(bgr):
    s = NORM_SIDE / max(bgr.shape[1], bgr.shape[0])
    w = max(8, round(bgr.shape[1] * s))
    h = max(8, round(bgr.shape[0] * s))
    return cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)


class PocketClassifier:
    def __init__(self):
        self.bg = {}  # pocket index -> photo of the empty pocket
        self.X = []  # feature vectors of the examples
        self.y = []  # their labels
        self.mu = np.zeros(N_SCALAR, np.float32)
        self.sd = np.ones(N_SCALAR, np.float32)

    # ------------------------------------------------------------ training
    def set_background(self, pocket, crop):
        self.bg[pocket] = _normalize_size(crop)

    def has_background(self, pocket):
        return pocket in self.bg

    def add_sample(self, label, pocket, crop):
        f, frac, _ = self._features(pocket, crop)
        if f is None:
            print(f"sample ignored: pocket {pocket + 1} looks empty (fg={frac:.3f})")
            return
        self.X.append(f)
        self.y.append(label)
        self._refit()
        print(f"sample: {NAMES[label]} from pocket {pocket + 1} (now {self.count(label)})")

    def count(self, label):
        return self.y.count(label)

    def clear_samples(self):
        self.X, self.y = [], []
        self._refit()

    def clear_label(self, label):
        keep = [i for i, v in enumerate(self.y) if v != label]
        self.X, self.y = [self.X[i] for i in keep], [self.y[i] for i in keep]
        self._refit()

    def clear_background(self):
        self.bg = {}

    def _refit(self):
        if not self.X:
            self.mu = np.zeros(N_SCALAR, np.float32)
            self.sd = np.ones(N_SCALAR, np.float32)
            return
        A = np.array(self.X, np.float32)[:, :N_SCALAR]
        self.mu = A.mean(0)
        # floor the spread so a feature with ~0 variance can't dominate
        self.sd = np.maximum(A.std(0), 0.05)

    # ------------------------------------------------------------ predict
    def predict(self, pocket, crop):
        """Returns (label, confidence 0..1, foreground fraction, mask)."""
        f, frac, mask = self._features(pocket, crop)
        if f is None:
            if self.has_background(pocket):
                return EMPTY, 1.0, frac, mask
            return UNKNOWN, 0.0, frac, mask
        if not self.X:
            return UNKNOWN, 0.0, frac, mask  # not trained yet
        A = np.array(self.X, np.float32)
        z = (A[:, :N_SCALAR] - f[:N_SCALAR]) / self.sd
        h = HIST_WEIGHT * (A[:, N_SCALAR:] - f[N_SCALAR:])
        d = np.sqrt((z * z).sum(1) + (h * h).sum(1))
        order = np.argsort(d)[: min(K, len(d))]
        votes = np.bincount([self.y[i] for i in order], minlength=5)
        best = int(votes.argmax())
        conf = votes[best] / len(order)
        if d[order[0]] > REJECT_DIST:
            best = UNKNOWN
        return best, float(conf), frac, mask

    # ------------------------------------------------------------ features
    def _features(self, pocket, crop_in):
        crop = _normalize_size(crop_in)
        blur = cv2.GaussianBlur(crop, (5, 5), 0)

        # --- which pixels changed vs the empty pocket ---
        if pocket in self.bg:
            bg = self.bg[pocket]
            if bg.shape != crop.shape:
                bg = cv2.resize(bg, (crop.shape[1], crop.shape[0]))
            a = cv2.cvtColor(blur, cv2.COLOR_BGR2Lab).astype(np.float32)
            b = cv2.cvtColor(cv2.GaussianBlur(bg, (5, 5), 0), cv2.COLOR_BGR2Lab).astype(np.float32)
            d = (a - b) ** 2
            # lightness counts less, so soft shadows aren't "objects"
            dist = np.sqrt(0.35 * d[..., 0] + d[..., 1] + d[..., 2])
            mask = (dist > DIFF_TH).astype(np.uint8) * 255
        else:
            gray = cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        blob = np.zeros(mask.shape, np.uint8)
        if not contours:
            return None, 0.0, blob
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        frac = area / (crop.shape[0] * crop.shape[1])
        cv2.drawContours(blob, [c], -1, 255, cv2.FILLED)
        if frac < EMPTY_FG_FRAC:
            return None, frac, blob

        # --- shape (doesn't change when the object rotates) ---
        peri = cv2.arcLength(c, True)
        hull_area = max(1.0, cv2.contourArea(cv2.convexHull(c)))
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        rr_area = max(1.0, rw * rh)
        rr_aspect = min(rw, rh) / max(1.0, max(rw, rh))
        poly = cv2.approxPolyDP(c, 0.03 * peri, True)
        circularity = 4 * math.pi * area / max(1.0, peri * peri)
        solidity = area / hull_area
        extent = area / rr_area
        vertices = min(len(poly), 12) / 12.0

        # --- colour of the blob ---
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
        on = blob > 0
        H = hsv[..., 0][on].astype(np.float32) * (2 * math.pi / 180.0)
        S = hsv[..., 1][on].astype(np.float32) / 255.0
        V = hsv[..., 2]
        w = S.sum() + 1e-6
        hx, hy = float((S * np.cos(H)).sum() / w), float((S * np.sin(H)).sum() / w)
        mean_s = float(S.mean())
        mean_v = float(V[on].mean()) / 255.0

        # cup from above = bright rim around a darker inside
        er = max(1, round(0.25 * math.sqrt(area / math.pi)))
        core = cv2.erode(blob, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * er + 1, 2 * er + 1)))
        ring = cv2.bitwise_and(blob, cv2.bitwise_not(core))
        v_core = float(V[core > 0].mean()) if (core > 0).any() else 0.0
        v_ring = float(V[ring > 0].mean()) if (ring > 0).any() else 1.0
        core_ring = v_core / max(1.0, v_ring)

        # edges inside the blob (block corners vs smooth egg)
        edges = cv2.Canny(cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY), 50, 150)
        edge_density = np.count_nonzero(edges[on]) / max(1.0, area)

        f = [frac, circularity, solidity, extent, rr_aspect, vertices,
             hx, hy, mean_s, mean_v, core_ring, edge_density]
        assert len(f) == N_SCALAR

        hist = cv2.calcHist([hsv], [0, 1], blob, [H_BINS, S_BINS], [0, 180, 0, 256])
        hist /= max(1.0, float(hist.sum()))
        return np.array(f + hist.flatten().tolist(), np.float32), frac, blob

    # ------------------------------------------------------------ save/load
    def save(self, path):
        n_feat = N_SCALAR + H_BINS * S_BINS
        X = np.array(self.X, np.float32) if self.X else np.zeros((0, n_feat), np.float32)
        np.savez(path,
                 bg_keys=np.array(list(self.bg.keys()), np.int32),
                 **{f"bg_{k}": v for k, v in self.bg.items()},
                 X=X,
                 y=np.array(self.y, np.int32))

    def load(self, path):
        try:
            data = np.load(path)
        except (FileNotFoundError, OSError):
            return False
        self.bg = {int(k): data[f"bg_{int(k)}"] for k in data["bg_keys"]}
        self.X = [row for row in data["X"]]
        self.y = [int(v) for v in data["y"]]
        self._refit()
        return True
