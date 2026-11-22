"""
arm_link: connects this vision app to the QNX arm (pointing.py --arm).

- PICK requests go to motion.py over local UDP (127.0.0.1:5611):
      {"cmd": "PICK", "from": 1, "to": 3, "label": "egg"}
  motion picks the grip force for that label itself (grip_profiles.json on QNX),
  so the safety-critical number never comes from this process.
- A 5 Hz heartbeat goes to the supervisor (127.0.0.1:5622). If it stops (this
  app crashed), the supervisor pauses the arm, restarts us, and resumes.
  It carries the number of hands in view, and is sent at once when that
  changes: the supervisor pauses the arm while any hand is in view.
- The supervisor answers with how long the START window has left and its
  FAULT, if any ({"select_s": 12.4, "fault": null}); pointing only starts a new
  move while the window is open. The console's START button asks the supervisor
  to open it, and the console shows the fault (START is refused until RESET).

Same interface as FakeRobot in pointing.py: busy(), armed(), send_pick(), last, last_t.
Never blocks the camera loop: every socket call here is non-blocking.
"""

import json
import socket
import time

from classifier import NAMES


class ArmRobot:
    gate = True                       # selection needs START

    def __init__(self, motion_port=5611, heartbeat_port=5622):
        self.motion = ("127.0.0.1", motion_port)
        self.hb = ("127.0.0.1", heartbeat_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.status = {}              # latest reply from motion
        self.status_t = 0.0
        self.next_poll = 0.0
        self.next_hb = 0.0
        self.pending_until = 0.0      # just sent a PICK: count as busy until motion answers
        self.select_until = 0.0       # START window, from the supervisor
        self.fault = None             # supervisor's FAULT reason, or None
        self.start_n = 0              # console START presses (the supervisor acts on changes)
        self.last_hands = None
        self.last, self.last_t = "", 0.0

    def _send(self, addr, msg):
        try:
            self.sock.sendto(json.dumps(msg).encode(), addr)
        except OSError:
            pass

    def poll(self):
        """Read replies from motion and the supervisor; ask motion for status at 5 Hz."""
        while True:
            try:
                data = self.sock.recv(16384)
            except (BlockingIOError, OSError):
                break
            try:
                r = json.loads(data)
            except ValueError:
                continue
            if "select_s" in r:                       # from the supervisor
                self.select_until = time.monotonic() + float(r["select_s"])
                self.fault = r.get("fault")
                continue
            self.status, self.status_t = r, time.monotonic()
            if r.get("busy"):
                self.pending_until = 0.0
            elif r.get("ok") is False and self.pending_until:
                self.last = f"[arm] refused: {r.get('error')}"
                print(self.last, flush=True)
                self.pending_until = 0.0
        now = time.monotonic()
        if now >= self.next_poll:
            self.next_poll = now + 0.2
            self._send(self.motion, {"cmd": "STATUS"})

    def busy(self):
        self.poll()
        fresh = time.monotonic() - self.status_t < 1.0
        return time.monotonic() < self.pending_until or (fresh and bool(self.status.get("busy")))

    def armed(self):
        return time.monotonic() < self.select_until

    def select_left(self):
        return max(0.0, self.select_until - time.monotonic())

    def request_start(self):
        """Console START: ask the supervisor to open the window (next heartbeat, now)."""
        self.start_n += 1
        self.next_hb = 0.0

    def send_pick(self, src, label, dst, grip):
        name = NAMES[label]
        lo, hi = grip.get(name, (None, None))
        self.last = f"[pick] from={src + 1} to={dst + 1} obj={name} grip=[{lo},{hi}] -> motion"
        self.last_t = time.time()
        print(self.last, flush=True)
        self.pending_until = time.monotonic() + 0.8
        self.select_until = 0.0       # one START = one move
        self._send(self.motion, {"cmd": "PICK", "from": src + 1, "to": dst + 1, "label": name})

    def heartbeat(self, fps, state, preds, frame_ms=None, hands=0):
        """Call every frame; sends 5 times a second, and at once when the hand count changes."""
        now = time.monotonic()
        if now < self.next_hb and hands == self.last_hands:
            return
        self.next_hb = now + 0.2
        self.last_hands = hands
        self._send(self.hb, {
            "t": time.time(), "fps": round(fps, 1), "state": state, "hands": hands,
            "start_n": self.start_n,
            "labels": [NAMES[p[0]] for p in preds],
            "confidence": [round(float(p[1]), 2) for p in preds],
            "frame_ms": frame_ms, "arm": self.status.get("state")})
