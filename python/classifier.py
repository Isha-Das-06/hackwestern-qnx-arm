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
REJECT_DIST = 4.0  # nearest example further than this -> unknown
# How much each shape/colour number may normally wobble for the SAME object (fixed, so it
# works from the very first examples; fitting it to a few near-identical examples made
# everything else look "different").
#        size  circ  solid extent aspect verts  hx   hy   sat  bright core_ring edges
SCALE = [0.30, 0.12, 0.08, 0.08,  0.15,  0.15, 0.20, 0.20, 0.08, 0.10, 0.20,    0.06]
FILE_VERSION = 2   # v2 saves the example pictures, so examples survive feature changes
# Robustness to things around the holder (arm parts, wires, a hand at the edge)
MAX_SHIFT = 4  # camera/tray may have moved this many pixels (at NORM_SIDE scale) since the photo
FOCUS_R = 1.6  # only look within this many holder-radii of the holder centre
BG_LEARN = 0.03  # empty box: unchanged pixels slowly follow lighting changes
BG_SAFE_TH = 14.0  # ...only pixels closer than this to the photo (half the "changed" level)
BG_MAX_CHANGED = 0.02  # ...and only while under 2% of the box differs at all


def _normalize_size(bgr):
    s = NORM_SIDE / max(bgr.shape[1], bgr.shape[0])
    w = max(8, round(bgr.shape[1] * s))
    h = max(8, round(bgr.shape[0] * s))
    return cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)


