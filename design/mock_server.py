"""Mock of the console: plays moves on a loop, no camera or robot needed.

Run:  design\\run_mock.bat     then open http://localhost:8090
      python design/mock_server.py console_v3 8091 --wide    (v3, widescreen camera)
Keys sent from the page (Set up buttons etc.) change the fake state, so everything is clickable.
"""
import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "python"))
import web_ui  # noqa: E402

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
WIDE = "--wide" in sys.argv                          # 1280x720 camera instead of 640x480
FOLDER = ARGS[0] if ARGS else "console_v2"
PORT = int(ARGS[1]) if len(ARGS) > 1 else 8090
web_ui.WEB_DIR = os.path.join(HERE, FOLDER)          # which mock page to serve
web = web_ui.WebUI(PORT)
CAM_W, CAM_H = (1280, 720) if WIDE else (640, 480)

RECTS = ([[0.17, 0.3, 0.15, 0.58], [0.35, 0.3, 0.15, 0.58], [0.53, 0.3, 0.15, 0.58], [0.71, 0.3, 0.15, 0.58]]
         if "--wide" in sys.argv else
         [[0.05, 0.36, 0.2, 0.5], [0.28, 0.36, 0.2, 0.5], [0.51, 0.36, 0.2, 0.5], [0.74, 0.36, 0.2, 0.5]])
GRIP = {"egg": [80, 140], "cup": [150, 260], "block": [300, 600]}


