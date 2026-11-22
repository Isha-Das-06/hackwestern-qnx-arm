"""
motion: owns both SERVO42C ports and runs pick-and-place.

    on -p 30 python3 motion.py          real motors (/dev/ser3, /dev/ser5)
    python3 motion.py --sim             fake motors (sim_servo.py), no hardware

Pick sequence (one command from vision does all of it):
    IDLE -> MOVE_TO_PICK -> LOWER -> GRIP -> LIFT -> MOVE_TO_PLACE -> LOWER
         -> RELEASE -> HOME -> IDLE          and FAULT from anywhere.

Joint units: the lift works in mm of carriage travel, the base in degrees of
yaw. gear_ratio in config/arm.json converts them to motor degrees.

Safety rules, each one sentence:
  - Pocket positions are fixed, taught joint positions; no IK.
  - Homing seeks the lift's bottom stop at power-up (and the base's, if set).
  - Every target is checked against the joint's soft limits before moving, and
    motion refuses to run if any pocket or pose is outside them.
  - Targets are absolute, so errors never add up from move to move.
  - Both joints move together: speeds are scaled so they arrive together.
  - If a motor falls too far behind its commanded angle, something is in the
    way: stop, stop pushing on it, hold, FAULT.
  - Every move has a time limit, and if a joint stops making progress we stop
    (motor 2's V1.0 firmware has no stall detection of its own).
  - Any fault = stop and HOLD (motors stay enabled, gripper keeps its grip).
  - PAUSE (vision down, or a hand in view) stops and holds, and RESUME
    continues the same move from where the arm is.
  - If the object slips while carrying it, we stop and hold (FAULT).

Commands: one JSON object per UDP packet to 127.0.0.1:<cmd_port>; the reply
is the status. See arm_cmd.py.
  PICK {from, to, label}  HOME  JOG {joint, amount}  GOTO {pocket | "home"}
  TEACH {pocket}  CALIBRATE
  PAUSE  RESUME  FAULT {reason}  STOP  RESET  STATUS
Taught pockets and measured travel are saved in config/taught.json.
Telemetry / heartbeat: status JSON to 127.0.0.1:<telemetry_port> at 10 Hz.
"""

import argparse
import json
import os
import queue
import socket
import threading
import time

from gripper_link import HERE, LoopTimer, load_json
from mks_servo import Servo42C, ServoError
from servo_test import SEEK_BACKOFF_DEG, AngleTracker, run_until_blocked

TAUGHT = os.path.join(HERE, "config", "taught.json")


