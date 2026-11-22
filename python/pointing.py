"""Point at the box with the object for 1 s (it identifies the object), then point
at the box it should go to for 1 s (it checks that box is empty). Then it "sends"
a move: from box, to box, object and that object's grip range.

Runs on the laptop AND on the QNX Pi:
  laptop: run_python.bat                    (window + keys, mediapipe or TFLite)
  QNX Pi: python3 python/pointing.py        (QNX camera via qnx/pv_cam, TFLite,
                                             browser view at http://<pi>:8080)

Keys (window or browser): q quit | c draw pocket boxes | b photo of empty tray
  TAB pick pocket | 1 egg / 2 cup / 3 block = add example | x clear | m show mask
"""
import argparse
import collections
import math
import os
import platform
import time
import traceback

import cv2

from cloud_sync import CloudSync
from classifier import BLOCK, CUP, EGG, EMPTY, NAMES, UNKNOWN, PocketClassifier
from handtrack_tflite import HandTracker as TfliteHandTracker
from logic import (AWAIT_CLEAR, CHOOSE_DEST, CLASSIFYING, DISPATCHED, DWELLING, FROM, IDLE,
                   MIDDLE_MCP, REJECTED, TO, WRIST, PointerTracker, Selector, Tray, finger_bends,
                   load_grip)
from qnx_camera import QnxCamera, on_qnx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAND_MODEL = os.path.join(ROOT, "models", "hand_landmarker.task")
CONFIG = os.path.join(ROOT, "config")
TRAY_PATH = os.path.join(CONFIG, "tray.yml")
CLF_PATH = os.path.join(CONFIG, "classifier_py.npz")
CLOUD_CFG = os.path.join(CONFIG, "cloud.json")         # url + token for the history dashboard
CLOUD_SPOOL = os.path.join(CONFIG, "cloud_queue.jsonl")  # unsent history while offline

HAND_EDGES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
              (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
              (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


def now_ms():
    return time.perf_counter() * 1000.0


# ---------------------------------------------------------------- helpers
def hand_box(pts, w, h):
    """Box around the 21 landmarks, padded 10%, clipped to the image."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    m = 0.10 * max(max(xs) - min(xs), max(ys) - min(ys))
    return (max(0, min(xs) - m), max(0, min(ys) - m), min(w, max(xs) + m), min(h, max(ys) + m))


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def hand_covers(pts, rect, w, h):
    """True if the hand OR its forearm is over the pocket. From a top-down
    camera the arm hides the object too, so we also walk back from the wrist."""
    if overlaps(hand_box(pts, w, h), rect):
        return True
    wx, wy = pts[WRIST]
    dx, dy = wx - pts[MIDDLE_MCP][0], wy - pts[MIDDLE_MCP][1]
    palm = math.hypot(dx, dy)
    if palm < 1:
        return False
    dx, dy = dx / palm, dy / palm
    g = palm * 0.5
    x0, y0, x1, y1 = rect[0] - g, rect[1] - g, rect[2] + g, rect[3] + g
    for k in range(17):  # 0 .. 4 palm lengths back along the forearm
        px, py = wx + dx * k * 0.25 * palm, wy + dy * k * 0.25 * palm
        if x0 <= px < x1 and y0 <= py < y1:
            return True
    return False


def system_name():
    """'QNX 8.0.0' + board on the Pi, e.g. 'Windows 11' on the laptop."""
    u = platform.uname()
    if u.system == "QNX":
        board = next((w for w in u.version.split() + [u.machine] if "Pi" in w), u.machine)
        board = board.replace("RaspberryPi", "Raspberry Pi ")
        return f"QNX {u.release}", board
    return f"{u.system} {u.release}", u.machine


def text(img, s, org, scale, col, thick=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, col, thick, cv2.LINE_AA)


class FakeRobot:
    """Stand-in for the QNX control task: busy for 3 s after each pick."""

    def __init__(self):
        self.busy_until = 0.0
        self.last, self.last_t = "", 0.0  # last command sent, wall-clock time

    def busy(self):
        return now_ms() < self.busy_until

    def send_pick(self, src, label, dst, grip):
        lo, hi = grip[NAMES[label]]
        self.last = f"[pick] from={src + 1} to={dst + 1} obj={NAMES[label]} grip=[{lo},{hi}]"
        self.last_t = time.time()
        print(self.last, flush=True)
        self.busy_until = now_ms() + 3000

    def heartbeat(self, *a, **k):
        pass  # no supervisor on the laptop


# ---------------------------------------------------------------- hand trackers
class MediapipeTracker:
    """Laptop only: the mediapipe package doesn't exist on QNX."""

    name = "mediapipe"

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self.mp = mp
        self.lm = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=HAND_MODEL),
            running_mode=vision.RunningMode.VIDEO, num_hands=2))
        self.t_last = -1

    def detect(self, frame):
        H, W = frame.shape[:2]
        ts = max(int(now_ms()), self.t_last + 1)  # must strictly increase
        self.t_last = ts
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.lm.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ts)
        hands = [[(p.x * W, p.y * H) for p in lms] for lms in res.hand_landmarks]
        worlds = [[(p.x, p.y, p.z) for p in lms] for lms in res.hand_world_landmarks]
        return hands, worlds


