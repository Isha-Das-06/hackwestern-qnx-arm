"""
supervisor: starts gripper_link, motion and vision, and watches them.

    on -p 40 python3 supervisor.py          real robot   (or ./start_robot.sh)
    python3 supervisor.py --sim             fake Pico, fake motors, fake vision
Dashboard: http://<pi>:8090

The rules (each one sentence, for the judges):
  1. E-stop pressed (or its wire broken) -> FAULT. Hardware has already cut
     motor power; software just notices and refuses to move until RESET.
  2. gripper_link or motion dies or goes silent -> FAULT: stop and hold.
     If motion is the one that died, we send the stop to the drivers ourselves.
  3. The Pico link goes stale -> FAULT (the Pico has frozen the servo itself).
  4. Vision dies or goes silent -> PAUSE motion (hold), restart vision, and
     RESUME when its heartbeat is back. Vision crashing is never a fault.
  5. A FAULT is sticky: only the RESET button (or `arm_cmd.py reset`) clears it.
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gripper_link import HERE, LoopTimer, load_json


def udp_request(port, msg, timeout=0.3):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(json.dumps(msg).encode(), ("127.0.0.1", port))
        return json.loads(s.recv(8192))
    except (OSError, ValueError):
        return None
    finally:
        s.close()


def udp_send(port, msg):
    """Fire and forget: the supervisor loop must never wait on a dead process."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(json.dumps(msg).encode(), ("127.0.0.1", port))
    except OSError:
        pass
    finally:
        s.close()


class Proc:
    """One child process plus its heartbeat."""

    def __init__(self, name, cfg, cmd, port):
        self.name, self.cfg, self.cmd = name, cfg, cmd
        self.p = None
        self.restarts = 0
        self.last_msg = None
        self.last_t = None
        self.started_t = 0.0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.sock.setblocking(False)
        os.makedirs("/tmp/robot", exist_ok=True)
        self.log = f"/tmp/robot/{name}.log"

    def start(self):
        with open(self.log, "a") as log:
            log.write(f"\n--- supervisor start {time.ctime()} ---\n")
            self.p = subprocess.Popen(self.cmd, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL)
        self.started_t = time.monotonic()
        self.last_t = None

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def kill(self):
        if self.alive():
            self.p.kill()
            self.p.wait(timeout=2)

    def poll_heartbeat(self):
        while True:
            try:
                data = self.sock.recv(16384)
            except BlockingIOError:
                return
            try:
                self.last_msg = json.loads(data)
                self.last_t = time.monotonic()
            except ValueError:
                pass

    def silent_ms(self, now):
        ref = self.last_t if self.last_t is not None else self.started_t
        return (now - ref) * 1000

    def silent(self, now, limit_ms):
        """No heartbeat for limit_ms. A just-started process gets 3 s to boot."""
        if self.last_t is None and now - self.started_t < 3.0:
            return False
        return self.silent_ms(now) > limit_ms

    def info(self, now):
        return {"pid": self.p.pid if self.p else None, "alive": self.alive(),
                "restarts": self.restarts, "silent_ms": round(self.silent_ms(now)),
                "log": self.log}


