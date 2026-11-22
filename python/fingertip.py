"""Fingertip finder for when the palm is outside the camera picture.

The hand model needs to see a palm. With the tray filling the picture, often only
a finger reaches in from the side. This finds that finger without a palm:

  1. It learns what the scene normally looks like (a slowly updated background),
     and allows for the camera's auto-exposure making the whole picture brighter/darker.
  2. Skin-coloured pixels that differ from it = a hand/finger.
  3. Only blobs that come in from an edge of the picture count (a hand reaches
     in from outside; the robot itself doesn't change colour to skin).
  4. The fingertip = the point of the blob furthest from where it enters,
     and it must be over one of the boxes (the only place pointing matters).

Works at a small size so it costs a few ms on the Pi. Returns 21 points in the
same shape as the hand model, so the rest of the app (boxes covered by the hand,
fingertip smoothing) works unchanged. A finger reaching in counts as pointing.
"""
import cv2
import numpy as np

SMALL_W = 160
DIFF_TH = 22.0        # colour distance (Lab, lightness counts less) that counts as changed
LEARN_BG = 0.05       # how fast unchanged pixels follow the scene (lighting drift)
LEARN_FG = 0.006      # changed pixels are absorbed slowly (a finger held for a few s stays)
STATIC_FRAMES = 40    # ...but a patch changed this many frames in a row (~6 s) without moving
LEARN_STATIC = 0.08   # is the scene, not a hand (e.g. table a hand or wire uncovered): learn it fast
MIN_AREA = 0.0012     # blob must cover at least this much of the picture...
MIN_REACH = 0.03      # ...and reach at least this far in (fraction of picture width)
TIP_R = 0.06          # look at the blob within this radius (of picture width) of its tip...
TIP_MAX_FILL = 0.38   # ...a finger fills ~15-25% of that circle, a fist/hand holding something ~50%
AIM_AHEAD = 0.15      # the tip may be this far (of picture width) short of the box it points at
COVER_FRAC = 0.03     # hand pixels over more than this much of a box = "hand in the way"
FINGER_LEN = 0.10     # knuckle -> tip length used for aiming (of picture width)
EDGE = 3              # px (at small size) from the border that counts as "touching"
BOX_PAD = 0.0         # the tip (or the point it aims at) must be inside a box
WARMUP = 10           # frames used to learn the empty scene first


def _skin(small_bgr):
    """Skin-ish pixels (YCrCb box that fits most skin tones under room light)."""
    ycc = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2YCrCb)
    return cv2.inRange(ycc, (40, 135, 80), (255, 180, 130))


