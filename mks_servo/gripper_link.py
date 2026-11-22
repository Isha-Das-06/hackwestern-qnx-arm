"""
gripper_link: the QNX side of the gripper. QNX makes every grip decision here.

Run at high priority so the force loop keeps its timing under load:
    on -p 30 python3 gripper_link.py            (real Pico on /dev/ser4)
    python3 gripper_link.py --port /dev/ttyp3   (fake_pico.py for testing)

What it does, every 10 ms (100 Hz, absolute deadlines so it never drifts):
  1. read the newest FSR frame from the Pico (UART4),
  2. compare force with the active object's target / max (grip_profiles.json),
  3. step the servo angle: close slowly until target, hold, back off at once
     if either jaw goes above max,
  4. send the new angle to the Pico.
If no valid Pico frame arrives for 50 ms the link is STALE: we hold the angle.
If QNX goes silent, the Pico freezes the servo by itself after 100 ms.

Commands: one JSON object per UDP packet to 127.0.0.1:<cmd_port>, reply is
the status JSON.  {"cmd": "OPEN" | "GRIP" | "HOLD" | "RELAX" | "STATUS",
"object": "egg"}  (object only for GRIP).  See grip_cmd.py.
For calibrating the jaw travel: {"cmd": "ANGLE", "angle": 95} moves slowly to
that servo angle and stops early if either jaw feels calib_max_force.
Telemetry: status JSON sent by UDP to 127.0.0.1:<telemetry_port> at 20 Hz
(this is also our heartbeat for the supervisor).
"""

import argparse
import json
import os
import select
import socket
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def load_json(name):
    with open(os.path.join(HERE, "config", name)) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def xor(data):
    x = 0
    for b in data:
        x ^= b
    return x


def open_raw_port(path):
    """Raw 115200 8N1, non-blocking reads (same setup as mks_servo.py)."""
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = termios.B115200
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


class PicoLink:
    """Parses Pico->Pi frames and sends Pi->Pico angle commands."""
    FRAME_LEN = 10

    def __init__(self, fd):
        self.fd = fd
        self.buf = b""
        self.latest = None          # (fsr1, fsr2, angle, flags, seq)
        self.last_rx = None         # time.monotonic() of last valid frame
        self.frames_ok = self.frames_bad = self.seq_gaps = 0
        self.tx_seq = 0

    def poll(self):
        while select.select([self.fd], [], [], 0)[0]:
            chunk = os.read(self.fd, 256)
            if not chunk:
                break
            self.buf += chunk
        while len(self.buf) >= self.FRAME_LEN:
            i = self.buf.find(b"\xAA\x55")
            if i < 0:
                self.buf = self.buf[-1:]
                return
            self.buf = self.buf[i:]
            if len(self.buf) < self.FRAME_LEN:
                return
            fr = self.buf[:self.FRAME_LEN]
            if xor(fr[:9]) != fr[9]:
                self.frames_bad += 1
                self.buf = self.buf[1:]      # resync on the next 0xAA
                continue
            self.buf = self.buf[self.FRAME_LEN:]
            seq = fr[8]
            if self.latest is not None and seq != (self.latest[4] + 1) & 0xFF:
                self.seq_gaps += 1
            self.latest = (fr[2] | fr[3] << 8, fr[4] | fr[5] << 8, fr[6], fr[7], seq)
            self.last_rx = time.monotonic()
            self.frames_ok += 1

    def send(self, angle, hold):
        a = max(0, min(180, int(round(angle))))
        fr = bytes([0xAA, 0x56, a, 0x01 if hold else 0x00, self.tx_seq])
        self.tx_seq = (self.tx_seq + 1) & 0xFF
        try:
            os.write(self.fd, fr + bytes([xor(fr)]))
        except OSError:
            pass   # TX trouble shows up as the Pico freezing; nothing smarter to do


