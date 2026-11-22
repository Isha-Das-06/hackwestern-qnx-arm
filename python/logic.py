"""Box layout, fingertip smoothing and the point-from / point-to state machine.

Used on both the laptop and the QNX Pi. Pockets are saved in config/tray.yml.
"""
import math
from collections import Counter, deque

import cv2

from classifier import EMPTY, NAMES, UNKNOWN

# MediaPipe hand landmark numbers we use
WRIST, INDEX_TIP, MIDDLE_MCP = 0, 8, 9
INDEX_MCP, MIDDLE_TIP, RING_MCP, RING_TIP = 5, 12, 13, 16

# Pointing shape: index finger straight, middle + ring fingers curled.
#
# Measured in 3D (MediaPipe "world" landmarks, metres) as how much each finger
# BENDS at its three joints (knuckle + two finger joints), in degrees. A bend
# is the same whatever angle the camera sees the hand from, unlike 2D lengths:
# seen side-on, curled fingers hanging down look long in the flat image.
FINGERS = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12), "ring": (13, 14, 15, 16)}
# Nov 21 live test: a relaxed real point measured index ~70-75, middle ~91-97, right on the
# old 75/90 limits, so it flickered. Flat hand = others 40-50, so 70 still rejects it.
POINT_INDEX_MAX_BEND = 90.0   # index bent less than this = straight enough
POINT_OTHERS_MIN_BEND = 70.0  # middle and ring bent more than this = curled

# 2D fallback (only if no 3D landmarks): tip-to-knuckle / palm length.
POINT_INDEX_MIN = 0.45
POINT_OTHERS_MAX = 0.6


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle(a, b, c):
    """Degrees the path a->b->c turns at b (0 = straight on)."""
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - b[i] for i in range(3)]
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(x * x for x in v))
    if nu < 1e-9 or nv < 1e-9:
        return 0.0
    cos = sum(u[i] * v[i] for i in range(3)) / (nu * nv)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def finger_bends(world):
    """Total bend (degrees) of index, middle, ring from 21 3D points."""
    out = {}
    for name, (mcp, pip, dip, tip) in FINGERS.items():
        out[name] = (_angle(world[WRIST], world[mcp], world[pip])
                     + _angle(world[mcp], world[pip], world[dip])
                     + _angle(world[pip], world[dip], world[tip]))
    return out


def is_pointing(pts, world=None):
    """True if the hand is in a pointing shape (index out, others curled).

    A flat open hand, a hand holding/placing an object, a fist or a peace sign
    all fail, so shuffling objects around the tray can't select a pocket.
    world: the 21 3D points (preferred). pts: 21 2D pixels (fallback).
    """
    if world is not None:
        b = finger_bends(world)
        return (b["index"] < POINT_INDEX_MAX_BEND
                and min(b["middle"], b["ring"]) > POINT_OTHERS_MIN_BEND)
    palm = _dist(pts[WRIST], pts[MIDDLE_MCP])
    if palm < 1:
        return False
    idx = _dist(pts[INDEX_TIP], pts[INDEX_MCP]) / palm
    mid = _dist(pts[MIDDLE_TIP], pts[MIDDLE_MCP]) / palm
    ring = _dist(pts[RING_TIP], pts[RING_MCP]) / palm
    return idx > POINT_INDEX_MIN and max(mid, ring) < POINT_OTHERS_MAX * idx


# Pointing AT a box from a little away: follow the finger's direction past the tip
AIM_REACH = 1.5       # up to this many finger lengths (knuckle -> tip) past the tip
AIM_MAX_REACH = 0.25  # but never further than this fraction of the picture width


# ---------------------------------------------------------------- pockets
N_BOXES = 4  # 3 tray pockets + 1 extra box to put things in; any box can be "from" or "to"


