"""
motion: owns both SERVO42C ports and runs pick-and-place.

    on -p 30 python3 motion.py          real motors (/dev/ser3, /dev/ser5)
    python3 motion.py --sim             fake motors (sim_servo.py), no hardware

Pick sequence (one command from vision does all of it):
    IDLE -> MOVE_TO_PICK -> LOWER -> GRIP -> LIFT -> MOVE_TO_PLACE -> LOWER
         -> RELEASE -> HOME -> IDLE          and FAULT from anywhere.

Safety rules, each one sentence:
  - Pocket positions are fixed, taught joint angles (config/arm.json); no IK.
  - Every target is checked against the joint's soft limits before moving.
  - Targets are absolute, so errors never add up from move to move.
  - Both joints move together: speeds are scaled so they arrive together.
  - Every move has a time limit, and if a joint stops making progress we stop
    (motor 2's V1.0 firmware has no stall detection of its own).
  - Any fault = stop and HOLD (motors stay enabled, gripper keeps its grip).
  - PAUSE (sent by the supervisor when vision is down) stops and holds, and
    RESUME continues the same move from where the arm is.
  - If the object slips while carrying it, we stop and hold (FAULT).

Commands: one JSON object per UDP packet to 127.0.0.1:<cmd_port>; the reply
is the status. See arm_cmd.py.
  PICK {from, to, label}  HOME  JOG {joint, deg}  TEACH {pocket}
  PAUSE  RESUME  FAULT {reason}  STOP  RESET  STATUS
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
from servo_test import AngleTracker, run_until_blocked


class Fault(Exception):
    """Something went wrong: stop, hold, report."""


class Rejected(Exception):
    """A command we refuse without moving (bad pocket, out of limits...)."""


class Joint:
    """One arm joint = one SERVO42C, in arm degrees."""

    def __init__(self, name, cfg, motor):
        self.name, self.cfg, self.m = name, cfg, motor
        self.ratio = cfg["gear_ratio"]
        self.zero = 0.0                   # motor degrees where the joint is at 0
        self.tracker = None if motor.has_checksum else AngleTracker(motor)

    def motor_deg(self):
        """Multi-turn motor position. V1.0's encoder wraps, so we unwrap it."""
        if self.tracker is None:
            return self.m.encoder_degrees()
        self.tracker.update()
        return self.tracker.total

    def deg(self):
        return (self.motor_deg() - self.zero) / self.ratio

    def check_limits(self, target):
        if not self.cfg["min_deg"] <= target <= self.cfg["max_deg"]:
            raise Rejected(f"{self.name} {target:.1f} deg is outside its limits "
                           f"[{self.cfg['min_deg']}, {self.cfg['max_deg']}]")

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
        self.grip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.grip_sock.settimeout(0.3)

    # ---------------------------------------------------------------- setup
    def open_motors(self):
        for name, jc in self.cfg["joints"].items():
            if self.sim:
                from sim_servo import FakeServo
                # The fake lift has a hard stop at motor 0 deg and starts above it.
                m = FakeServo(jc["port"], name=name, firmware=jc["firmware"],
                              hard_min=0.0 if name == "lift" else None,
                              start_deg=60.0 if name == "lift" else 0.0,
                              speedup=self.sim)
            else:
                m = Servo42C(jc["port"], addr=jc["addr"], name=name, firmware=jc["firmware"])
            m.init()            # Surya's init: accel, microsteps, stall protection
            m.enable(True)      # init ends released; an arm must hold
            self.joints[name] = Joint(name, jc, m)

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

    # ------------------------------------------------------------- moving
    def move_to(self, targets, step):
        """Coordinated absolute move of one or both joints, in arm degrees."""
        self.step = step
        if self.homed:
            for name, t in targets.items():
                self.joints[name].check_limits(t)
        c = self.cfg
        tries = 0                           # 1 move + up to 2 small corrections
        while tries < 3:
            self.checkpoint()
            todo = {}
            for name, t in targets.items():
                j = self.joints[name]
                d = (t - j.deg()) * j.ratio         # motor degrees to go
                if abs(d) / j.ratio > c["tolerance_deg"] * 0.5:
                    todo[name] = d
            if not todo:
                return
            if self._run_move(todo):        # False = paused part-way: re-plan, same try
                tries += 1
        for name, t in targets.items():
            err = abs(self.joints[name].deg() - t)
            if err > c["tolerance_deg"]:
                raise Fault(f"{name} missed its target by {err:.1f} deg")

    def _run_move(self, todo):
        c = self.cfg
        k = c["deg_per_s_per_speed"]
        # Same arrival time for all joints: the slowest one sets the time.
        t_move = max(abs(d) / (self.joints[n].cfg["max_speed"] * k) for n, d in todo.items())
        active = {}
        for name, d in todo.items():
            j = self.joints[name]
            speed = max(c["min_speed"], min(j.cfg["max_speed"], round(abs(d) / (t_move * k))))
            start = j.motor_deg()
            if j.m.has_checksum:      # V1.1: exact pulse move, the driver stops itself
                done0 = j.m.moves_completed
                j.m.move(j.direction(d), speed, int(abs(d) / 360.0 * j.m.PULSES_PER_REV))
            else:                     # V1.0: run, we stop it on the encoder
                done0 = None
                j.m.run(j.direction(d), speed)
            active[name] = {"d": d, "start": start, "done0": done0, "last": start,
                            "speed": speed}
        deadline = time.monotonic() + t_move * c["timeout_factor"] + c["timeout_margin_s"]
        next_progress = time.monotonic() + c["progress_check_s"]
        next_stall = next_slip = time.monotonic() + 0.5
        try:
            while active:
                time.sleep(0.02)
                self.checkpoint()
                if self.paused.is_set():
                    self.hold_all()
                    self.state_before_pause, self.state = self.state, "PAUSED"
                    while self.paused.is_set():
                        self.checkpoint()
                        time.sleep(0.05)
                    self.state = self.state_before_pause
                    return False
                now = time.monotonic()
                self.joints_now = {n: round(j.deg(), 2) for n, j in self.joints.items()}
                for name in list(active):
                    j, a = self.joints[name], active[name]
                    pos = j.motor_deg()
                    moved = (pos - a["start"]) * (1 if a["d"] > 0 else -1)
                    if a["done0"] is None:
                        if moved >= abs(a["d"]) - c["v10_stop_lead_motor_deg"]:
                            j.m.stop()
                            del active[name]
                    elif j.m.moves_completed > a["done0"] or moved >= abs(a["d"]) - 0.2:
                        del active[name]
                if now > next_progress:
                    for name, a in active.items():
                        pos = self.joints[name].motor_deg()
                        if abs(pos - a["last"]) < c["min_progress_motor_deg"]:
                            raise Fault(f"{name} is not moving (jammed or stalled)")
                        a["last"] = pos
                    next_progress = now + c["progress_check_s"]
                if now > next_stall:
                    for name in active:
                        if self.joints[name].m.has_checksum and self.joints[name].m.is_stalled():
                            raise Fault(f"{name} driver reports a stall")
                    next_stall = now + 0.5
                if self.carrying and now > next_slip:
                    r = self.gripper({"cmd": "STATUS"})
                    if r.get("slip") or r["state"] not in ("GRIPPED", "HOLD"):
                        raise Fault(f"object slipped or grip lost ({r['state']})")
                    next_slip = now + 0.1
                if now > deadline:
                    raise Fault(f"move timed out ({', '.join(active)})")
            return True
        except BaseException:
            self.hold_all()
            raise

    # ------------------------------------------------------------ the jobs
    def do_home(self):
        self.state = "HOMING"
        h = self.cfg["homing"]
        for name, j in self.joints.items():
            mode = h.get(name, "marked_zero")
            if mode == "hard_stop":
                self.step = f"{name}: seeking hard stop"
                run_until_blocked(j.m, j.cfg["dir_bit_positive"] ^ 1, h["seek_speed"],
                                  h["seek_error_deg"], h["seek_max_motor_deg"])
                j.zero = j.motor_deg() - h["lift_stop_deg"] * j.ratio
            else:
                j.zero = j.motor_deg() - h["marked_pose"][name] * j.ratio
        self.homed = True
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

    def do_jog(self, name, deg):
        self.state = "JOG"
        j = self.joints[name]
        self.move_to({name: j.deg() + deg}, f"jog {name} {deg:+.1f}")

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
                elif job[0] == "REINIT":
                    self.state = "STARTING"
                    for j in self.joints.values():
                        j.m.init()
                        j.m.enable(True)
                        j.tracker = None if j.m.has_checksum else AngleTracker(j.m)
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
            self.jobs.put(("JOG", name, float(msg.get("deg", 0))))
        elif cmd == "TEACH":
            pocket = str(msg.get("pocket"))
            if not self.homed:
                return "home first"
            self.cfg["pockets"][pocket] = dict(self.joints_now)
            self.save_pockets()
        else:
            return f"unknown cmd {cmd!r}"
        self.state = "QUEUED" if cmd != "TEACH" else self.state
        return None

    def save_pockets(self):
        path = os.path.join(HERE, "config", "arm.json")
        with open(path) as f:
            full = json.load(f)
        full["pockets"] = self.cfg["pockets"]
        with open(path + ".tmp", "w") as f:
            json.dump(full, f, indent=2)
        os.replace(path + ".tmp", path)

    def status(self, timer):
        return {"t": time.time(), "state": self.state, "step": self.step,
                "busy": self.busy() or self.job is not None, "homed": self.homed,
                "fault": self.fault, "paused": self.paused.is_set(),
                "joints": self.joints_now, "job": self.job and list(self.job),
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