class FingertipFinder:
    def __init__(self):
        self.bg = None
        self.n = 0
        self.age = None    # per pixel: frames in a row it has looked changed
        self.mask = None   # last foreground mask (small size), for debugging
        self.hand_mask = None  # skin reaching in from an edge (small size): the whole hand/arm
        self.scale = 1.0

    def reset(self):
        self.bg, self.n = None, 0

    def covers(self, rect):
        """True if part of a hand reaching in (not just the fingertip) is over this
        pixel rect (x0, y0, x1, y1) - then what's in that box can't be judged yet."""
        if self.hand_mask is None:
            return False
        s = self.scale
        x0, y0 = max(0, int(rect[0] * s)), max(0, int(rect[1] * s))
        x1, y1 = int(rect[2] * s) + 1, int(rect[3] * s) + 1
        roi = self.hand_mask[y0:y1, x0:x1]
        return roi.size > 0 and np.count_nonzero(roi) > COVER_FRAC * roi.size

    def detect(self, bgr, boxes=None):
        """boxes: list of (x0, y0, x1, y1) pixel rects; the tip must be over one.
        Returns 21 (x, y) points in full-frame pixels, or None.
        Index 8 (the index fingertip) is the tip; index 0 (wrist) is where it enters."""
        H, W = bgr.shape[:2]
        s = SMALL_W / W
        small = cv2.resize(bgr, (SMALL_W, round(H * s)), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (3, 3), 0)
        lab = cv2.cvtColor(small, cv2.COLOR_BGR2Lab).astype(np.float32)
        if self.bg is None or self.bg.shape != lab.shape:
            self.bg, self.n = lab.copy(), 0
            self.age = np.zeros(lab.shape[:2], np.int32)
        d = lab - self.bg
        d -= np.median(d[::4, ::4].reshape(-1, 3), axis=0)  # whole-picture exposure / white-balance shift
        dist = np.sqrt(0.35 * d[..., 0] ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)
        changed = (dist > DIFF_TH).astype(np.uint8) * 255
        fg = cv2.bitwise_and(changed, _skin(small))
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        self.mask = fg
        self.scale = s
        self.hand_mask = None

        # learn the scene: unchanged pixels quickly, changed ones slowly
        self.age = np.where(changed > 0, self.age + 1, 0)
        rate = np.where(changed > 0, np.where(self.age > STATIC_FRAMES, LEARN_STATIC, LEARN_FG),
                        LEARN_BG).astype(np.float32)[..., None]
        if self.n < WARMUP:
            rate[:] = 0.5
        self.bg += rate * (lab - self.bg)
        self.n += 1
        if self.n <= WARMUP:
            return None

        sboxes = None
        if boxes:
            sboxes = []
            for x0, y0, x1, y1 in boxes:
                px, py = BOX_PAD * (x1 - x0), BOX_PAD * (y1 - y0)
                sboxes.append(((x0 - px) * s, (y0 - py) * s, (x1 + px) * s, (y1 + py) * s))

        def in_box(x, y):
            return sboxes is None or any(a <= x <= c and b <= y <= e for a, b, c, e in sboxes)

        h, w = fg.shape
        R = TIP_R * w
        n, lbl, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
        best = None
        hand_mask = np.zeros_like(fg)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] < MIN_AREA * w * w:
                continue
            x0, y0, bw, bh = stats[i, :4]
            ys, xs = np.nonzero(lbl[y0:y0 + bh, x0:x0 + bw] == i)
            xs, ys = xs + x0, ys + y0
            on_edge = (xs < EDGE) | (xs >= w - EDGE) | (ys < EDGE) | (ys >= h - EDGE)
            if not on_edge.any():
                continue
            hand_mask[ys, xs] = 255
            ex, ey = xs[on_edge].mean(), ys[on_edge].mean()   # where it comes in
            dd = (xs - ex) ** 2 + (ys - ey) ** 2
            k = int(dd.argmax())
            reach = float(np.sqrt(dd[k]))
            tx, ty = float(xs[k]), float(ys[k])
            if reach < MIN_REACH * w:
                continue
            # the end must be thin like a finger (a hand holding an object is a wide lump)
            near = (xs - tx) ** 2 + (ys - ty) ** 2 <= R * R
            if near.sum() > TIP_MAX_FILL * np.pi * R * R:
                continue
            # finger direction: from the middle of its last bit towards the tip
            cx, cy = xs[near].mean(), ys[near].mean()
            ux, uy = tx - cx, ty - cy
            ul = float(np.hypot(ux, uy))
            if ul < 0.5:
                ux, uy, ul = tx - ex, ty - ey, reach
            ux, uy = ux / ul, uy / ul
            # the tip must be over a box, or point at one a little ahead
            ahead = AIM_AHEAD * w
            if not any(in_box(tx + ux * ahead * f / 8, ty + uy * ahead * f / 8) for f in range(9)):
                continue
            if best is None or reach > best[0]:
                best = (reach, (ex, ey), (tx, ty), (ux, uy))
        self.hand_mask = hand_mask
        if best is None:
            return None
        _, (ex, ey), (tx, ty), (ux, uy) = best
        # 21 points in the hand model's layout (full-frame pixels): wrist = where it enters,
        # index knuckle -> tip along the finger direction (so aiming follows the finger),
        # the other fingers bunched near the wrist (= "curled", so it reads as pointing).
        E, T = (ex / s, ey / s), (tx / s, ty / s)
        flen = FINGER_LEN * W
        K = (T[0] - ux * flen, T[1] - uy * flen)
        palm = (E[0] + (T[0] - E[0]) * 0.3, E[1] + (T[1] - E[1]) * 0.3)
        pts = [palm] * 21
        for j in range(5):
            pts[j] = (E[0] + (palm[0] - E[0]) * j / 4, E[1] + (palm[1] - E[1]) * j / 4)
        pts[5], pts[6], pts[7], pts[8] = K, ((2 * K[0] + T[0]) / 3, (2 * K[1] + T[1]) / 3), \
            ((K[0] + 2 * T[0]) / 3, (K[1] + 2 * T[1]) / 3), T
        return pts
