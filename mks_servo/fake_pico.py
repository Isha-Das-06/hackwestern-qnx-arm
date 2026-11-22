"""
fake_pico: pretends to be the Pico 2 gripper board on a pseudo-terminal, so
gripper_link.py can be tested on the Pi before the real Pico is wired.

    python3 fake_pico.py                 # prints the pty path, e.g. /dev/ttyp3
    python3 gripper_link.py --port /dev/ttyp3

It speaks the exact same frames as pico_gripper.ino and copies its rules:
streams FSR at 200 Hz, applies the latest valid angle, and FREEZES if no
valid command arrives for 100 ms (it prints when, so you can time it).

Fake physics: the object touches the jaws at --contact degrees; past that,
force rises by --stiffness counts per degree. --slip-after N makes the
object slip out N seconds after first contact (force drops to ~0).
"""

import argparse
import os
import time
import tty

from gripper_link import load_json

g = load_json("gripper.json")
p = argparse.ArgumentParser()
p.add_argument("--contact", type=float, default=(g["open_angle"] + g["closed_angle"]) / 2,
               help="angle where jaws touch")
p.add_argument("--stiffness", type=float, default=40.0, help="counts per degree squeezed")
p.add_argument("--open-angle", type=float, default=g["open_angle"])
p.add_argument("--slip-after", type=float, default=0.0)
p.add_argument("--path-file", default="/tmp/fake_pico_port")
a = p.parse_args()

master, slave = os.openpty()
tty.setraw(master)
tty.setraw(slave)
path = os.ttyname(slave)
with open(a.path_file, "w") as f:
    f.write(path)
print(f"fake_pico on {path} (also written to {a.path_file})", flush=True)

os.set_blocking(master, False)
angle = None          # servo not attached until the first command
last_cmd = None
frozen_reported = False
contact_t = None
seq = 0
buf = b""
closing_down = a.contact < a.open_angle   # closing = angle decreasing


def xor(d):
    x = 0
    for b in d:
        x ^= b
    return x


def force_now(now):
    global contact_t
    if angle is None:
        return 15
    squeeze = (a.contact - angle) if closing_down else (angle - a.contact)
    if squeeze <= 0:
        return 15
    if contact_t is None:
        contact_t = now
    if a.slip_after and now - contact_t > a.slip_after:
        return 20
    return int(15 + squeeze * a.stiffness)


next_t = time.monotonic()
while True:
    next_t += 0.005
    d = next_t - time.monotonic()
    if d > 0:
        time.sleep(d)
    now = time.monotonic()

    try:
        buf += os.read(master, 512)
    except (BlockingIOError, OSError):
        pass
    while len(buf) >= 6:
        i = buf.find(b"\xAA\x56")
        if i < 0:
            buf = buf[-1:]
            break
        buf = buf[i:]
        if len(buf) < 6:
            break
        fr, buf = buf[:6], buf[6:]
        if xor(fr[:5]) != fr[5]:
            continue
        if frozen_reported:
            print(f"fake_pico: link back after {(now - last_cmd)*1000:.0f} ms", flush=True)
            frozen_reported = False
        last_cmd = now
        angle = max(g["angle_min"], min(g["angle_max"], fr[2]))   # same clamp as gripper_link

    frozen = last_cmd is not None and now - last_cmd > 0.100
    if frozen and not frozen_reported:
        print(f"fake_pico: FROZE at angle {angle}, {(now - last_cmd)*1000:.0f} ms "
              f"after last command", flush=True)
        frozen_reported = True

    f1 = force_now(now)
    f2 = max(0, f1 - 10)
    flags = (1 if frozen else 0) | (2 if angle is None else 0)
    out = bytes([0xAA, 0x55, f1 & 0xFF, f1 >> 8, f2 & 0xFF, f2 >> 8,
                 int(angle or 0), flags, seq])
    seq = (seq + 1) & 0xFF
    try:
        os.write(master, out + bytes([xor(out)]))
    except (BlockingIOError, OSError):
        pass