class PocketClassifier:
    def __init__(self):
        self.bg = {}  # pocket index -> photo of the empty pocket
        self._holders = {}  # pocket index -> (cx, cy, r) of the holder ring in the photo
        self.X = []  # feature vectors of the examples
        self.y = []  # their labels
        self.crops = []  # the example pictures (normalized) ...
        self.pockets = []  # ... and which box each came from, to recompute features
        self.mu = np.zeros(N_SCALAR, np.float32)
        self.sd = np.ones(N_SCALAR, np.float32)

    # ------------------------------------------------------------ training
    def set_background(self, pocket, crop):
        self.bg[pocket] = _normalize_size(crop)
        self._holders.pop(pocket, None)

    def _holder(self, pocket, shape):
        """(cx, cy, r) of the black holder ring, found once in the empty photo.
        Falls back to the middle of the box if no dark ring is found."""
        h, w = shape[:2]
        if pocket in self._holders:
            return self._holders[pocket]
        found = None
        bg = self.bg.get(pocket)
        if bg is not None and bg.shape[:2] == (h, w):
            v = cv2.cvtColor(cv2.GaussianBlur(bg, (5, 5), 0), cv2.COLOR_BGR2HSV)[..., 2]
            dark = cv2.morphologyEx((v < 70).astype(np.uint8) * 255, cv2.MORPH_CLOSE,
                                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
            cs, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cs:
                c = max(cs, key=cv2.contourArea)
                (x, y), r = cv2.minEnclosingCircle(c)
                # a plausible holder ring: not tiny, not the whole box, near the middle
                # of the box (not some dark thing in a corner), and hollow (lighter inside)
                inner = np.zeros(dark.shape, np.uint8)
                cv2.circle(inner, (round(x), round(y)), max(1, round(0.45 * r)), 255, cv2.FILLED)
                hollow = (inner > 0).any() and float((dark[inner > 0] > 0).mean()) < 0.5
                if (cv2.contourArea(c) > 0.03 * h * w and 0.12 * min(h, w) < r < 0.6 * max(h, w)
                        and abs(x - w / 2) < 0.22 * w and abs(y - h / 2) < 0.22 * h and hollow):
                    found = (x, y, r)
        if found is None:
            found = (w / 2, h / 2, 0.35 * min(h, w))
        self._holders[pocket] = found
        return found

    def _changed(self, pocket, blur):
        """Per-pixel colour distance to the empty photo, tolerant to small shifts:
        first the best overall shift, then the closest of the 3x3 neighbours."""
        bg = self.bg[pocket]
        if bg.shape != blur.shape:
            bg = cv2.resize(bg, (blur.shape[1], blur.shape[0]))
        a = cv2.cvtColor(blur, cv2.COLOR_BGR2Lab).astype(np.float32)
        b = cv2.cvtColor(cv2.GaussianBlur(bg, (5, 5), 0), cv2.COLOR_BGR2Lab).astype(np.float32)
        h, w = a.shape[:2]
        p = MAX_SHIFT + 1
        bp = cv2.copyMakeBorder(b, p, p, p, p, cv2.BORDER_REPLICATE)
        wts = np.array([0.35, 1.0, 1.0], np.float32)

        def dist(dx, dy):
            d = a - bp[p + dy:p + dy + h, p + dx:p + dx + w]
            return np.sqrt((d * d * wts).sum(2))

        # best overall shift: slide the middle of the live picture over the photo
        ga = cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY)
        gb = cv2.copyMakeBorder(cv2.cvtColor(cv2.GaussianBlur(bg, (5, 5), 0), cv2.COLOR_BGR2GRAY),
                                MAX_SHIFT, MAX_SHIFT, MAX_SHIFT, MAX_SHIFT, cv2.BORDER_REPLICATE)
        res = cv2.matchTemplate(gb, ga, cv2.TM_SQDIFF)
        _, _, (mx, my), _ = cv2.minMaxLoc(res)
        best = (mx - MAX_SHIFT, my - MAX_SHIFT)
        out = None
        for dx in range(best[0] - 1, best[0] + 2):
            for dy in range(best[1] - 1, best[1] + 2):
                d = dist(max(-p, min(p, dx)), max(-p, min(p, dy)))
                out = d if out is None else np.minimum(out, d)
        return out

    def _learn_background(self, pocket, crop_in, mask):
        """Box is empty: let the unchanged pixels of the photo follow slow lighting drift."""
        crop = _normalize_size(crop_in)
        bg = self.bg[pocket]
        if bg.shape != crop.shape:
            return
        dist = getattr(self, "_dist", None)
        if dist is None or dist.shape != crop.shape[:2]:
            return
        # Only pixels that clearly match the photo follow the light. Anything that differs
        # (even a little, anywhere in the box) is never blended in - otherwise an object
        # put down slowly could fade into the "empty" photo and the box would stay "empty".
        changed = (dist > BG_SAFE_TH).astype(np.uint8)
        if changed.mean() > BG_MAX_CHANGED:
            return  # something is (partly) there: don't learn at all
        keep = cv2.dilate(changed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
        new = cv2.addWeighted(bg.astype(np.float32), 1 - BG_LEARN, crop.astype(np.float32), BG_LEARN, 0)
        new[keep] = bg[keep]
        self.bg[pocket] = new.round().astype(np.uint8)

    def has_background(self, pocket):
        return pocket in self.bg

    def add_sample(self, label, pocket, crop):
        f, frac, _ = self._features(pocket, crop)
        if f is None:
            print(f"sample ignored: pocket {pocket + 1} looks empty (fg={frac:.3f})")
            return
        self.X.append(f)
        self.y.append(label)
        self.crops.append(_normalize_size(crop))
        self.pockets.append(pocket)
        self._refit()
        print(f"sample: {NAMES[label]} from pocket {pocket + 1} (now {self.count(label)})")

    def count(self, label):
        return self.y.count(label)

    def clear_samples(self):
        self.X, self.y, self.crops, self.pockets = [], [], [], []
        self._refit()

    def clear_label(self, label):
        keep = [i for i, v in enumerate(self.y) if v != label]
        self.X, self.y = [self.X[i] for i in keep], [self.y[i] for i in keep]
        self.crops = [self.crops[i] for i in keep]
        self.pockets = [self.pockets[i] for i in keep]
        self._refit()

    def clear_background(self):
        self.bg = {}
        self._holders = {}

    def _refit(self):
        self.sd = np.array(SCALE, np.float32)

    # ------------------------------------------------------------ predict
    def predict(self, pocket, crop):
        """Returns (label, confidence 0..1, foreground fraction, mask)."""
        f, frac, mask = self._features(pocket, crop)
        if f is None:
            if self.has_background(pocket):
                self._learn_background(pocket, crop, mask)
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
            # lightness counts less (inside _changed), so soft shadows aren't "objects"
            self._dist = self._changed(pocket, blur)  # kept for _learn_background
            mask = (self._dist > DIFF_TH).astype(np.uint8) * 255
        else:
            gray = cv2.cvtColor(blur, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))

        # Only the area around the holder counts: arm parts, wires or a hand near the
        # edge of the drawn box are ignored.
        if pocket in self.bg:
            cx, cy, r = self._holder(pocket, crop.shape)
            focus = np.zeros(mask.shape, np.uint8)
            cv2.circle(focus, (round(cx), round(cy)), round(FOCUS_R * r), 255, cv2.FILLED)
            mask = cv2.bitwise_and(mask, focus)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        blob = np.zeros(mask.shape, np.uint8)
        if not contours:
            return None, 0.0, blob
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        frac = area / (crop.shape[0] * crop.shape[1])
        # size compared to the holder ring: the same in every box, whatever size box was drawn
        if pocket in self.bg:
            ring_r = self._holder(pocket, crop.shape)[2]
            size = area / (math.pi * ring_r * ring_r)
        else:
            size = frac * 4
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

        f = [size, circularity, solidity, extent, rr_aspect, vertices,
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
                 version=np.array(FILE_VERSION),
                 bg_keys=np.array(list(self.bg.keys()), np.int32),
                 **{f"bg_{k}": v for k, v in self.bg.items()},
                 X=X,
                 y=np.array(self.y, np.int32),
                 ex_pockets=np.array(self.pockets, np.int32),
                 **{f"ex_{i}": c for i, c in enumerate(self.crops)})

    def load(self, path):
        try:
            data = np.load(path)
        except (FileNotFoundError, OSError):
            return False
        self.bg = {int(k): data[f"bg_{int(k)}"] for k in data["bg_keys"]}
        self._holders = {}
        self._refit()
        self.X, self.y, self.crops, self.pockets = [], [], [], []
        if "version" not in data.files or int(data["version"]) < FILE_VERSION:
            if len(data["y"]):
                print("classifier: examples from an older version were dropped - please teach again")
            return True
        # recompute features from the saved pictures, so they always match this code
        for i, (lab, pk) in enumerate(zip(data["y"], data["ex_pockets"])):
            crop = data[f"ex_{i}"]
            f, _, _ = self._features(int(pk), crop)
            if f is not None:
                self.X.append(f)
                self.y.append(int(lab))
                self.crops.append(crop)
                self.pockets.append(int(pk))
        return True