class Tray:
    """Boxes stored as fractions of the image (0..1), so they still fit
    if the camera resolution changes."""

    def __init__(self, n=N_BOXES):
        self.pockets = self._defaults(n)

    @staticmethod
    def _defaults(n):
        w, h, y = 0.2, 0.32, 0.60
        gap = (1 - n * w) / (n + 1)
        return [[f"P{i + 1}", [gap + i * (w + gap), y, w, h]] for i in range(n)]

    def __len__(self):
        return len(self.pockets)

    def rect_px(self, i, frame_w, frame_h):
        x, y, w, h = self.pockets[i][1]
        x0, y0 = max(0, round(x * frame_w)), max(0, round(y * frame_h))
        x1, y1 = min(frame_w, round((x + w) * frame_w)), min(frame_h, round((y + h) * frame_h))
        return x0, y0, x1, y1

    def hit(self, px, py, frame_w, frame_h):
        for i in range(len(self)):
            x0, y0, x1, y1 = self.rect_px(i, frame_w, frame_h)
            if x0 <= px < x1 and y0 <= py < y1:
                return i
        return -1

    def aim(self, tip, base, frame_w, frame_h, max_reach=AIM_MAX_REACH):
        """Box the finger points AT: the box under the tip, or else the first box
        straight ahead of it (along knuckle -> tip), up to AIM_REACH finger lengths
        and max_reach of the picture width away. -1 if none."""
        b = self.hit(tip[0], tip[1], frame_w, frame_h)
        if b >= 0 or base is None:
            return b
        dx, dy = tip[0] - base[0], tip[1] - base[1]
        flen = math.hypot(dx, dy)
        if flen < 4:
            return -1
        reach = min(AIM_REACH * flen, max_reach * frame_w)
        steps = max(1, int(reach / 6))
        for k in range(1, steps + 1):
            f = reach * k / steps / flen
            b = self.hit(tip[0] + dx * f, tip[1] + dy * f, frame_w, frame_h)
            if b >= 0:
                return b
        return -1

    def load(self, path):
        fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
        if not fs.isOpened():
            return False
        node = fs.getNode("pockets")
        out = []
        for i in range(node.size()):
            p = node.at(i)
            r = p.getNode("rect")
            if r.size() == 4:
                out.append([p.getNode("name").string(), [r.at(j).real() for j in range(4)]])
        fs.release()
        if out:
            n = len(self.pockets)
            if len(out) < n:  # older file with fewer boxes: keep them, add default ones
                print(f"tray.yml has {len(out)} boxes, need {n}: press c to draw all {n}")
                out += self._defaults(n)[len(out):]
            self.pockets = out
        return bool(out)

    def save(self, path):
        fs = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
        fs.startWriteStruct("pockets", cv2.FileNode_SEQ)
        for name, rect in self.pockets:
            fs.startWriteStruct("", cv2.FileNode_MAP)
            fs.write("name", name)
            fs.startWriteStruct("rect", cv2.FileNode_SEQ | cv2.FileNode_FLOW)
            for v in rect:
                fs.write("", float(v))
            fs.endWriteStruct()
            fs.endWriteStruct()
        fs.endWriteStruct()
        fs.release()


def load_grip(path):
    """Grip pressure window per object from config/grip.yml (raw sensor units)."""
    grip = {"egg": (80, 140), "cup": (150, 260), "block": (300, 600)}
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
    if fs.isOpened():
        for k in grip:
            n = fs.getNode(k)
            if n.size() == 2:
                grip[k] = (int(n.at(0).real()), int(n.at(1).real()))
        fs.release()
    else:
        print(f"warn: {path} missing, using placeholder grip values")
    return grip


# ---------------------------------------------------------------- fingertip
class PointerTracker:
    """Index fingertip averaged over a few frames, so it doesn't flicker at a
    pocket edge, plus a steadied "is the hand pointing?" flag (majority of the
    last few frames). A short tracking dropout keeps the last values."""

    def __init__(self, smooth_frames=5, dropout_ms=200):
        self.hist = deque(maxlen=smooth_frames)
        self.pose = deque(maxlen=smooth_frames)
        self.dropout_ms = dropout_ms
        self.last = None
        self.pointing = False
        self.t_seen = -1e9

    def update(self, hand_pts, t_ms, world=None):
        """hand_pts: list of 21 (x, y) pixels, or None. world: the same hand's
        21 (x, y, z) 3D points if available. Returns (tip, pointing)."""
        if hand_pts is None:
            if self.last is not None and t_ms - self.t_seen <= self.dropout_ms:
                return self.last, self.pointing
            self.hist.clear()
            self.pose.clear()
            self.last, self.pointing = None, False
            return None, False
        self.hist.append(hand_pts[INDEX_TIP])
        self.pose.append(is_pointing(hand_pts, world))
        n = len(self.hist)
        self.last = (sum(p[0] for p in self.hist) / n, sum(p[1] for p in self.hist) / n)
        self.pointing = sum(self.pose) * 2 > len(self.pose)
        self.t_seen = t_ms
        return self.last, self.pointing


# ---------------------------------------------------------------- selection
IDLE, DWELLING, AWAIT_CLEAR, CLASSIFYING, CHOOSE_DEST, DISPATCHED, REJECTED = (
    "IDLE", "DWELLING", "AWAIT_CLEAR", "CLASSIFYING", "CHOOSE_DEST", "DISPATCHED", "REJECTED")
FROM, TO = "from", "to"  # which point of the move we're on


