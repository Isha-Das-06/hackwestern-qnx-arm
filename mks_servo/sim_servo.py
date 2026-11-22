"""
sim_servo: a fake MKS SERVO42C with the same methods motion.py uses from
Servo42C, so the arm logic can be tested on the Pi with no motors attached.

    python3 motion.py --sim

It copies the real quirks that matter:
  - firmware "1.0": the encoder wraps every revolution (0-360) and 0xFD moves
    are ignored (use run() + stop()), no stall protection;
  - firmware "1.1": multi-turn encoder, exact pulse moves, moves_completed.
  - optional hard stops (`hard_min`, `hard_max`), so homing and calibrating
    against them works: the shaft stops there and the shaft error grows, like
    a real blocked motor.
Set SIM_JAM=<name> in the environment to make that motor jam after 1 s of
movement (for testing the stall / progress checks).
"""

import os
import threading
import time

from mks_servo import Servo42C, ServoError

DEG_PER_S_PER_SPEED = 3.8      # same estimate motion.py uses for time limits


class FakeServo:
    PULSES_PER_REV = Servo42C.PULSES_PER_REV

    def __init__(self, port, addr=0xE0, name=None, firmware="1.1", hard_min=None,
                 hard_max=None, start_deg=0.0, speedup=1.0, **_):
        self.name = name or port
        self.has_checksum = firmware != "1.0"
        self.moves_completed = 0
        self.consecutive_failures = 0
        self.enabled = False
        self.actual = start_deg       # shaft position, degrees (multi-turn)
        self.commanded = start_deg    # where the driver wants the shaft
        self.vel = 0.0                # deg/s while running
        self.remaining = None         # deg left in a pulse move (V1.1), or None
        self.hard_min, self.hard_max = hard_min, hard_max
        self.speedup = float(speedup or 1.0)
        self.jam = os.environ.get("SIM_JAM") == self.name
        self.moving_since = None
        self.t = time.monotonic()
        self.lock = threading.Lock()

    # --- physics ------------------------------------------------------------
    def _tick(self):
        now = time.monotonic()
        dt, self.t = now - self.t, now
        if not self.enabled or self.vel == 0:
            return
        step = self.vel * dt
        if self.remaining is not None:
            if abs(step) >= self.remaining:
                step = self.remaining if step > 0 else -self.remaining
                self.vel, self.remaining = 0.0, None
                self.moves_completed += 1
            else:
                self.remaining -= abs(step)
        self.commanded += step
        jammed = self.jam and self.moving_since and now - self.moving_since > 1.0
        if not jammed:
            self.actual = self.commanded
            if self.hard_min is not None and self.actual < self.hard_min:
                self.actual = self.hard_min
            if self.hard_max is not None and self.actual > self.hard_max:
                self.actual = self.hard_max
        if self.vel == 0:
            self.moving_since = None

    def _start(self, direction, speed, deg=None):
        self._tick()
        sign = 1 if direction == 1 else -1          # 1 = CCW = positive here
        self.vel = sign * speed * DEG_PER_S_PER_SPEED * self.speedup
        self.remaining = deg
        self.moving_since = self.moving_since or time.monotonic()

    # --- the Servo42C methods motion.py uses --------------------------------
    def init(self):
        self.enabled = False

    def enable(self, on=True):
        with self.lock:
            self._tick()
            self.enabled = on

    def stop(self):
        with self.lock:
            self._tick()
            self.vel, self.remaining = 0.0, None
            self.commanded = self.actual
            self.moving_since = None

    def run(self, direction, speed):
        with self.lock:
            self._start(direction, speed)

    def move(self, direction, speed, pulses, retries=0):
        with self.lock:
            if self.has_checksum:              # V1.0 acks 0xFD but never runs it
                self._start(direction, speed, pulses * 360.0 / self.PULSES_PER_REV)

    def is_stalled(self):
        with self.lock:
            self._tick()
            if self.has_checksum and self.jam and self.moving_since \
                    and time.monotonic() - self.moving_since > 1.5:
                return True
            return False

    def clear_stall(self):
        pass

    def set_protection(self, on=True):
        if not self.has_checksum:
            raise ServoError(f"{self.name}: no reply to 0x88")

    def encoder_degrees(self):
        with self.lock:
            self._tick()
            return self.actual % 360.0 if not self.has_checksum else self.actual

    def shaft_error_degrees(self):
        with self.lock:
            self._tick()
            return max(-30.0, min(30.0, self.commanded - self.actual))

    def safe_stop(self):
        self.stop()

    def release(self):
        self.stop()
        self.enabled = False

    def close(self):
        pass