def load_taught():
    try:
        with open(TAUGHT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


class Fault(Exception):
    """Something went wrong: stop, hold, report."""


class Rejected(Exception):
    """A command we refuse without moving (bad pocket, out of limits...)."""


class Joint:
    """One arm joint = one SERVO42C, in the joint's own unit (lift mm, base deg)."""

    def __init__(self, name, cfg, motor):
        self.name, self.cfg, self.m = name, cfg, motor
        self.ratio = cfg["gear_ratio"]
        self.unit = cfg.get("unit", "deg")
        self.zero = 0.0                   # motor degrees where the joint is at 0
        self.lo, self.hi = cfg["min"], cfg["max"]   # soft limits (narrowed by measured travel)
        self.tracker = None if motor.has_checksum else AngleTracker(motor)

    def reset_tracker(self):
        """V1.0 only: after a seek turned the shaft without us polling it."""
        if self.tracker is not None:
            self.tracker = AngleTracker(self.m)

    def motor_deg(self):
        """Multi-turn motor position. V1.0's encoder wraps, so we unwrap it."""
        if self.tracker is None:
            return self.m.encoder_degrees()
        self.tracker.update()
        return self.tracker.total

    def deg(self):
        return (self.motor_deg() - self.zero) / self.ratio

    def check_limits(self, target):
        if not self.lo <= target <= self.hi:
            raise Rejected(f"{self.name} {target:.1f} {self.unit} is outside its limits "
                           f"[{self.lo:.1f}, {self.hi:.1f}]")

    def direction(self, motor_delta):
        bit = self.cfg["dir_bit_positive"]
        return bit if motor_delta > 0 else bit ^ 1


class Motion:
    def __init__(self, cfg, sim):
        self.cfg = cfg
        self.gripper_cfg = load_json("gripper.json")
        self.profiles = load_json("grip_profiles.json")
        self.state = "STARTING"
        self.step = ""
        self.homed = False
        self.fault = None
        self.job = None
        self.picks_done = 0
        self.last_result = None
        self.joints_now = {}
        self.jobs = queue.Queue()
        self.abort = threading.Event()     # FAULT / STOP: stop now, hold
        self.paused = threading.Event()    # PAUSE: stop and hold, then carry on
        self.carrying = False              # object in the jaws: watch for slip
        self.sim = sim
        self.joints = {}
        self.taught = load_taught()                 # Pi-owned: pockets + measured travel
        self.cfg["pockets"].update(self.taught.get("pockets", {}))
        self.grip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.grip_sock.settimeout(0.3)

    # ---------------------------------------------------------------- setup
    def open_motors(self):
        for name, jc in self.cfg["joints"].items():
            if self.sim:
                from sim_servo import FakeServo
                # Fake hard stops: the lift between motor 0 and 334 deg (70 mm,
                # starting low), the base at +-80 deg either side of where it starts.
                m = FakeServo(jc["port"], name=name, firmware=jc["firmware"],
                              hard_min=0.0 if name == "lift" else -80.0,
                              hard_max=334.0 if name == "lift" else 80.0,
                              start_deg=60.0 if name == "lift" else 0.0,
                              speedup=self.sim)
            else:
                m = Servo42C(jc["port"], addr=jc["addr"], name=name, firmware=jc["firmware"])
            self.joints[name] = Joint(name, jc, m)
            self.prepare_motor(self.joints[name])
        self.apply_limits()

    def prepare_motor(self, j):
        """Surya's init (accel, microsteps, stall protection), then enable and hold."""
        j.m.init()
        if j.m.has_checksum and not j.cfg.get("stall_protection", True):
            # A tripped stall protection RELEASES the shaft, and the lift
            # backdrives: it would drop. Our lag check stops it instead.
            j.m.set_protection(False)
        j.m.enable(True)        # init ends released; an arm must hold

    def apply_limits(self):
        """Soft limits = configured range, narrowed to the measured travel minus a margin."""
        for name, j in self.joints.items():
            j.lo, j.hi = j.cfg["min"], j.cfg["max"]
            travel = self.taught.get("travel", {}).get(name)
            if travel:
                margin = j.cfg.get("limit_margin", 0.0)
                j.lo, j.hi = max(j.lo, travel[0] + margin), min(j.hi, travel[1] - margin)

    def check_config(self):
        """Refuse to run if any pocket or pose is outside the soft limits."""
        poses = {f"pocket {p}": v for p, v in self.cfg["pockets"].items()}
        poses["home_pose"] = self.cfg["home_pose"]
        poses["travel height"] = {"lift": self.cfg["travel_lift"]}
        bad = [f"{label} {name}={v} outside [{self.joints[name].lo:.1f}, {self.joints[name].hi:.1f}]"
               for label, pose in poses.items() for name, v in pose.items()
               if not self.joints[name].lo <= v <= self.joints[name].hi]
        if bad:
            raise Fault("config: " + "; ".join(bad))

    def save_taught(self):
        with open(TAUGHT + ".tmp", "w") as f:
            json.dump(self.taught, f, indent=2)
        os.replace(TAUGHT + ".tmp", TAUGHT)

    # -------------------------------------------------------- gripper client
    def gripper(self, msg):
        try:
            self.grip_sock.sendto(json.dumps(msg).encode(),
                                  ("127.0.0.1", self.gripper_cfg["cmd_port"]))
            return json.loads(self.grip_sock.recv(4096))
        except (socket.timeout, OSError, ValueError):
            raise Fault("gripper_link is not answering")

    def gripper_until(self, msg, good, bad, timeout):
        r = self.gripper(msg)
        if not r.get("ok", True):
            raise Fault(f"gripper refused {msg}: {r.get('error')}")
        deadline = time.monotonic() + timeout
        while True:
            self.checkpoint()
            r = self.gripper({"cmd": "STATUS"})
            if r["state"] in good:
                return r
            if r["state"] in bad:
                return r
            if time.monotonic() > deadline:
                raise Fault(f"gripper stuck in {r['state']} after {msg['cmd']}")
            time.sleep(0.05)

    # ------------------------------------------------------- stop and hold
    def hold_all(self):
        for j in self.joints.values():
            j.m.safe_stop()          # stop, stay enabled (holding torque)

    def checkpoint(self):
        """Called often by every loop: obey FAULT/STOP and PAUSE."""
        if self.abort.is_set():
            raise Fault(self.fault or "stopped")

    def wait_if_paused(self):
        """PAUSE (vision down or a hand in view): hold here until RESUME."""
        if not self.paused.is_set():
            return
        self.hold_all()
        before, self.state = self.state, "PAUSED"
        while self.paused.is_set():
            self.checkpoint()
            time.sleep(0.05)
        self.state = before

    def relieve(self, j, back_bit, lag):
        """After hitting something: pull the commanded angle back to where the
        shaft actually is, so the motor stops pushing on it. Best effort."""
        try:
            j.m.stop()
            speed = self.cfg["min_speed"]
            if j.m.has_checksum:
                j.m.move(back_bit, speed, int(abs(lag) / 360.0 * j.m.PULSES_PER_REV))
                time.sleep(abs(lag) / (speed * self.cfg["deg_per_s_per_speed"]) + 0.1)
            else:
                j.m.run(back_bit, speed)
                deadline = time.monotonic() + 1.0
                while abs(j.m.shaft_error_degrees()) > 1.5 and time.monotonic() < deadline:
                    time.sleep(0.02)
            j.m.stop()
        except (ServoError, OSError):
            pass

    # ------------------------------------------------------------- moving
    def move_to(self, targets, step, approach=True):
        """Coordinated absolute move of one or both joints, in joint units."""
        self.step = step
        if self.homed:
            for name, t in targets.items():
                self.joints[name].check_limits(t)
        c = self.cfg
        tol = {n: self.joints[n].cfg.get("tolerance", c["tolerance"]) for n in targets}
        if approach and self.homed:
            # Gear play: a joint with "approach" always finishes its move turning
            # that way, so the play is taken up the same way at every pocket.
            for name, t in targets.items():
                j = self.joints[name]
                side = j.cfg.get("approach")
                if side and (t - j.deg()) * side < -tol[name] * 0.5:
                    pre = t - side * j.cfg["approach_overshoot"]
                    if j.lo <= pre <= j.hi:
                        self.move_to(dict(targets, **{name: pre}), step, approach=False)
                        self.step = step
        tries = 0                           # 1 move + up to 2 small corrections
        while tries < 3:
            self.checkpoint()
            self.wait_if_paused()
            todo = {}
            for name, t in targets.items():
                j = self.joints[name]
                d = (t - j.deg()) * j.ratio         # motor degrees to go
                if abs(d) / j.ratio > tol[name] * 0.5:
                    todo[name] = d
            if not todo:
                return
            if self._run_move(todo):        # False = paused part-way: re-plan, same try
                tries += 1
        for name, t in targets.items():
            j = self.joints[name]
            err = abs(j.deg() - t)
            if err > tol[name]:
                raise Fault(f"{name} missed its target by {err:.1f} {j.unit}")

    def _run_move(self, todo):
        c = self.cfg
        k = c["deg_per_s_per_speed"]
        # Same arrival time for all joints: the slowest one sets the time. Short
        # corrections get at least min_move_s, so they run slowly and land.
        # A joint with "deg_per_s" turns at that fixed rate whatever the speed
        # byte says (the base's V1.0 firmware: ~32-45 deg/s at every speed).
        def seconds(n, d):
            jc = self.joints[n].cfg
            return abs(d) / (jc["deg_per_s"] if "deg_per_s" in jc else jc["max_speed"] * k)
        t_move = max([seconds(n, d) for n, d in todo.items()] + [c["min_move_s"]])
        active = {}
        for name, d in todo.items():
            j = self.joints[name]
            speed = max(c["min_speed"], min(j.cfg["max_speed"], round(abs(d) / (t_move * k))))
            start = j.motor_deg()
            pulses = int(abs(d) / 360.0 * j.m.PULSES_PER_REV)
            p0 = j.m.pulses_received()
            if j.m.has_checksum:      # V1.1: exact pulse move, the driver stops itself
                done0 = j.m.moves_completed
                j.m.move(j.direction(d), speed, pulses)
            else:                     # V1.0: run, we stop it on its pulse counter
                done0 = None
                j.m.run(j.direction(d), speed)
            active[name] = {"d": d, "start": start, "done0": done0, "last": start,
                            "p0": p0, "pulses": pulses,
                            "speed": speed, "over": 0, "prev": (time.monotonic(), 0), "v": 0.0}
        deadline = time.monotonic() + t_move * c["timeout_factor"] + c["timeout_margin_s"]
        next_progress = time.monotonic() + c["progress_check_s"]
        next_stall = next_slip = time.monotonic() + 0.5
        try:
            while active:
                time.sleep(0.02)
                self.checkpoint()
                if self.paused.is_set():
                    self.wait_if_paused()
                    return False
                # Obstruction: the shaft falls behind the commanded angle (0x39).
                # Turning freely it lags 2-5 motor deg; blocked, it passes 10 in ~0.2 s.
                for name, a in active.items():
                    j = self.joints[name]
                    lag = j.m.shaft_error_degrees()
                    a["lag"] = abs(lag)
                    a["over"] = a["over"] + 1 if abs(lag) >= j.cfg["lag_limit_motor_deg"] else 0
                    if a["over"] >= c["lag_polls"]:
                        for other in active:
                            self.joints[other].m.stop()
                        self.relieve(j, j.direction(a["d"]) ^ 1, lag)
                        raise Fault(f"{name} blocked: {abs(lag):.1f} motor deg behind "
                                    f"(something in the way)")
                now = time.monotonic()
                self.joints_now = {n: round(j.deg(), 2) for n, j in self.joints.items()}
                for name in list(active):
                    j, a = self.joints[name], active[name]
                    pos = j.motor_deg()
                    moved = (pos - a["start"]) * (1 if a["d"] > 0 else -1)
                    if a["done0"] is None:
                        # V1.0: its pulse counter is the commanded position, and the
                        # shaft settles exactly there after a stop (measured within
                        # 0.4 deg). Stop when the counter reaches the target, early by
                        # what it counts while the stop is on its way.
                        cmd = abs(j.m.pulses_received() - a["p0"])
                        t_prev, c_prev = a["prev"]
                        now_t = time.monotonic()
                        if now_t > t_prev:
                            a["v"] = (cmd - c_prev) / (now_t - t_prev)
                        a["prev"] = (now_t, cmd)
                        if cmd >= a["pulses"] - c["v10_stop_lead_s"] * a["v"]:
                            j.m.stop()
                            del active[name]
                    # V1.1: done on its "move finished" frame, or when its pulse
                    # counter has reached the commanded count (the shaft itself sags
                    # under load, so its position can't tell).
                    elif j.m.moves_completed > a["done0"] or \
                            abs(j.m.pulses_received() - a["p0"]) >= a["pulses"] - 2:
                        del active[name]
                if now > next_progress:
                    for name, a in active.items():
                        pos = self.joints[name].motor_deg()
                        if abs(pos - a["last"]) < c["min_progress_motor_deg"]:
                            raise Fault(f"{name} is not moving (jammed or stalled)")
                        a["last"] = pos
                    next_progress = now + c["progress_check_s"]
                if now > next_stall:
                    # Only where the driver's own stall protection is on; with it
                    # off (lift) the lag check does this job, and 0x3E's reply can
                    # be confused with the move-started frame.
                    for name in active:
                        j = self.joints[name]
                        if j.m.has_checksum and j.cfg.get("stall_protection", True) \
                                and j.m.is_stalled():
                            raise Fault(f"{name} driver reports a stall")
                    next_stall = now + 0.5
                if self.carrying and now > next_slip:
                    r = self.gripper({"cmd": "STATUS"})
                    if r.get("slip") or r["state"] not in ("GRIPPED", "HOLD"):
                        raise Fault(f"object slipped or grip lost ({r['state']})")
                    next_slip = now + 0.1
                if now > deadline:
                    raise Fault(f"move timed out ({', '.join(active)})")
            # V1.0 keeps closing on its commanded angle after the stop (slowly for
            # the last couple of degrees): wait until it's there.
            settle_by = time.monotonic() + c["v10_settle_s"]
            for n in todo:
                m = self.joints[n].m
                while not m.has_checksum and abs(m.shaft_error_degrees()) > c["v10_settle_lag_deg"] \
                        and time.monotonic() < settle_by:
                    time.sleep(0.03)
            return True
        except BaseException:
            self.hold_all()
            raise

    # ------------------------------------------------------------ the jobs
    def seek(self, j, toward):
        """Drive a joint slowly into its hard stop (toward = +1 / -1 in joint
        units). Returns motor degrees turned before contact; ends
        SEEK_BACKOFF_DEG motor degrees off the stop, holding."""
        hj = self.cfg["homing"][j.name]
        bit = j.cfg["dir_bit_positive"] if toward > 0 else j.cfg["dir_bit_positive"] ^ 1
        turned = run_until_blocked(j.m, bit, self.cfg["homing"]["seek_speed"],
                                   hj["seek_error_deg"], hj["seek_max_motor_deg"],
                                   protection_after=j.cfg.get("stall_protection", True))
        j.reset_tracker()
        return turned

    def home_joint(self, j):
        hj = self.cfg["homing"][j.name]
        if hj["mode"] == "hard_stop":
            self.step = f"{j.name}: seeking its stop"
            self.seek(j, hj["toward"])
            here = hj["stop_at"] - hj["toward"] * SEEK_BACKOFF_DEG / j.ratio
        else:
            here = hj["marked_at"]          # the arm was parked on its mark
        j.zero = j.motor_deg() - here * j.ratio

    def do_home(self):
        """Lift first (it seeks up, away from the docks), make sure the jaws are
        at least at travel height, then the base, then the home pose."""
        self.state = "HOMING"
        self.homed = False
        lift = self.joints["lift"]
        self.home_joint(lift)
        if lift.deg() < self.cfg["travel_lift"]:
            self.move_to({"lift": self.cfg["travel_lift"]}, "lift to travel height")
        self.home_joint(self.joints["base"])
        self.homed = True
        self.check_config()
        self.move_to(self.cfg["home_pose"], "going to home pose")

    def do_calibrate(self):
        """Measure the real travel of joints with calibrate_both_ends by seeking
        both stops, and save it to taught.json (it narrows the soft limits).
        The far stop also re-zeroes the joint, so no separate homing is needed."""
        self.state = "CALIBRATING"
        self.homed = False
        self.move_to({"lift": self.cfg["travel_lift"]}, "lift to travel height")
        travel = self.taught.setdefault("travel", {})
        for name, j in self.joints.items():
            hj = self.cfg["homing"][name]
            if not hj.get("calibrate_both_ends"):
                continue
            self.step = f"{name}: seeking its first stop"
            self.seek(j, hj["toward"])
            self.step = f"{name}: seeking the other stop"
            span = (self.seek(j, -hj["toward"]) + SEEK_BACKOFF_DEG) / j.ratio
            far = hj["stop_at"] - hj["toward"] * span
            here = far + hj["toward"] * SEEK_BACKOFF_DEG / j.ratio
            j.zero = j.motor_deg() - here * j.ratio
            travel[name] = sorted([round(hj["stop_at"], 2), round(far, 2)])
            print(f"motion: {name} travel {travel[name]} {j.unit}", flush=True)
        self.save_taught()
        self.apply_limits()
        self.homed = True
        self.check_config()
        self.move_to(self.cfg["home_pose"], "going to home pose")

    def do_pick(self, src, dst, label):
        P, lift = self.cfg["pockets"], self.cfg["travel_lift"]
        self.state = "MOVE_TO_PICK"
        r = self.gripper_until({"cmd": "OPEN"}, ("OPEN",), (), self.cfg["release_timeout_s"])
        self.move_to({"lift": lift, "base": P[src]["base"]}, f"to pocket {src}")
        self.state = "LOWER"
        self.move_to({"lift": P[src]["lift"]}, f"down into pocket {src}")
        self.state = "GRIP"
        self.step = f"gripping {label}"
        r = self.gripper_until({"cmd": "GRIP", "object": label}, ("GRIPPED",),
                               ("NO_OBJECT", "OVER_FORCE"), self.cfg["grip_timeout_s"])
        if r["state"] != "GRIPPED":
            # Nothing safely held: let go (object is resting in its pocket), go home.
            self.gripper_until({"cmd": "OPEN"}, ("OPEN",), (), self.cfg["release_timeout_s"])
            self.state = "HOME"
            self.move_to({"lift": lift}, "up (grip failed)")
            self.move_to(self.cfg["home_pose"], "home (grip failed)")
            return f"grip failed: {r['state']}"
        self.carrying = True
        self.state = "LIFT"
        self.move_to({"lift": lift}, f"lifting {label}")
        self.state = "MOVE_TO_PLACE"
        self.move_to({"lift": lift, "base": P[dst]["base"]}, f"to pocket {dst}")
        self.state = "LOWER"
        self.move_to({"lift": P[dst]["lift"]}, f"down into pocket {dst}")
        self.state = "RELEASE"
        self.step = f"releasing {label}"
        self.carrying = False
        self.gripper_until({"cmd": "OPEN"}, ("OPEN",), (), self.cfg["release_timeout_s"])
        self.state = "HOME"
        self.move_to({"lift": lift}, "up")
        self.move_to(self.cfg["home_pose"], "home")
        self.picks_done += 1
        return "done"

    def do_goto(self, where, high=False):
        """Go to a pocket (or "home") the way a pick does: travel height, turn,
        lower (unless high: stay at travel height above it)."""
        self.state = "GOTO"
        if where == "home":
            self.move_to(self.cfg["home_pose"], "home")
            return
        P, lift = self.cfg["pockets"], self.cfg["travel_lift"]
        if self.joints["lift"].deg() < lift - self.cfg["tolerance"]:
            self.move_to({"lift": lift}, "up to travel height")
        self.move_to({"lift": lift, "base": P[where]["base"]}, f"to pocket {where}")
        if not high:
            self.move_to({"lift": P[where]["lift"]}, f"down into pocket {where}")

    def do_jog(self, name, amount):
        self.state = "JOG"
        j = self.joints[name]
        self.move_to({name: j.deg() + amount}, f"jog {name} {amount:+.1f} {j.unit}")

    def worker(self):
        """The only thread that talks to the motors."""
        try:
            self.open_motors()
            self.state = "UNHOMED"
            if self.cfg.get("auto_home"):
                self.jobs.put(("HOME",))
        except (ServoError, OSError) as e:
            self.set_fault(f"motor setup failed: {e}")
        while True:
            try:
                job = self.jobs.get(timeout=0.2)
            except queue.Empty:
                job = None
            try:
                if self.joints:
                    self.joints_now = {n: round(j.deg(), 2) for n, j in self.joints.items()}
                if job is None:
                    continue
                self.job = job
                if job[0] == "HOME":
                    self.do_home()
                    self.last_result = "homed"
                elif job[0] == "PICK":
                    self.last_result = self.do_pick(*job[1:])
                elif job[0] == "JOG":
                    self.do_jog(*job[1:])
                elif job[0] == "GOTO":
                    self.do_goto(*job[1:])
                elif job[0] == "CALIBRATE":
                    self.do_calibrate()
                    self.last_result = f"calibrated: {self.taught['travel']}"
                elif job[0] == "REINIT":
                    self.state = "STARTING"
                    if len(self.joints) < len(self.cfg["joints"]):
                        self.open_motors()          # setup failed earlier (no power?)
                    else:
                        for j in self.joints.values():
                            self.prepare_motor(j)
                            j.reset_tracker()
                    if self.cfg.get("auto_home"):
                        self.do_home()
                self.state, self.step = ("IDLE" if self.homed else "UNHOMED"), ""
            except Fault as e:
                self.hold_all()
                self.set_fault(str(e))
            except Rejected as e:
                self.last_result = f"rejected: {e}"
                self.state, self.step = ("IDLE" if self.homed else "UNHOMED"), ""
            except (ServoError, OSError) as e:
                self.hold_all()
                self.set_fault(f"motor comms: {e}")
            finally:
                self.carrying = False
                self.job = None

    def set_fault(self, reason):
        if self.fault is None:
            self.fault = reason
        self.abort.set()
        self.state = "FAULT"
        self.last_result = f"fault: {self.fault}"
        print(f"motion: FAULT: {self.fault}", flush=True)

    # ----------------------------------------------------------- commands
    def busy(self):
        return self.state not in ("IDLE", "UNHOMED", "FAULT")

    def command(self, msg):
        cmd = str(msg.get("cmd", "")).upper()
        if cmd == "STATUS":
            return None
        if cmd in ("FAULT", "STOP"):
            self.set_fault(msg.get("reason") or ("operator stop" if cmd == "STOP" else "fault"))
            return None
        if cmd == "PAUSE":
            self.paused.set()
            return None
        if cmd == "RESUME":
            self.paused.clear()
            return None
        if cmd == "RESET":
            if self.job is not None:
                return "still stopping, try again"
            self.fault, self.step = None, ""
            self.abort.clear()
            if msg.get("rehome"):
                # After an e-stop the drivers lost power: their encoders restarted,
                # so our zero is gone. Re-init the drivers and home again.
                self.homed = False
                self.state = "QUEUED"
                self.jobs.put(("REINIT",))
            else:
                self.state = "IDLE" if self.homed else "UNHOMED"
            return None
        if self.state == "FAULT":
            return f"in FAULT ({self.fault}): send RESET first"
        if self.busy() or self.job is not None:
            return f"busy ({self.state})"
        if cmd == "HOME":
            self.jobs.put(("HOME",))
        elif cmd == "PICK":
            src, dst, label = str(msg.get("from")), str(msg.get("to")), msg.get("label")
            if not self.homed:
                return "not homed"
            if src not in self.cfg["pockets"] or dst not in self.cfg["pockets"]:
                return f"unknown pocket (have {sorted(self.cfg['pockets'])})"
            if src == dst:
                return "from and to are the same pocket"
            if label not in self.profiles:
                return f"no grip profile for {label!r}"
            self.jobs.put(("PICK", src, dst, label))
        elif cmd == "JOG":
            name = msg.get("joint")
            if name not in self.cfg["joints"]:
                return f"unknown joint {name!r}"
            amount = float(msg.get("amount", msg.get("deg", 0)))
            if not self.homed and abs(amount) > self.cfg["unhomed_jog_max"]:
                return f"not homed: jog at most {self.cfg['unhomed_jog_max']} at a time"
            self.jobs.put(("JOG", name, amount))
        elif cmd == "CALIBRATE":
            if not self.homed:
                return "home first"
            self.jobs.put(("CALIBRATE",))
        elif cmd == "GOTO":
            where = str(msg.get("pocket"))
            if not self.homed:
                return "home first"
            if where != "home" and where not in self.cfg["pockets"]:
                return f"unknown pocket (have {sorted(self.cfg['pockets'])})"
            self.jobs.put(("GOTO", where, bool(msg.get("high"))))
        elif cmd == "TEACH":
            pocket = str(msg.get("pocket"))
            if not self.homed:
                return "home first"
            self.cfg["pockets"][pocket] = dict(self.joints_now)
            self.taught.setdefault("pockets", {})[pocket] = dict(self.joints_now)
            self.save_taught()
        else:
            return f"unknown cmd {cmd!r}"
        self.state = "QUEUED" if cmd != "TEACH" else self.state
        return None

    def status(self, timer):
        return {"t": time.time(), "state": self.state, "step": self.step,
                "busy": self.busy() or self.job is not None, "homed": self.homed,
                "fault": self.fault, "paused": self.paused.is_set(),
                "joints": self.joints_now, "job": self.job and list(self.job),
                "limits": {n: [round(j.lo, 1), round(j.hi, 1)] for n, j in self.joints.items()},
                "picks_done": self.picks_done, "last_result": self.last_result,
                "sim": self.sim, "timing": timer.stats()}


def main():
    ap = argparse.ArgumentParser(description="pick-and-place motion task")
    ap.add_argument("--sim", type=float, nargs="?", const=1.0, default=0.0, metavar="SPEEDUP",
                    help="fake motors (sim_servo.py); optional speed-up factor, e.g. --sim 4")
    args = ap.parse_args()
    cfg = load_json("arm.json")
    if args.sim:
        cfg["deg_per_s_per_speed"] *= args.sim     # the fake motors run that much faster
    mo = Motion(cfg, args.sim)
    threading.Thread(target=mo.worker, daemon=True).start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", cfg["cmd_port"]))
    sock.setblocking(False)
    tel = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    timer = LoopTimer(cfg["loop_hz"])
    every = max(1, cfg["loop_hz"] // cfg["telemetry_hz"])
    n = 0
    print(f"motion: {'SIM' if args.sim else 'real'} motors, cmd udp {cfg['cmd_port']}, "
          f"telemetry udp {cfg['telemetry_port']}, pid {os.getpid()}", flush=True)
    while True:
        timer.wait()
        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except BlockingIOError:
                break
            try:
                err = mo.command(json.loads(data))
            except (ValueError, TypeError) as e:
                err = f"bad command: {e}"
            reply = mo.status(timer)
            reply["ok"], reply["error"] = err is None, err
            sock.sendto(json.dumps(reply).encode(), addr)
        n += 1
        if n % every == 0:
            try:
                tel.sendto(json.dumps(mo.status(timer)).encode(),
                           ("127.0.0.1", cfg["telemetry_port"]))
            except OSError:
                pass
        if timer.win_n >= cfg["loop_hz"]:
            timer.roll()


if __name__ == "__main__":
    main()