class Gripper:
    """The force-control state machine. One step() per 10 ms cycle.

    States: WAITING (no Pico yet), OPENING, OPEN, CLOSING, GRIPPED, HOLD,
            NO_OBJECT (closed fully, never reached target), OVER_FORCE (backed
            off 3 times, gave up and holds), STALE (link lost), MOVING (ANGLE).
    """

    def __init__(self, cfg, profiles):
        self.cfg, self.profiles = cfg, profiles
        self.state = "WAITING"
        self.angle = None            # commanded angle (float); None until known
        self.target = None           # ANGLE command target
        self.profile = None          # active {"target", "max"}
        self.obj = None
        self.slip = False            # sticky until the next command
        self.over_max = 0            # how many times we backed off (total)
        self.backoffs = 0            # back-offs during the current grip
        self.loaded = False          # reached target during the current grip
        self.was_over = False        # last cycle was over max (count events once)
        self.closing_dir = 1 if cfg["closed_angle"] > cfg["open_angle"] else -1

    def command(self, msg):
        cmd = str(msg.get("cmd", "")).upper()
        if cmd == "STATUS":
            return None
        if self.state in ("WAITING", "STALE"):
            return f"link not ready ({self.state})"
        if cmd == "GRIP":
            obj = msg.get("object")
            if obj not in self.profiles:
                return f"unknown object {obj!r}"
            self.obj, self.profile, self.state = obj, self.profiles[obj], "CLOSING"
            self.backoffs, self.loaded = 0, False
        elif cmd == "OPEN":
            self.state, self.profile, self.obj = "OPENING", None, None
        elif cmd == "HOLD":
            self.state = "HOLD"
        elif cmd == "RELAX":
            self.angle = self._toward_open(self.angle, self.cfg["relax_deg"])
            self.state, self.profile = "HOLD", None
        elif cmd == "ANGLE":
            self.target = max(0.0, min(180.0, float(msg.get("angle", self.angle))))
            self.state, self.profile, self.obj = "MOVING", None, None
        else:
            return f"unknown cmd {cmd!r}"
        self.slip = False
        return None

    def _toward_open(self, a, step):
        o = self.cfg["open_angle"]     # opening = the opposite way to closing
        return min(a + step, o) if self.closing_dir < 0 else max(a - step, o)

    def _toward_closed(self, a, step):
        c = self.cfg["closed_angle"]
        return max(a - step, c) if self.closing_dir < 0 else min(a + step, c)

    def step(self, link, now):
        cfg = self.cfg
        if link.latest is None:
            return
        fresh = (now - link.last_rx) * 1000 <= cfg["stale_ms"]
        if not fresh:
            self.state = "STALE"     # keep sending the same angle: hold
            return
        fsr1, fsr2, pico_angle, _, _ = link.latest
        if self.state in ("WAITING", "STALE"):
            # (Re)connected. Start from where the Pico says the servo is; if it
            # was never attached, the servo jumps to attach_angle (its centre,
            # where the jaws sit mid-travel), so that must be a safe spot.
            self.angle = float(pico_angle if not (link.latest[3] & 0x02) else cfg["attach_angle"])
            self.state = "HOLD"
        force, peak = (fsr1 + fsr2) / 2.0, max(fsr1, fsr2)

        # Force ceiling: checked every cycle in every state that squeezes.
        # Back off at once; while closing, try again at 1/4 speed, and after
        # 3 back-offs give up and just hold.
        # The Pico's next frame can still show the old high force, so we back
        # off on every high reading but count it as one event.
        over = bool(self.profile) and peak > self.profile["max"]
        if over:
            self.angle = self._toward_open(self.angle, cfg["backoff_deg"])
            if not self.was_over:
                self.over_max += 1
                self.backoffs += 1
            if self.state == "CLOSING" and self.backoffs >= 3:
                self.state = "OVER_FORCE"   # gave up: holding, NOT a good grip
        self.was_over = over
        if over:
            return

        if self.state == "MOVING":
            if peak > cfg["calib_max_force"]:
                self.state = "HOLD"          # touched something: stop right here
            else:
                s = cfg["calib_step_deg"]
                self.angle += max(-s, min(s, self.target - self.angle))
                if self.angle == self.target:
                    self.state = "HOLD"
        elif self.state == "OPENING":
            self.angle = self._toward_open(self.angle, cfg["open_step_deg"])
            if self.angle == cfg["open_angle"]:
                self.state = "OPEN"
        elif self.state == "CLOSING":
            if force >= self.profile["target"]:
                self.state, self.loaded = "GRIPPED", True
            elif self.angle == cfg["closed_angle"]:
                self.state = "NO_OBJECT"
            else:
                step = cfg["close_step_deg"] / (4 if self.backoffs else 1)
                self.angle = self._toward_closed(self.angle, step)
        elif self.state == "GRIPPED":
            if self.loaded and force < cfg["slip_fraction"] * self.profile["target"]:
                self.slip = True     # motion reads this and stops / re-grips

    def hold_flag(self):
        return self.state not in ("OPENING", "CLOSING", "MOVING")


