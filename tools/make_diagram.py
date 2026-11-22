"""Draws the system diagram for the Devpost page -> docs_images/architecture.png"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

S = 2  # draw at 2x for sharp text
W, H = 1800, 1010
img = Image.new("RGB", (W * S, H * S), "#ffffff")
d = ImageDraw.Draw(img)
F = "C:/Windows/Fonts/"


def font(size, bold=False):
    return ImageFont.truetype(F + ("segoeuib.ttf" if bold else "segoeui.ttf"), size * S)


INK, DIM, LINE = "#1f2328", "#57606a", "#8c959f"
BLUE, BLUE_BG = "#0969da", "#ddf4ff"
RED, RED_BG = "#cf222e", "#ffebe9"
GREEN, GREEN_BG = "#1a7f37", "#dafbe1"
GREY_BG = "#f6f8fa"


def box(x0, y0, x1, y1, fill, outline, width=2, dash=False, r=14):
    if dash:
        d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], r * S, fill=fill)
        dashed_rect(x0, y0, x1, y1, outline)
    else:
        d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], r * S, fill=fill,
                            outline=outline, width=width * S)


def dashed_line(x0, y0, x1, y1, color, w=2, on=10, off=7):
    L = math.hypot(x1 - x0, y1 - y0)
    n = int(L // (on + off)) + 1
    for i in range(n):
        a, b = i * (on + off) / L, min(1, (i * (on + off) + on) / L)
        d.line([(x0 + (x1 - x0) * a) * S, (y0 + (y1 - y0) * a) * S,
                (x0 + (x1 - x0) * b) * S, (y0 + (y1 - y0) * b) * S], fill=color, width=w * S)


def dashed_rect(x0, y0, x1, y1, color):
    for a in [(x0 + 14, y0, x1 - 14, y0), (x0 + 14, y1, x1 - 14, y1),
              (x0, y0 + 14, x0, y1 - 14), (x1, y0 + 14, x1, y1 - 14)]:
        dashed_line(*a, color)


def text(x, y, s, size=20, bold=False, color=INK, anchor="la"):
    d.text((x * S, y * S), s, font=font(size, bold), fill=color, anchor=anchor)


def arrow(x0, y0, x1, y1, color=INK, w=2, both=False, dash=False):
    if dash:
        dashed_line(x0, y0, x1, y1, color, w)
    else:
        d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=color, width=w * S)

    def head(xa, ya, xb, yb):
        ang = math.atan2(yb - ya, xb - xa)
        k = 13
        p = [(xb, yb), (xb - k * math.cos(ang - 0.45), yb - k * math.sin(ang - 0.45)),
             (xb - k * math.cos(ang + 0.45), yb - k * math.sin(ang + 0.45))]
        d.polygon([(a * S, b * S) for a, b in p], fill=color)
    head(x0, y0, x1, y1)
    if both:
        head(x1, y1, x0, y0)


def chip(x, y, label, fg, bg):
    w = d.textlength(label, font=font(15, True)) / S + 20
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + 26) * S], 13 * S, fill=bg)
    text(x + 10, y + 13, label, 15, True, fg, "lm")


def node(x0, y0, x1, y1, title, lines, fill="#ffffff", outline=LINE, prio=None, tsize=21):
    box(x0, y0, x1, y1, fill, outline)
    text(x0 + 18, y0 + 16, title, tsize, True)
    if prio:
        chip(x1 - 18 - (d.textlength(prio[0], font=font(15, True)) / S + 20), y0 + 16, *prio)
    for i, s in enumerate(lines):
        text(x0 + 18, y0 + 52 + i * 27, s, 17, False, DIM)


# ---- title
text(60, 40, "How the robot is built", 34, True)
text(60, 88, "Everything that controls the arm runs on one Raspberry Pi under QNX. The cloud only keeps history.", 19, False, DIM)

# ---- QNX board
QX0, QY0, QX1, QY1 = 330, 150, 1370, 800
box(QX0, QY0, QX1, QY1, GREY_BG, "#d0d7de", 2, r=20)
text(QX0 + 24, QY0 + 20, "Raspberry Pi  ·  QNX 8.0", 24, True)
text(QX0 + 24, QY0 + 56, "Each box is a separate QNX process with its own memory. Higher priority always runs first.", 17, False, DIM)

# supervisor
node(560, 250, 1140, 370, "Supervisor", ["Watches a heartbeat from every process · reads the e-stop",
                                          "AI crashed: pause, hold, restart it.  Anything else: stop and hold."],
     prio=("priority 40", "#ffffff", INK))

# three workers
node(360, 470, 680, 650, "Vision", ["Hand tracking: TensorFlow Lite", "(QNX tflite_runtime)",
                                    "Object classifier", "~9 frames a second"],
     prio=("priority 10", INK, "#eaeef2"))
node(730, 470, 1010, 650, "Motion", ["Pick-and-place sequence", "Soft limits · stall check",
                                     "Runs 50 times a second"],
     prio=("priority 30", "#ffffff", BLUE))
node(1060, 470, 1345, 650, "Grip control", ["Closes to the target force", "Backs off · flags slips",
                                            "Runs 100 times a second"],
     prio=("priority 30", "#ffffff", BLUE))

# arrows inside
arrow(680, 555, 730, 555)
text(705, 530, "pick", 14, True, DIM, "mm")
arrow(1010, 555, 1060, 555)
text(1035, 530, "grip", 14, True, DIM, "mm")
for x in (520, 870, 1200):
    arrow(x, 470, x if x == 870 else (600 if x == 520 else 1100), 370, LINE, 2, dash=True)
text(1160, 420, "heartbeats", 15, False, DIM)

# web pages note
text(QX0 + 24, 685, "Web pages from the Pi:", 17, True)
text(QX0 + 24, 713, "camera view with box labels", 17, False, DIM)
text(QX0 + 24, 741, "arm dashboard: force bars, live timing", 17, False, DIM)
text(905, 685, "Measured under full CPU load:", 17, True, BLUE)
text(905, 713, "grip control at most 0.49 ms late", 17, True, BLUE)
text(905, 741, "same code at normal priority: 137 ms late", 17, False, DIM)

# ---- left side: camera + e-stop
node(60, 500, 280, 610, "USB camera", ["640 × 480"])
arrow(280, 555, 360, 555)
node(60, 230, 280, 390, "E-stop button", ["Cuts motor power", "Wire is normally-closed:", "loose wire = stop"],
     fill=RED_BG, outline=RED)
arrow(280, 310, 560, 310, RED)
text(420, 290, "GPIO", 15, True, RED, "mm")

# ---- right side: Pico + gripper
node(1440, 470, 1740, 625, "Raspberry Pi Pico", ["Reads the force sensors", "Freezes the gripper if QNX", "is silent for 100 ms"],
     fill=GREEN_BG, outline=GREEN)
arrow(1345, 535, 1440, 535, INK, both=True)
text(1392, 512, "UART", 14, True, DIM, "mm")
node(1440, 680, 1740, 790, "Gripper", ["Servo + force sensor", "in each jaw"])
arrow(1590, 625, 1590, 680, INK, both=True)

# ---- bottom: motors
node(700, 860, 1040, 970, "Two stepper motors", ["Closed-loop (SERVO42C)", "lift + base"])
arrow(870, 650, 870, 860, INK, both=True)
text(882, 830, "UART", 14, True, DIM, "lm")

# ---- cloud
box(1440, 150, 1740, 385, "#ffffff", LINE, dash=True)
text(1458, 168, "Cloud (history only)", 21, True)
text(1458, 210, "Vultr server", 18, True, INK)
text(1458, 236, "history service + dashboard", 16, False, DIM)
text(1458, 270, "Tiger Data", 18, True, INK)
text(1458, 296, "TimescaleDB: moves + health", 16, False, DIM)
text(1458, 330, "Pi sends moves + health every 10 s", 16, False, DIM)
text(1458, 354, "The robot never waits on it", 16, False, DIM)
arrow(1370, 270, 1440, 270, LINE, 2, dash=True)

os.makedirs("docs_images", exist_ok=True)
img = img.resize((W, H), Image.LANCZOS)
img.save("docs_images/architecture.png")
print("saved docs_images/architecture.png")