class TfliteTracker:
    """QNX-compatible: the QNX AI workshop's two TFLite models (handtrack_tflite.py)."""

    def __init__(self):
        self.t = TfliteHandTracker(os.path.join(ROOT, "models"))
        self.name = "tflite (" + self.t.backend + ")"

    def detect(self, frame):
        found = self.t.detect(frame, 2)
        return [h["pts"] for h in found], [h["world"] for h in found]


def make_tracker(which):
    if which in ("auto", "mediapipe"):
        try:
            return MediapipeTracker()
        except Exception as e:  # not installed (e.g. on QNX) or no model file
            if which == "mediapipe":
                raise
            print(f"mediapipe unavailable ({e.__class__.__name__}), using TFLite tracker")
    return TfliteTracker()


# ---------------------------------------------------------------- main
def main():
    qnx = on_qnx()
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", type=int, default=None,
                    help="camera: webcam index on the laptop (default 0), "
                         "QNX camera unit on the Pi (default 4 = USB camera)")
    ap.add_argument("--camera", choices=["auto", "opencv", "qnx"], default="auto",
                    help="auto = QNX camera bridge on QNX, OpenCV webcam elsewhere")
    ap.add_argument("--web", type=int, default=8080 if qnx else 0,
                    help="browser view on this port (0 = off; default 8080 on QNX)")
    ap.add_argument("--flip", dest="flip", action="store_true", default=not qnx,
                    help="mirror the image (default on laptop, off on QNX)")
    ap.add_argument("--no-flip", dest="flip", action="store_false", help="don't mirror the image")
    ap.add_argument("--no-point-check", action="store_true",
                    help="any hand over a pocket counts (old behaviour)")
    ap.add_argument("--tracker", choices=["auto", "mediapipe", "tflite"], default="tflite",
                    help="hand tracker: tflite (default) = the QNX workshop models, same as "
                         "on the Pi; mediapipe = laptop only; auto = mediapipe if installed")
    ap.add_argument("--res", default="640x480",
                    help="QNX camera size, e.g. 1280x720 for widescreen (default 640x480)")
    ap.add_argument("--arm", action="store_true",
                    help="send picks to the QNX arm (motion.py) and heartbeat to its supervisor")
    ap.add_argument("--headless", action="store_true", help="no window (testing)")
    ap.add_argument("--frames", type=int, default=0, help="stop after N frames (testing)")
    ap.add_argument("--save-frame", default="", help="save the last frame here (testing)")
    args = ap.parse_args()
    if qnx:
        args.headless = True  # OpenCV on QNX has no window support: use --web

    web = None
    if args.web:
        from web_ui import WebUI
        web = WebUI(args.web)
        print(f"browser view: http://<this machine's address>:{args.web}")

    os.makedirs(CONFIG, exist_ok=True)
    tray = Tray()
    boxes_set = tray.load(TRAY_PATH)  # False until boxes have been drawn and saved once
    if not boxes_set:
        print("no config/tray.yml yet: default pocket boxes (press c to draw your own)")
    clf = PocketClassifier()
    if clf.load(CLF_PATH):
        print(f"classifier: {clf.count(EGG)} egg / {clf.count(CUP)} cup / {clf.count(BLOCK)} block examples")
    grip = load_grip(os.path.join(CONFIG, "grip.yml"))

    tracker = make_tracker(args.tracker)
    print(f"hand tracker: {tracker.name}")

    if args.camera == "qnx" or (args.camera == "auto" and qnx):
        unit = 4 if args.cam is None else args.cam
        try:
            res = tuple(int(v) for v in args.res.lower().split("x"))
        except ValueError:
            raise SystemExit(f"--res should look like 1280x720, not {args.res}")
        cap = QnxCamera(unit, res)
        if not cap.isOpened():
            raise SystemExit(f"no frames from QNX camera unit {unit} "
                             "(list units with: qnx/pv_cam -l; build it with: make -C qnx)")
    else:
        idx = 0 if args.cam is None else args.cam
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        if not cap.isOpened():
            raise SystemExit(f"cannot open webcam {idx} (try --cam 1)")

    pointer = PointerTracker()
    selector = Selector()
    if args.arm:
        from arm_link import ArmRobot
        robot = ArmRobot()
        print("arm link: picks -> motion udp 5611, heartbeat -> supervisor udp 5622", flush=True)
    else:
        robot = FakeRobot()
    last_pred = [(UNKNOWN, 0.0)] * len(tray)
    last_frac = [0.0] * len(tray)  # how much of each box changed vs its empty photo

    # UI state (mouse callback edits this)
    ui = {"calib": False, "calib_i": 0, "calib_one": False, "drag": None, "drag_now": None,
          "size": (1, 1), "focus": 0, "mask": False, "boxes_set": boxes_set}

    def set_pocket(x0, y0, x1, y1):
        """Store the box being drawn (normalized 0..1 coords) and move to the next pocket
        (or stop, when redrawing just one box)."""
        if not ui["calib"] or x1 - x0 < 0.01 or y1 - y0 < 0.01:
            return
        tray.pockets[ui["calib_i"]][1] = [x0, y0, x1 - x0, y1 - y0]
        ui["calib_i"] += 1
        if ui["calib_one"] or ui["calib_i"] >= len(tray):
            ui["calib"], ui["calib_one"], ui["boxes_set"] = False, False, True
            tray.save(TRAY_PATH)
            print(f"box positions saved to {TRAY_PATH}")

    def on_mouse(ev, x, y, flags, _):
        if not ui["calib"]:
            return
        if ev == cv2.EVENT_LBUTTONDOWN:
            ui["drag"] = ui["drag_now"] = (x, y)
        elif ev == cv2.EVENT_MOUSEMOVE and ui["drag"]:
            ui["drag_now"] = (x, y)
        elif ev == cv2.EVENT_LBUTTONUP and ui["drag"]:
            (ax, ay), W, H = ui["drag"], *ui["size"]
            ui["drag"] = None
            set_pocket(min(ax, x) / W, min(ay, y) / H, max(ax, x) / W, max(ay, y) / H)

    win = "pointing (python)"
    if not args.headless:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, 1280, 720)
        cv2.setMouseCallback(win, on_mouse)

    frames, fps, t_fps, n_fps = 0, 0.0, now_ms(), 0
    prev_state = selector.state
    view = None

    # for the browser console: timings, move history, system info
    sys_os, sys_board = system_name()
    t_start = time.time()
    frame_ms = collections.deque(maxlen=90)   # whole-loop time per frame (~10 s)
    hand_ms = collections.deque(maxlen=30)    # hand-model time per frame
    moves = collections.deque(maxlen=20)      # newest first
    t_prev = None
    BUDGET_MS = 200                            # a frame slower than this counts as late
    marks = {}                                 # timestamps inside the current move
    health = {"react_ms": None, "last_move": None, "cpu_pct": None}
    cpu_prev = (sum(os.times()[:2]), time.time())
    n_cpu = os.cpu_count() or 1

    cloud = CloudSync.from_config(CLOUD_CFG, CLOUD_SPOOL)  # None = off
    t_health = time.time()

    def cloud_move(m):
        """A move is final (done / rejected / cancelled / no-response) -> send it to history."""
        if cloud:
            lm = health["last_move"] if m["status"] in ("done", "no-response") else None
            cloud.send("move", obj=m["obj"], from_box=m["from"], to_box=m["to"], status=m["status"],
                       note=m["note"], grip=m["grip"], robot_s=m.get("secs"),
                       react_ms=m.get("react_ms"),
                       identify_ms=lm["identify_ms"] if lm else None,
                       choose_s=lm["choose_s"] if lm else None)

    def add_move(status, note=""):
        lbl = selector.label
        if lbl == UNKNOWN and selector.target >= 0:
            lbl = last_pred[selector.target][0]
        obj = NAMES[lbl] if lbl in (EGG, CUP, BLOCK) else ""
        moves.appendleft({"t": time.time(), "obj": obj,
                          "from": selector.target + 1 if selector.target >= 0 else 0,
                          "to": selector.dest + 1 if selector.dest >= 0 else 0,
                          "grip": list(grip[obj]) if obj in grip else None,
                          "status": status, "note": note, "t_sent": now_ms()})
        if status != "moving":
            cloud_move(moves[0])

    while True:
        ok, frame = cap.read()
        if not ok:
            print("camera read failed")
            break
        if args.flip:
            frame = cv2.flip(frame, 1)  # mirror, so moving right moves right
        H, W = frame.shape[:2]
        ui["size"] = (W, H)
        t = now_ms()
        if t_prev is not None:
            frame_ms.append(t - t_prev)
        t_prev = t

        # ---- hands: 21 (x, y) pixels + 21 (x, y, z) 3D points per hand ----
        hands, worlds = tracker.detect(frame)
        hand_ms.append(now_ms() - t)

        # biggest hand on screen is the one pointing
        def area(pts):
            b = hand_box(pts, W, H)
            return (b[2] - b[0]) * (b[3] - b[1])
        primary = max(hands, key=area) if hands else None
        primary_world = worlds[hands.index(primary)] if primary and len(worlds) == len(hands) else None

        tip, pointing = pointer.update(primary, t, primary_world)
        bends = finger_bends(primary_world) if primary_world else None
        over = tray.hit(tip[0], tip[1], W, H) if tip else -1  # fingertip is over this pocket
        # Only a pointing hand selects; a hand placing/holding an object doesn't.
        hover = over if (pointing or args.no_point_check) else -1

        # ---- pockets: is a hand over it? if not, what's in it? ----
        occluded = []
        for i in range(len(tray)):
            r = tray.rect_px(i, W, H)
            occ = any(hand_covers(h, r, W, H) for h in hands)
            occluded.append(occ)
            if not occ and r[2] > r[0] and r[3] > r[1]:
                label, conf, frac, _ = clf.predict(i, frame[r[1]:r[3], r[0]:r[2]])
                last_pred[i] = (label, conf)
                last_frac[i] = frac

        # ---- selection ----
        pick = selector.update(t, hover, occluded, [p[0] for p in last_pred], robot.busy())
        if selector.state != prev_state:
            print(f"[sel] {prev_state} -> {selector.state}  from={selector.target + 1}"
                  f" to={selector.dest + 1}  {selector.msg}")
            # timestamps for the "Real-time health" panel
            if selector.state == CLASSIFYING and selector.phase == FROM:
                marks["identify"] = t
            elif selector.state == CHOOSE_DEST and prev_state == CLASSIFYING:
                marks["identify_ms"] = t - marks.get("identify", t)
                marks["choose"] = t
            elif selector.state == AWAIT_CLEAR and selector.phase == TO and prev_state == DWELLING:
                marks["choose_s"] = (t - marks.get("choose", t)) / 1000
            elif selector.state == CLASSIFYING and selector.phase == TO:
                marks["hand_away"] = t

            if selector.state == REJECTED:
                add_move("rejected", selector.msg)
            elif prev_state == CHOOSE_DEST and selector.state == IDLE:
                add_move("cancelled", "No destination chosen in time")
            elif prev_state == DISPATCHED and moves and moves[0]["status"] == "moving":
                ok_done = selector.msg == "done"
                moves[0]["status"] = "done" if ok_done else "no-response"
                moves[0]["secs"] = round((now_ms() - moves[0]["t_sent"]) / 1000, 1)
                health["last_move"] = {"identify_ms": round(marks.get("identify_ms", 0)),
                                       "choose_s": round(marks.get("choose_s", 0), 1),
                                       "robot_s": moves[0]["secs"]}
                cloud_move(moves[0])
            prev_state = selector.state
        if pick:
            robot.send_pick(pick[0], pick[1], pick[2], grip)
            add_move("moving")
            if "hand_away" in marks:  # hand left the destination box -> command sent
                health["react_ms"] = round(now_ms() - marks["hand_away"])
                moves[0]["react_ms"] = health["react_ms"]

        # ---- fps ----
        frames += 1
        n_fps += 1
        if t - t_fps >= 1000:
            fps = n_fps * 1000 / (t - t_fps)
            t_fps, n_fps = t, 0
            # this app's share of the whole CPU (all cores), over the last second
            cpu_now = (sum(os.times()[:2]), time.time())
            if cpu_now[1] > cpu_prev[1]:
                health["cpu_pct"] = round(100 * (cpu_now[0] - cpu_prev[0])
                                          / (cpu_now[1] - cpu_prev[1]) / n_cpu, 1)
            cpu_prev = cpu_now
            if cloud and time.time() - t_health >= 10 and frame_ms:  # health sample every 10 s
                t_health = time.time()
                ft = list(frame_ms)
                cloud.send("health", fps=round(fps, 1), frame_ms=round(sum(ft) / len(ft), 1),
                           worst_ms=round(max(ft), 1),
                           ontime_pct=round(100 * sum(v <= BUDGET_MS for v in ft) / len(ft), 1),
                           cpu_pct=health["cpu_pct"],
                           hand_ms=round(sum(hand_ms) / len(hand_ms), 1) if hand_ms else None)
            if args.headless or hands:  # once a second, only while a hand is in view
                bs = (f" bend I{bends['index']:.0f} M{bends['middle']:.0f} R{bends['ring']:.0f}"
                      if bends else "")
                print(f"[stat] {fps:.1f} fps | hands {len(hands)} | tip over P{over + 1}"
                      f" | pointing {'YES' if pointing else 'no'}{bs} | {selector.state}")

        robot.heartbeat(fps, selector.state, last_pred,
                        round(frame_ms[-1], 1) if frame_ms else None)

        # ---- draw ----
        if not args.headless or args.save_frame:  # the browser draws its own overlay
            view = frame.copy()
            for i in range(len(tray)):
                x0, y0, x1, y1 = tray.rect_px(i, W, H)
                col, th = (140, 140, 140), 2
                if i == hover:
                    col, th = (0, 220, 255), 3
                if i == selector.target:
                    col, th = (255, 200, 0), 4
                if i == selector.dest:
                    col, th = (0, 165, 255), 4
                if ui["calib"] and i == ui["calib_i"]:
                    col = (255, 0, 255)
                cv2.rectangle(view, (x0, y0), (x1, y1), col, th)
                tag = "FROM" if i == selector.target else "TO" if i == selector.dest else ""
                if tag:
                    text(view, tag, (x0 + 4, y1 - 10), 0.8, col, 2)
                if i == ui["focus"] and not ui["calib"]:
                    cv2.rectangle(view, (x0 - 4, y0 - 4), (x1 + 4, y1 + 4), (255, 255, 255), 1)
                label, conf = last_pred[i]
                text(view, f"{tray.pockets[i][0]} {NAMES[label]} {conf * 100:.0f}%"
                     + (" (hand)" if occluded[i] else ""), (x0 + 4, y0 + 20), 0.55, col)
                if ui["mask"] and not occluded[i] and x1 > x0 and y1 > y0:
                    _, _, _, m = clf.predict(i, frame[y0:y1, x0:x1])
                    m = cv2.resize(m, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
                    view[y0:y1, x0:x1][m > 0] = (255, 0, 255)
            for h in hands:
                c = (0, 255, 0) if h is primary else (160, 160, 160)
                for a, b in HAND_EDGES:
                    cv2.line(view, tuple(map(int, h[a])), tuple(map(int, h[b])), c, 2, cv2.LINE_AA)
                for p in h:
                    cv2.circle(view, tuple(map(int, p)), 3, (255, 255, 255), -1, cv2.LINE_AA)
            if tip:
                tp = (int(tip[0]), int(tip[1]))
                cv2.circle(view, tp, 8, (0, 220, 255) if hover >= 0 else (200, 200, 200), 2, cv2.LINE_AA)
                if over >= 0 and hover < 0:  # over a pocket but not pointing
                    text(view, "point with index finger", (tp[0] + 14, tp[1] - 12), 0.6, (200, 200, 200), 1)
                if selector.state == DWELLING:
                    ring = (0, 165, 255) if selector.phase == TO else (255, 200, 0)
                    cv2.ellipse(view, tp, (26, 26), -90, 0, 360 * selector.progress,
                                ring, 4, cv2.LINE_AA)
            if ui["calib"] and ui["drag"]:
                cv2.rectangle(view, ui["drag"], ui["drag_now"], (255, 0, 255), 2)

            text(view, f"{selector.state}  {selector.msg}", (12, 32), 0.8, (255, 255, 255), 2)
            bend_s = (f" (bend I{bends['index']:.0f} M{bends['middle']:.0f} R{bends['ring']:.0f})"
                      if bends else "")
            text(view, f"{fps:.0f} fps | hover P{hover + 1} | pointing {'YES' if pointing else 'no'}{bend_s}"
                 f" | robot {'BUSY' if robot.busy() else 'idle'} | {tracker.name}",
                 (12, 58), 0.5, (220, 220, 220))
            if ui["calib"]:
                text(view, f"DRAW: drag a box around box {ui['calib_i'] + 1} of {len(tray)}",
                     (12, 86), 0.7, (255, 0, 255), 2)
            else:
                text(view, f"examples egg {clf.count(EGG)} cup {clf.count(CUP)} block {clf.count(BLOCK)}"
                     f" | keys 1/2/3 teach P{ui['focus'] + 1}", (12, 86), 0.5, (200, 255, 200))
                text(view, "q quit | c draw boxes | b empty tray | TAB box | 1 egg 2 cup 3 block"
                     " | x clear | m mask", (12, H - 14), 0.5, (200, 200, 200))

        # ---- show + collect keys (window and/or browser) ----
        keys = []
        if web:
            pic = frame
            if ui["mask"]:  # show what the classifier counts as "something in the box"
                pic = frame.copy()
                for i in range(len(tray)):
                    x0, y0, x1, y1 = tray.rect_px(i, W, H)
                    if not occluded[i] and x1 > x0 and y1 > y0:
                        _, _, _, m = clf.predict(i, frame[y0:y1, x0:x1])
                        m = cv2.resize(m, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
                        pic[y0:y1, x0:x1][m > 0] = (255, 0, 255)
            ok_jpg, jpg = cv2.imencode(".jpg", pic, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok_jpg:
                web.publish(jpg.tobytes())
            ft = sorted(frame_ms)
            mean = sum(ft) / len(ft) if ft else 0
            web.set_state({
                "sys": {"os": sys_os, "board": sys_board, "tracker": tracker.name,
                        "cam": f"{W}x{H}", "uptime": round(time.time() - t_start),
                        "fps": round(fps, 1),
                        "frame_ms": round(frame_ms[-1]) if frame_ms else 0,
                        "worst_ms": round(ft[-1]) if ft else 0,
                        "hand_ms": round(sum(hand_ms) / len(hand_ms)) if hand_ms else 0,
                        "budget_ms": BUDGET_MS,
                        "now": time.time(),  # the page shows times relative to this (Pi clock may be unset)
                        "ontime_pct": round(100 * sum(v <= BUDGET_MS for v in ft) / len(ft), 1) if ft else None,
                        "jitter_ms": round((sum((v - mean) ** 2 for v in ft) / len(ft)) ** 0.5) if ft else None,
                        **health,
                        "cloud": cloud.status() if cloud else None},
                "sel": {"state": selector.state, "phase": selector.phase, "msg": selector.msg,
                        "from": selector.target, "to": selector.dest,
                        "obj": NAMES[selector.label] if selector.label in (EGG, CUP, BLOCK) else "",
                        "progress": round(selector.progress, 3),
                        "time_left_ms": max(0, round(selector.choose_timeout_ms - (t - selector.t_enter)))
                        if selector.state == CHOOSE_DEST else None},
                "hand": {"tip": [round(tip[0] / W, 4), round(tip[1] / H, 4)] if tip else None,
                         "pointing": bool(pointing), "over": over,
                         "pts": [[round(x / W, 4), round(y / H, 4)] for x, y in primary]
                         if primary else None},
                "boxes": [{"rect": [round(v, 4) for v in tray.pockets[i][1]],
                           "label": NAMES[last_pred[i][0]], "conf": round(last_pred[i][1], 2),
                           "hand": bool(occluded[i]),
                           "grip": list(grip[NAMES[last_pred[i][0]]])
                           if NAMES[last_pred[i][0]] in grip else None}
                          for i in range(len(tray))],
                "robot": {"busy": robot.busy(), "last": robot.last, "last_t": robot.last_t,
                          "link": "simulated"},  # "connected" once the real control task is wired
                "moves": [{k: v for k, v in m.items() if k != "t_sent"} for m in moves],
                "setup": {"calib": ui["calib"], "calib_i": ui["calib_i"], "calib_one": ui["calib_one"],
                          "boxes_set": ui["boxes_set"], "focus": ui["focus"],
                          "mask": ui["mask"], "has_bg": all(clf.has_background(i) for i in range(len(tray))),
                          "counts": {"egg": clf.count(EGG), "cup": clf.count(CUP),
                                     "block": clf.count(BLOCK)}},
            })
            for ev in web.pop_events():
                if ev[0] == "key":
                    keys.append({"tab": 9}.get(ev[1], ord(ev[1][0]) if ev[1] else 0))
                elif ev[0] == "rect":
                    set_pocket(*ev[1:])
                elif ev[0] == "focus" and 0 <= ev[1] < len(tray):
                    ui["focus"] = ev[1]
                elif ev[0] == "cancel" and selector.state not in (IDLE, DISPATCHED):
                    add_move("cancelled", "Cancelled from the console")
                    selector._finish(t, "move cancelled")
                    prev_state = selector.state
                elif ev[0] == "redraw" and 0 <= ev[1] < len(tray):
                    ui["calib"], ui["calib_i"], ui["calib_one"] = True, ev[1], True
                    print(f"redraw box {ev[1] + 1}: drag a box around it")
                elif ev[0] == "forget":
                    clf.clear_label(ev[1])
                    clf.save(CLF_PATH)
                    print(f"{NAMES[ev[1]]} examples cleared")
                elif ev[0] == "forgetbg":
                    clf.clear_background()
                    clf.save(CLF_PATH)
                    print("empty-tray photo cleared - take a new one")
                elif ev[0] == "teach":
                    # teach from whichever box has something in it (no need to pick a box)
                    full = [i for i in range(len(tray)) if not occluded[i] and last_pred[i][0] != EMPTY]
                    # several look full (object over a line, shadows)? use the box that changed
                    # the most, if it clearly beats the rest
                    full.sort(key=lambda i: -last_frac[i])
                    if len(full) > 1 and last_frac[full[0]] >= 2 * last_frac[full[1]]:
                        full = full[:1]
                    if not all(clf.has_background(i) for i in range(len(tray))):
                        print("teach: take the empty-tray photo first (it's how I find the object)")
                    elif any(occluded):
                        print("teach: move your hand out of the boxes first")
                    elif not full:
                        print("teach: put the object in a box first")
                    elif len(full) > 1:
                        print(f"teach: boxes {', '.join(str(i + 1) for i in sorted(full))} all have something "
                              f"in them - leave just one object in the boxes")
                    else:
                        f = full[0]
                        x0, y0, x1, y1 = tray.rect_px(f, W, H)
                        try:
                            clf.add_sample(ev[1], f, frame[y0:y1, x0:x1])
                            clf.save(CLF_PATH)
                        except Exception:
                            traceback.print_exc()
                            print("^ teaching failed - send this to Claude")
        if not args.headless:
            cv2.imshow(win, view)
            keys.append(cv2.waitKey(1) & 0xFF)

        quit_now = False
        for key in keys:
            if key in (ord("q"), 27):
                quit_now = True
            if key == ord("c"):
                ui["calib"], ui["calib_i"], ui["calib_one"] = not ui["calib"], 0, False
                if ui["calib"]:
                    print(f"draw boxes: drag a box around box 1, then 2, ... up to {len(tray)}")
                else:
                    print("draw boxes: cancelled (press c again to start over)")
            if key == ord("m"):
                ui["mask"] = not ui["mask"]
            if key == 9:  # TAB
                ui["focus"] = (ui["focus"] + 1) % len(tray)
            try:  # a bug in a key action should print an error, not close the app
                if key == ord("b"):
                    if hands:
                        print("move your hand out of view first")
                    else:
                        for i in range(len(tray)):
                            x0, y0, x1, y1 = tray.rect_px(i, W, H)
                            clf.set_background(i, frame[y0:y1, x0:x1])
                        clf.save(CLF_PATH)
                        print(f"empty-tray photos saved for {len(tray)} pockets")
                if key in (ord("1"), ord("2"), ord("3")):
                    f = ui["focus"]
                    if occluded[f]:
                        print(f"hand is over P{f + 1} - move it away first")
                    else:
                        x0, y0, x1, y1 = tray.rect_px(f, W, H)
                        clf.add_sample(key - ord("0"), f, frame[y0:y1, x0:x1])
                        clf.save(CLF_PATH)
                if key == ord("x"):
                    clf.clear_samples()
                    clf.save(CLF_PATH)
                    print("examples cleared")
            except Exception:
                traceback.print_exc()
                print("^ that key action failed - send this to Claude")
        if quit_now:
            break

        if args.frames and frames >= args.frames:
            break

    if args.save_frame and view is not None:
        cv2.imwrite(args.save_frame, view)
    cap.release()
    if not args.headless:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