class Supervisor:
    def __init__(self, cfg, sim):
        self.cfg, self.sim = cfg, sim
        self.arm = load_json("arm.json")
        self.grip_cfg = load_json("gripper.json")
        self.fault = None            # sticky reason string
        self.events = []             # recent events for the dashboard
        self.vision_down = False
        self.estop = False
        self.lock = threading.Lock()
        self.fake_pico = None
        ports = {"gripper": self.grip_cfg["telemetry_port"],
                 "motion": self.arm["telemetry_port"], "vision": cfg["vision_port"]}
        subs = {}
        if sim:
            self.fake_pico = subprocess.Popen([sys.executable, "fake_pico.py"], cwd=HERE,
                                              stdout=open("/tmp/robot_fake_pico.log", "w"),
                                              stderr=subprocess.STDOUT)
            for _ in range(50):
                if os.path.exists("/tmp/fake_pico_port") and \
                        os.path.getmtime("/tmp/fake_pico_port") > time.time() - 10:
                    break
                time.sleep(0.1)
            subs["{fake_pico_port}"] = open("/tmp/fake_pico_port").read().strip()
            with open(cfg["estop_sim_path"], "w") as f:
                f.write("0")
        self.procs = {}
        for name, pc in cfg["procs"].items():
            cmd = [subs.get(a, a) for a in (pc["sim"] if sim else pc["cmd"])]
            self.procs[name] = Proc(name, pc, cmd, ports[name])
        self.estop_path = cfg["estop_sim_path"] if sim else cfg["estop_path"]
        if not sim:
            try:                     # make sure the pin is an input
                with open(self.estop_path, "w") as f:
                    f.write("in")
            except OSError:
                pass

    # --------------------------------------------------------------- events
    def event(self, text):
        line = f"{time.strftime('%H:%M:%S')} {text}"
        print(f"supervisor: {line}", flush=True)
        with self.lock:
            self.events = ([line] + self.events)[:30]

    def raise_fault(self, reason):
        """Stop and hold everything. Sticky until RESET."""
        if self.fault is None:       # first problem: tell everyone once
            self.fault = reason
            self.event(f"FAULT: {reason}")
            udp_send(self.arm["cmd_port"], {"cmd": "FAULT", "reason": reason})
            udp_send(self.grip_cfg["cmd_port"], {"cmd": "HOLD"})
        if not self.procs["motion"].alive():
            self.hold_motors_directly()

    def hold_motors_directly(self):
        """motion is dead, so nobody owns the motor ports: send STOP ourselves."""
        if getattr(self, "_held_directly", False):
            return
        self._held_directly = True
        if self.sim:
            self.event("motion dead: (sim) would send STOP to both drivers")
            return
        from mks_servo import Servo42C
        for name, jc in self.arm["joints"].items():
            try:
                m = Servo42C(jc["port"], addr=jc["addr"], name=name, firmware=jc["firmware"])
                m.safe_stop()         # stop, stay enabled = holding
                m.close()
                self.event(f"sent STOP to {name} driver directly")
            except OSError as e:
                self.event(f"could not reach {name} driver: {e}")

    def read_estop(self):
        try:
            with open(self.estop_path) as f:
                return f.read(4).strip() != "0"     # anything but 0 = pressed
        except OSError:
            return True                             # can't read it: fail safe

    # ---------------------------------------------------------------- loop
    def check(self, now):
        for p in self.procs.values():
            p.poll_heartbeat()
        g, m, v = self.procs["gripper"], self.procs["motion"], self.procs["vision"]

        # 1. e-stop
        pressed = self.read_estop()
        if pressed and not self.estop:
            self.event("E-STOP pressed")
            self.raise_fault("E-STOP pressed")
        elif not pressed and self.estop:
            self.event("E-STOP released (press RESET to continue)")
        self.estop = pressed

        # 2. gripper_link / motion dead or silent
        for p in (g, m):
            if not p.alive():
                self.raise_fault(f"{p.name} exited (code {p.p.returncode})")
            elif p.silent(now, p.cfg["heartbeat_ms"]):
                self.raise_fault(f"{p.name} silent for {p.silent_ms(now):.0f} ms")

        # 3. Pico link
        gs = g.last_msg or {}
        if gs.get("state") == "STALE":
            self.raise_fault("Pico link stale (servo frozen by the Pico)")

        # 4. vision: pause, restart, resume
        vc = v.cfg
        # "Back" only once the new vision has really sent a heartbeat.
        down = not v.alive() or v.last_t is None or v.silent_ms(now) > vc["heartbeat_ms"]
        if down and not self.vision_down:
            self.event("vision down: PAUSE motion (holding)")
            udp_send(self.arm["cmd_port"], {"cmd": "PAUSE"})
        if not down and self.vision_down:
            self.event("vision back: RESUME motion")
            udp_send(self.arm["cmd_port"], {"cmd": "RESUME"})
        self.vision_down = down
        if not v.alive() or v.silent(now, vc["restart_after_silent_s"] * 1000):
            if now - v.started_t > 1.0:      # don't restart-loop faster than 1 Hz
                v.kill()
                v.restarts += 1
                self.event(f"restarting vision (#{v.restarts})")
                v.start()

    def reset(self):
        """Dashboard RESET: restart any dead process, then clear the fault."""
        if self.read_estop():
            return "e-stop is still pressed"
        restarted = []
        for p in (self.procs["gripper"], self.procs["motion"]):   # vision restarts itself
            if not p.alive():
                p.restarts += 1
                self.event(f"restarting {p.name}")
                p.start()
                restarted.append(p.name)
        if restarted:
            time.sleep(1.5)
        was_estop = self.fault is not None and "E-STOP" in self.fault
        self.fault = None
        self._held_directly = False
        if "motion" in restarted:        # a fresh motion has no fault; it homes itself
            self.event("RESET (motion restarted: it re-homes; park the base on its mark)")
            return None
        r = udp_request(self.arm["cmd_port"], {"cmd": "RESET", "rehome": was_estop})
        self.event("RESET" + (" (re-homing after e-stop)" if was_estop else ""))
        return None if r and r.get("ok") else f"motion: {r and r.get('error')}"

    def state(self, timer):
        now = time.monotonic()
        with self.lock:
            events = list(self.events)
        return {"t": time.time(), "fault": self.fault, "estop": self.estop,
                "vision_down": self.vision_down, "sim": self.sim, "events": events,
                "timing": timer.stats(),
                "procs": {n: p.info(now) for n, p in self.procs.items()},
                "gripper": self.procs["gripper"].last_msg,
                "motion": self.procs["motion"].last_msg,
                "vision": self.procs["vision"].last_msg,
                "profiles": load_json("grip_profiles.json")}

    def shutdown(self):
        udp_request(self.arm["cmd_port"], {"cmd": "STOP", "reason": "supervisor shutting down"})
        for p in self.procs.values():
            p.kill()
        if self.fake_pico:
            self.fake_pico.kill()