# ---------------------------------------------------------------- fake camera picture
def scene(labels):
    W, H = CAM_W, CAM_H
    k = H / 480  # object size scale
    img = np.zeros((H, W, 3), np.uint8)
    for y in range(H):  # table, lit from the top
        img[y, :] = (58 + y / k * 0.05, 74 + y / k * 0.06, 92 + y / k * 0.07)
    rng = np.random.default_rng(3)
    img = cv2.add(img, rng.integers(0, 7, img.shape, dtype=np.uint8))
    tx0, ty0 = int(min(r[0] for r in RECTS) * W) - 20, int(RECTS[0][1] * H) - 20
    tx1, ty1 = int(max(r[0] + r[2] for r in RECTS) * W) + 20, int((RECTS[0][1] + RECTS[0][3]) * H) + 20
    cv2.rectangle(img, (tx0, ty0), (tx1, ty1), (40, 46, 52), -1)                 # tray
    for (x, y, w, h), lab in zip(RECTS, labels):
        x0, y0, x1, y1 = int(x * W) + 6, int(y * H) + 6, int((x + w) * W) - 6, int((y + h) * H) - 6
        cv2.rectangle(img, (x0, y0), (x1, y1), (30, 34, 38), -1)                 # pocket
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2 + int(10 * k)
        r = lambda v: int(v * k)  # noqa: E731
        if lab == "cup":
            cv2.circle(img, (cx + r(3), cy + r(4)), r(40), (20, 22, 25), -1, cv2.LINE_AA)
            cv2.circle(img, (cx, cy), r(40), (225, 228, 232), -1, cv2.LINE_AA)
            cv2.circle(img, (cx, cy), r(31), (165, 170, 178), -1, cv2.LINE_AA)
            cv2.ellipse(img, (cx + r(44), cy), (r(10), r(16)), 0, -90, 90, (225, 228, 232), r(5), cv2.LINE_AA)
        elif lab == "block":
            box = cv2.boxPoints(((cx, cy), (r(62), r(62)), 14)).astype(np.int32)
            cv2.fillPoly(img, [box + r(4)], (20, 22, 25), cv2.LINE_AA)
            cv2.fillPoly(img, [box], (40, 120, 230), cv2.LINE_AA)
        elif lab == "egg":
            cv2.ellipse(img, (cx, cy), (r(26), r(34)), 10, 0, 360, (200, 222, 240), -1, cv2.LINE_AA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def hand_at(x, y):
    """21 hand points (0..1) for a pointing hand whose fingertip is at (x, y), arm from below."""
    base = [(0, 0), (-.06, -.02), (-.09, -.06), (-.1, -.1), (-.1, -.13), (-.04, -.12), (-.03, -.18), (-.02, -.22),
            (-.01, -.26), (0, -.12), (0, -.15), (-.01, -.12), (-.01, -.09), (.03, -.11), (.03, -.14), (.02, -.11),
            (.02, -.08), (.06, -.09), (.06, -.12), (.05, -.1), (.05, -.07)]
    tx, ty = base[8]
    sx = .8 * (CAM_H / CAM_W) / .75  # keep the hand's shape on a widescreen picture
    return [[round(x + (px - tx) * sx, 4), round(y + (py - ty) * 1.05, 4)] for px, py in base]


def center(i):
    x, y, w, h = RECTS[i]
    return x + w / 2, y + h / 2


# ---------------------------------------------------------------- the scripted loop
# (start s, state, phase, from, to, obj, hand box or None, extra)
TIMELINE = [
    (0.0, "IDLE", "from", -1, -1, "", None, {}),
    (2.2, "IDLE", "from", -1, -1, "", 0, {}),
    (2.6, "DWELLING", "from", 0, -1, "", 0, {}),
    (3.6, "AWAIT_CLEAR", "from", 0, -1, "", "away", {}),
    (4.3, "CLASSIFYING", "from", 0, -1, "cup", None, {}),
    (5.0, "CHOOSE_DEST", "to", 0, -1, "cup", None, {"choose": True}),
    (6.6, "CHOOSE_DEST", "to", 0, -1, "cup", 3, {"choose": True}),
    (7.0, "DWELLING", "to", 0, 3, "cup", 3, {}),
    (8.0, "AWAIT_CLEAR", "to", 0, 3, "cup", "away", {}),
    (8.6, "CLASSIFYING", "to", 0, 3, "cup", None, {}),
    (9.2, "DISPATCHED", "to", 0, 3, "cup", None, {"send": ("cup", 1, 4)}),
    (12.4, "IDLE", "from", -1, -1, "", None, {"done": True, "labels": ["empty", "block", "empty", "cup"]}),
    (14.5, "DWELLING", "from", 1, -1, "", 1, {}),
    (15.5, "AWAIT_CLEAR", "from", 1, -1, "", "away", {}),
    (16.1, "CLASSIFYING", "from", 1, -1, "block", None, {}),
    (16.7, "CHOOSE_DEST", "to", 1, -1, "block", None, {"choose": True}),
    (17.8, "CHOOSE_DEST", "to", 1, -1, "block", 3, {"choose": True}),
    (18.2, "DWELLING", "to", 1, 3, "block", 3, {}),
    (19.2, "AWAIT_CLEAR", "to", 1, 3, "block", "away", {}),
    (19.8, "CLASSIFYING", "to", 1, 3, "block", None, {}),
    (20.4, "REJECTED", "to", 1, 3, "block", None, {"reject": "that box has a cup in it"}),
    (21.9, "IDLE", "from", -1, -1, "", None, {}),
    (27.0, "LOOP", "", -1, -1, "", None, {}),
]
START_LABELS = ["cup", "block", "empty", "empty"]

now = time.time()
moves = [
    {"t": now - 300, "obj": "block", "from": 3, "to": 2, "grip": GRIP["block"], "status": "done", "note": "", "secs": 3.4},
    {"t": now - 240, "obj": "cup", "from": 4, "to": 1, "grip": GRIP["cup"], "status": "done", "note": "", "secs": 3.1},
    {"t": now - 180, "obj": "cup", "from": 2, "to": 0, "grip": None, "status": "cancelled", "note": "No destination chosen in time"},
]
moves.reverse()
setup = {"calib": False, "calib_i": 0, "calib_one": False, "focus": 0, "mask": False,
         "has_bg": True, "boxes_set": True, "counts": {"egg": 2, "cup": 5, "block": 5}}
robot = {"busy": False, "last": "", "last_t": 0.0, "link": "simulated"}
labels = list(START_LABELS)
images = {}
t0 = time.time()
step_i = -1
t_start = time.time()
paused = False


def log(msg):
    print(msg, flush=True)


def stage_at(t):
    for i in range(len(TIMELINE) - 1, -1, -1):
        if t >= TIMELINE[i][0]:
            return i
    return 0


while True:
    for ev in web.pop_events():
        k = ev[1] if ev[0] == "key" else None
        if k == "p":
            paused = not paused
        elif k == "c":
            setup.update(calib=not setup["calib"], calib_i=0, calib_one=False)
            log("draw boxes: drag a box around box 1, then 2, ... up to 4" if setup["calib"] else "draw boxes: cancelled")
        elif ev[0] == "redraw":
            setup.update(calib=True, calib_i=ev[1], calib_one=True)
            log(f"redraw box {ev[1] + 1}: drag a box around it")
        elif ev[0] == "rect" and setup["calib"]:
            x0, y0, x1, y1 = ev[1:]
            RECTS[setup["calib_i"]] = [x0, y0, x1 - x0, y1 - y0]
            if setup["calib_one"] or setup["calib_i"] >= 3:
                setup.update(calib=False, calib_one=False)
                log("box positions saved")
            else:
                setup["calib_i"] += 1
        elif k == "b":
            setup["has_bg"] = True
            log("empty-tray photos saved for 4 boxes")
        elif ev[0] == "teach":
            name = ["egg", "cup", "block"][ev[1] - 1]
            setup["counts"][name] += 1
            box = labels.index(name) + 1 if name in labels else 1
            log(f"sample: {name} from box {box} (now {setup['counts'][name]})")
        elif k == "x":
            setup["counts"] = {"egg": 0, "cup": 0, "block": 0}
            log("examples cleared")
        elif k == "m":
            setup["mask"] = not setup["mask"]
        elif ev[0] == "cancel":
            log("move cancelled")

    if paused:
        t0 += 0.1
    t = time.time() - t0
    i = stage_at(t)
    st, ph, frm, to, obj, hb, extra = TIMELINE[i][1:]
    if st == "LOOP":
        t0 = time.time()
        labels = list(START_LABELS)
        step_i = -1
        continue
    if i != step_i:  # entering a new stage: side effects once
        step_i = i
        if "send" in extra:
            o, f, d = extra["send"]
            robot.update(busy=True, last=f"[pick] from={f} to={d} obj={o} grip=[{GRIP[o][0]},{GRIP[o][1]}]", last_t=time.time())
            moves.insert(0, {"t": time.time(), "obj": o, "from": f, "to": d, "grip": GRIP[o], "status": "moving", "note": ""})
            log(robot["last"])
        if extra.get("done"):
            robot["busy"] = False
            moves[0].update(status="done", secs=3.2)
        if "labels" in extra:
            labels = list(extra["labels"])
        if "reject" in extra:
            moves.insert(0, {"t": time.time(), "obj": obj, "from": frm + 1, "to": to + 1, "grip": None,
                             "status": "rejected", "note": extra["reject"]})
        del moves[20:]

    seg_start, seg_end = TIMELINE[i][0], TIMELINE[i + 1][0]
    frac = (t - seg_start) / max(seg_end - seg_start, 1e-6)
    hand = None
    if hb == "away":
        cx, cy = center(to if ph == "to" else frm)
        hand = hand_at(cx + 0.05 + frac * 0.25, cy + frac * 0.45)
    elif isinstance(hb, int):
        cx, cy = center(hb)
        wob = 0.006 * math.sin(t * 7)
        hand = hand_at(cx + wob, cy - 0.03)
    choose_start = 0
    if extra.get("choose"):
        j = i
        while j > 0 and TIMELINE[j - 1][7].get("choose"):
            j -= 1
        choose_start = TIMELINE[j][0]
    box_labels = list(labels)
    occl = [hand is not None and isinstance(hb, int) and k == hb for k in range(4)]
    key_ = tuple(labels)
    if key_ not in images:
        images[key_] = scene(labels)

    web.publish(images[key_])
    web.set_state({
        "sys": {"os": "QNX 8.0.0", "board": "Raspberry Pi 4B", "tracker": "tflite", "cam": f"{CAM_W}x{CAM_H}",
                "uptime": round(time.time() - t_start) + 6100, "fps": round(9.9 + 0.3 * math.sin(t * 1.3), 1),
                "frame_ms": 101 + int(4 * math.sin(t) + 6 * math.sin(t * 3.7)), "worst_ms": 128,
                "hand_ms": 66 + int(3 * math.sin(t * 2.1)),
                "react_ms": 620, "ontime_pct": 100.0, "cpu_pct": 38 + 3 * math.sin(t * .7), "jitter_ms": 6,
                "budget_ms": 200, "last_move": {"identify_ms": 420, "choose_s": 2.1, "robot_s": 3.2}},
        "sel": {"state": st, "phase": ph, "msg": extra.get("reject", ""), "from": frm, "to": to, "obj": obj,
                "progress": round(min(1, frac), 3) if st == "DWELLING" else 0.0,
                "time_left_ms": int(max(0, 10000 - (t - choose_start) * 1000)) if extra.get("choose") else None},
        "hand": {"tip": hand[8] if hand else None, "pointing": isinstance(hb, int), "over": hb if isinstance(hb, int) else -1,
                 "pts": hand},
        "boxes": [{"rect": [round(v, 4) for v in RECTS[k]], "label": box_labels[k], "conf": 0.94 if box_labels[k] == "cup" else 0.88,
                   "hand": occl[k], "grip": GRIP.get(box_labels[k])} for k in range(4)],
        "robot": robot, "moves": moves, "setup": setup,
    })
    time.sleep(0.05)