class Selector:
    """One move = two points:
      1. FROM: point at the box with the object for dwell_ms -> move the hand
         away -> identify the object (must be egg / cup / block)
      2. TO:   point at the box it should go to for dwell_ms -> move the hand
         away -> check that box is empty
    -> one pick request (from_box, object, to_box).

    After a move, the last box pointed at can't fire again until the finger leaves it.
    """

    def __init__(self, dwell_ms=1000, clear_frames=3, vote_frames=5,
                 await_timeout_ms=8000, reject_show_ms=1500, dispatch_timeout_ms=30000,
                 choose_timeout_ms=10000, grace_ms=300):
        self.dwell_ms = dwell_ms
        self.clear_frames = clear_frames
        self.vote_frames = vote_frames
        self.await_timeout_ms = await_timeout_ms
        self.reject_show_ms = reject_show_ms
        self.dispatch_timeout_ms = dispatch_timeout_ms
        self.choose_timeout_ms = choose_timeout_ms
        self.grace_ms = grace_ms  # finger may slip off the box this long without restarting the hold
        self.t_on = 0.0
        self.state = IDLE
        self.phase = FROM
        self.t_enter = 0.0
        self.target = -1   # box the object is in
        self.dest = -1     # box it goes to
        self.label = UNKNOWN
        self.locked = -1
        self.progress = 0.0
        self.clear_count = 0
        self.votes = []
        self.saw_busy = False
        self.msg = ""

    def box(self):
        """The box the current step is about."""
        return self.target if self.phase == FROM else self.dest

    def _go(self, state, t, msg=""):
        self.state, self.t_enter, self.msg = state, t, msg

    def _finish(self, t, msg):
        last = self.dest if self.dest >= 0 else self.target
        self.locked, self.target, self.dest, self.progress = last, -1, -1, 0.0
        self.phase, self.label = FROM, UNKNOWN
        self._go(IDLE, t, msg)

    def update(self, t, hover, occluded, labels, robot_busy):
        """hover: box under a pointing fingertip (-1 = none). occluded / labels:
        per box, is a hand over it / what the classifier sees in it.
        Returns (from_box, label, to_box) on the frame a pick should be sent, else None."""
        if hover != self.locked:
            self.locked = -1  # finger left the box: it can fire again

        if self.state == IDLE:
            self.progress = 0.0
            if hover >= 0 and hover != self.locked:
                if robot_busy:
                    self.msg = "robot busy"
                else:
                    self.target, self.dest, self.phase = hover, -1, FROM
                    self.t_on = t
                    self._go(DWELLING, t, "hold...")

        elif self.state == CHOOSE_DEST:
            self.progress = 0.0
            if hover >= 0 and hover != self.target:
                self.dest = hover
                self.t_on = t
                self._go(DWELLING, t, "hold...")
            elif t - self.t_enter > self.choose_timeout_ms:
                self._finish(t, "no destination chosen - start again")

        elif self.state == DWELLING:
            if hover == self.box():
                self.t_on = t
            if t - self.t_on > self.grace_ms:  # really left the box (not a 1-frame flicker)
                self.progress = 0.0
                if self.phase == FROM:
                    self.target = -1
                    self._go(IDLE, t)
                else:
                    self.dest = -1
                    self._go(CHOOSE_DEST, t, f"{NAMES[self.label]}: point where it goes")
            else:
                self.progress = min(1.0, (t - self.t_enter) / self.dwell_ms)
                if self.progress >= 1.0:
                    self.clear_count = 0
                    self._go(AWAIT_CLEAR, t, "selected - move hand away")

        elif self.state == AWAIT_CLEAR:
            self.clear_count = 0 if occluded[self.box()] else self.clear_count + 1
            if self.clear_count >= self.clear_frames:
                self.votes = []
                self._go(CLASSIFYING, t, "identifying..." if self.phase == FROM
                         else "checking it's empty...")
            elif t - self.t_enter > self.await_timeout_ms:
                self._finish(t, "timed out waiting for hand to clear")

        elif self.state == CLASSIFYING:
            if occluded[self.box()]:
                self.clear_count = 0
                self._go(AWAIT_CLEAR, t, "hand over box")
            else:
                self.votes.append(labels[self.box()])
                if len(self.votes) >= self.vote_frames:
                    label, n = Counter(self.votes).most_common(1)[0]
                    if n * 2 <= len(self.votes):  # needs a real majority
                        label = UNKNOWN
                    if self.phase == FROM:
                        if label == EMPTY:
                            self._go(REJECTED, t, "box is empty")
                        elif label == UNKNOWN:
                            self._go(REJECTED, t, "can't identify object")
                        else:
                            self.label, self.phase = label, TO
                            self._go(CHOOSE_DEST, t, f"{NAMES[label]}: point where it goes")
                    elif label == EMPTY:
                        self.saw_busy = False
                        self._go(DISPATCHED, t, f"moving {NAMES[self.label]}")
                        return self.target, self.label, self.dest
                    elif label == UNKNOWN:
                        self._go(REJECTED, t, "can't tell if that box is empty (press b?)")
                    else:
                        self._go(REJECTED, t, f"that box has a {NAMES[label]} in it")

        elif self.state == DISPATCHED:
            self.saw_busy |= robot_busy
            if ((self.saw_busy and not robot_busy)
                    or (not self.saw_busy and t - self.t_enter > 1000)
                    or t - self.t_enter > self.dispatch_timeout_ms):
                self._finish(t, "done" if self.saw_busy else "robot did not respond")

        elif self.state == REJECTED:
            if t - self.t_enter > self.reject_show_ms:
                self._finish(t, self.msg)

        return None