def make_web(sup, timer):
    page = os.path.join(HERE, "web", "dashboard.html")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/state":
                self.send(200, json.dumps(sup.state(timer)).encode())
            elif self.path in ("/", "/index.html"):
                with open(page, "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b"{}")

        def do_POST(self):
            act = self.path.strip("/")
            err = None
            if act == "reset":
                err = sup.reset()
            elif act == "stop":
                sup.raise_fault("STOP button")
            elif act == "home":
                r = udp_request(sup.arm["cmd_port"], {"cmd": "HOME"})
                err = None if r and r.get("ok") else (r and r.get("error")) or "no reply"
            elif act == "open":
                r = udp_request(sup.grip_cfg["cmd_port"], {"cmd": "OPEN"})
                err = None if r and r.get("ok") else (r and r.get("error")) or "no reply"
            else:
                err = "unknown action"
            self.send(200, json.dumps({"ok": err is None, "error": err}).encode())

    srv = ThreadingHTTPServer(("0.0.0.0", sup.cfg["web_port"]), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def main():
    ap = argparse.ArgumentParser(description="robot supervisor")
    ap.add_argument("--sim", action="store_true", help="fake Pico, motors and vision")
    args = ap.parse_args()
    cfg = load_json("supervisor.json")
    sup = Supervisor(cfg, args.sim)
    for name in ("gripper", "motion", "vision"):
        sup.procs[name].start()
        sup.event(f"started {name}: {' '.join(sup.procs[name].cmd)}")
    time.sleep(1.5)                  # let them open ports before we judge heartbeats
    timer = LoopTimer(cfg["loop_hz"])
    make_web(sup, timer)
    sup.event(f"dashboard on :{cfg['web_port']}")
    def on_term(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, on_term)
    try:
        while True:
            timer.wait()
            sup.check(time.monotonic())
            if timer.win_n >= cfg["loop_hz"]:
                timer.roll()
    except KeyboardInterrupt:
        sup.event("shutting down (motors stay enabled and holding)")
        sup.shutdown()


if __name__ == "__main__":
    main()