class LoopTimer:
    """Absolute-deadline periodic timer with jitter stats per 1 s window."""

    def __init__(self, hz):
        self.period = 1.0 / hz
        self.next = time.monotonic() + self.period
        self.reset_window()
        self.worst_ever_ms = 0.0
        self.missed_total = 0
        self.last = {"jitter_avg_ms": 0, "jitter_max_ms": 0, "missed": 0}

    def reset_window(self):
        self.win_max_ms = 0.0
        self.win_sum_ms = 0.0
        self.win_n = 0
        self.win_missed = 0

    def roll(self):
        """Close the 1 s stats window (call when win_n reaches the loop rate)."""
        self.last = {"jitter_avg_ms": round(self.win_sum_ms / max(1, self.win_n), 3),
                     "jitter_max_ms": round(self.win_max_ms, 3),
                     "missed": self.win_missed}
        self.reset_window()

    def stats(self):
        return dict(self.last, worst_ever_ms=round(self.worst_ever_ms, 2),
                    missed_total=self.missed_total, period_ms=round(self.period * 1000, 2))

    def wait(self):
        """Sleep until the next deadline; return lateness in ms."""
        while True:
            d = self.next - time.monotonic()
            if d <= 0:
                break
            time.sleep(d)
        late_ms = (time.monotonic() - self.next) * 1000
        self.next += self.period
        if late_ms > self.period * 1000:            # a whole period late: missed
            self.win_missed += 1
            self.missed_total += 1
            skipped = int(late_ms / 1000 / self.period)
            self.next += skipped * self.period      # don't burst to catch up
        self.win_max_ms = max(self.win_max_ms, late_ms)
        self.worst_ever_ms = max(self.worst_ever_ms, late_ms)
        self.win_sum_ms += late_ms
        self.win_n += 1
        return late_ms


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--port", help="override config port (e.g. fake_pico pty)")
    ap.add_argument("--quiet", action="store_true", help="no 1 s status lines")
    args = ap.parse_args()

    cfg = load_json("gripper.json")
    profiles = load_json("grip_profiles.json")
    port = args.port or cfg["port"]
    link = PicoLink(open_raw_port(port))
    grip = Gripper(cfg, profiles)

    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd_sock.bind(("127.0.0.1", cfg["cmd_port"]))
    cmd_sock.setblocking(False)
    tel_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tel_addr = ("127.0.0.1", cfg["telemetry_port"])

    timer = LoopTimer(cfg["loop_hz"])
    tel_every = max(1, int(cfg["loop_hz"] / cfg["telemetry_hz"]))
    cycle = 0
    print(f"gripper_link: port={port} {cfg['loop_hz']} Hz, cmd udp {cfg['cmd_port']}, "
          f"telemetry udp {cfg['telemetry_port']}, pid {os.getpid()}", flush=True)

    def status():
        f = link.latest
        now = time.monotonic()
        return {
            "t": time.time(), "state": grip.state, "object": grip.obj,
            "angle": None if grip.angle is None else round(grip.angle, 1),
            "fsr1": f and f[0], "fsr2": f and f[1], "pico_angle": f and f[2],
            "pico_frozen": bool(f and f[3] & 1), "slip": grip.slip,
            "over_max": grip.over_max, "profile": grip.profile,
            "link_age_ms": None if link.last_rx is None else round((now - link.last_rx) * 1000, 1),
            "frames_ok": link.frames_ok, "frames_bad": link.frames_bad, "seq_gaps": link.seq_gaps,
            "timing": timer.stats(),
        }

    while True:
        late = timer.wait()
        now = time.monotonic()
        link.poll()

        # Commands from motion / grip_cmd.py (non-blocking).
        while True:
            try:
                data, addr = cmd_sock.recvfrom(1024)
            except BlockingIOError:
                break
            try:
                err = grip.command(json.loads(data))
            except ValueError:
                err = "bad json"
            reply = status()
            reply["ok"], reply["error"] = err is None, err
            cmd_sock.sendto(json.dumps(reply).encode(), addr)

        grip.step(link, now)
        if grip.angle is not None:
            link.send(grip.angle, grip.hold_flag())

        cycle += 1
        if cycle % tel_every == 0:
            try:
                tel_sock.sendto(json.dumps(status()).encode(), tel_addr)
            except OSError:
                pass
        if timer.win_n >= cfg["loop_hz"]:            # once per second
            timer.roll()
            last_window = timer.last
            if not args.quiet:
                s = status()
                print(f"{s['state']:9s} ang={s['angle']} fsr={s['fsr1']},{s['fsr2']} "
                      f"age={s['link_age_ms']}ms ok={s['frames_ok']} bad={s['frames_bad']} "
                      f"gaps={s['seq_gaps']} jitter avg={last_window['jitter_avg_ms']} "
                      f"max={last_window['jitter_max_ms']} missed={last_window['missed']}",
                      flush=True)


if __name__ == "__main__":
    main()
