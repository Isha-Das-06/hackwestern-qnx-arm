"""
supervisor: starts gripper_link, motion and vision, watches them, and owns the
safety pins (e-stop, START button, actuator power, fault LED).

    on -p 40 python3 supervisor.py          real robot   (or ./start_robot.sh)
    python3 supervisor.py --sim             fake Pico, fake motors, fake vision
Dashboard: http://<pi>:8090

The rules (each one sentence, for the judges):
  1. E-stop pressed (or its wire broken) -> actuator power off in the same
     10 ms cycle, FAULT, and power stays off until the button is released and
     RESET is pressed. The button's own contact also cuts power in hardware.
  2. Actuator power is held on by this process; if the supervisor dies, QNX's
     GPIO driver drops the line and power goes off.
  3. gripper_link or motion dies or goes silent -> FAULT: stop and hold.
     If motion is the one that died, we send the stop to the drivers ourselves.
  4. The Pico link goes stale -> FAULT (the Pico has frozen the servo itself).
  5. Vision dies or goes silent, or a hand is in view -> PAUSE motion (hold);
     RESUME once vision is back and no hand has been seen for hand_clear_s.
     Vision crashing is never a fault; it is restarted.
  6. Pointing only selects anything inside the window the START button opens.
  7. A FAULT is sticky: only the RESET button (or `arm_cmd.py reset`) clears it.
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


class SafetyIO:
    """The safety pins. Real GPIO on the Pi; plain files in /tmp with --sim.

      power  GPIO18 (pin 12) actuator power enable (motor 12 V + servo MOSFETs),
             held high by a 100% PWM from this process: if the process dies,
             even by kill -9, QNX's GPIO driver stops the PWM and power drops.
      led    GPIO27 (pin 13) fault LED: on = FAULT, blinking = paused.
      estop  GPIO17 (pin 11) NC contact to GND: 0 = OK, 1 = pressed or wire
             broken. Unreadable counts as pressed.
      start  GPIO23 (pin 16) START button to GND: 0 = pressed.
    Pull-ups and the boot-time "off" state are set by uart_setup.sh.
    """

    def __init__(self, cfg, sim):
        self.sim = sim
        self.power_on = self.led_on = None
        io = cfg["io"]
        if sim:
            self.estop_path, self.start_path = cfg["estop_sim_path"], cfg["start_sim_path"]
            for path, idle in ((self.estop_path, "0"), (self.start_path, "1")):
                with open(path, "w") as f:
                    f.write(idle)
        else:
            import rpi_gpio as G
            G.setmode(G.BCM)
            G.setup(io["power_pin"], G.OUT)
            self.pwm = G.PWM(io["power_pin"], 1000, mode=G.PWM.MODE_MS)
            self.pwm.start(0.0)
            self.estop_path = f"/dev/gpio/{io['estop_pin']}"
            self.start_path = f"/dev/gpio/{io['start_pin']}"
            self.led_path = f"/dev/gpio/{io['led_pin']}"
            for path, mode in ((self.estop_path, "in"), (self.start_path, "in"),
                               (self.led_path, "out")):
                self._write(path, mode)
        self.set_power(False)
        self.set_led(False)

    @staticmethod
    def _write(path, text):
        try:
            with open(path, "w") as f:
                f.write(text)
        except OSError:
            pass

    @staticmethod
    def _read(path):
        try:
            with open(path) as f:
                return f.read(4).strip()
        except OSError:
            return None

    def estop_pressed(self):
        return self._read(self.estop_path) != "0"

    def start_pressed(self):
        return self._read(self.start_path) == "0"

    def set_power(self, on):
        if on == self.power_on:
            return
        self.power_on = on
        if self.sim:
            self._write("/tmp/fake_power", "1" if on else "0")
        else:
            self.pwm.ChangeDutyCycle(100.0 if on else 0.0)

    def set_led(self, on):
        if on == self.led_on:
            return
        self.led_on = on
        if not self.sim:
            self._write(self.led_path, "on" if on else "off")


class Proc:
    """One child process plus its heartbeat."""

    def __init__(self, name, cfg, cmd, port):
        self.name, self.cfg, self.cmd = name, cfg, cmd
        self.p = None
        self.restarts = 0
        self.last_msg = None
        self.last_t = None
        self.addr = None             # where its heartbeats come from (to talk back)
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
                data, addr = self.sock.recvfrom(16384)
            except BlockingIOError:
                return
            try:
                self.last_msg = json.loads(data)
                self.last_t, self.addr = time.monotonic(), addr
            except ValueError:
                pass

    def send_back(self, msg):
        if self.addr:
            try:
                self.sock.sendto(json.dumps(msg).encode(), self.addr)
            except OSError:
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
    def __init__(self, cfg, sim, real_vision=False):
        self.cfg, self.sim = cfg, sim
        self.arm = load_json("arm.json")
        self.grip_cfg = load_json("gripper.json")
        self.fault = None            # sticky reason string
        self.events = []             # recent events for the dashboard
        self.vision_down = False
        self.estop = False
        self.pause_reasons = []      # why motion is paused right now
        self.hand_t = -1e9           # last time vision saw a hand
        self.hands = 0
        self.select_until = 0.0      # START window (monotonic time)
        self.next_select_push = 0.0
        self.start_reads = 0
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
        self.io = SafetyIO(cfg, sim)
        self.procs = {}
        for name, pc in cfg["procs"].items():
            use_sim = sim and not (name == "vision" and real_vision)
            cmd = [subs.get(a, a) for a in (pc["sim"] if use_sim else pc["cmd"])]
            self.procs[name] = Proc(name, pc, cmd, ports[name])

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
        m = self.procs["motion"]
        if m.p is not None and not m.alive():
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

    def power_up(self):
        """Actuator power on (only with the e-stop released), then give the
        SERVO42C drivers time to boot before anyone talks to them."""
        if self.io.estop_pressed():
            self.estop = True
            self.raise_fault("E-STOP pressed")
            return False
        if not self.io.power_on:
            self.io.set_power(True)
            self.event("actuator power ON")
            time.sleep(self.cfg["power_on_delay_s"])
        return True

    def open_select(self, source):
        """START: pointing may select a move for select_window_s."""
        if self.fault:
            self.event(f"START ({source}) ignored: FAULT")
            return "in FAULT: press RESET first"
        self.select_until = time.monotonic() + self.cfg["select_window_s"]
        self.next_select_push = 0.0
        self.event(f"START ({source}): pointing armed for {self.cfg['select_window_s']} s")
        return None

    # ---------------------------------------------------------------- loop
    def check(self, now):
        for p in self.procs.values():
            p.poll_heartbeat()
        g, m, v = self.procs["gripper"], self.procs["motion"], self.procs["vision"]

        # 1. e-stop: power off in this same cycle, then latch a FAULT.
        pressed = self.io.estop_pressed()
        if pressed:
            self.io.set_power(False)
        if pressed and not self.estop:
            self.event("E-STOP pressed: actuator power OFF")
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

        # 4. vision down or a hand in view: pause; resume once both are clear.
        vc = v.cfg
        # "Back" only once the new vision has really sent a heartbeat.
        down = not v.alive() or v.last_t is None or v.silent_ms(now) > vc["heartbeat_ms"]
        self.hands = 0 if down else int((v.last_msg or {}).get("hands", 0))
        if self.hands:
            self.hand_t = now
        hand = now - self.hand_t < self.cfg["hand_clear_s"]
        reasons = [r for r, on in (("vision down", down), ("hand in view", hand)) if on]
        if reasons and not self.pause_reasons:
            self.event(f"PAUSE motion ({', '.join(reasons)}): holding")
            udp_send(self.arm["cmd_port"], {"cmd": "PAUSE"})
        elif not reasons and self.pause_reasons:
            self.event("clear: RESUME motion")
            udp_send(self.arm["cmd_port"], {"cmd": "RESUME"})
        self.pause_reasons, self.vision_down = reasons, down
        if not v.alive() or v.silent(now, vc["restart_after_silent_s"] * 1000):
            if v.alive():
                v.kill()
                v.died_t = now
            v.died_t = getattr(v, "died_t", None) or now
            # Wait a moment before restarting: the USB camera needs time to let go,
            # and it never restart-loops faster than restart_delay_s.
            if now - v.died_t >= vc.get("restart_delay_s", 2.0) and now - v.started_t > 1.0:
                v.died_t = None
                v.restarts += 1
                self.event(f"restarting vision (#{v.restarts})")
                v.start()

        # 5. START button (2 reads in a row = pressed) opens the pointing window;
        #    vision hears how long is left, 5 times a second.
        if self.io.start_pressed():
            self.start_reads += 1
            if self.start_reads == 2:
                self.open_select("button")
        else:
            self.start_reads = 0
        if self.fault:
            self.select_until = 0.0
        if now >= self.next_select_push:
            self.next_select_push = now + 0.2
            v.send_back({"select_s": round(max(0.0, self.select_until - now), 1)})

        # 6. Fault LED: on = FAULT, blinking = paused, off = running normally.
        self.io.set_led(bool(self.fault) or (bool(self.pause_reasons) and int(now * 2) % 2 == 0))

    def reset(self):
        """Dashboard RESET: restart any dead process, power back up after an
        e-stop, then clear the fault."""
        if self.io.estop_pressed():
            return "e-stop is still pressed"
        restarted = []
        for p in (self.procs["gripper"], self.procs["motion"]):   # vision restarts itself
            if not p.alive():
                p.restarts += 1
                self.event(f"restarting {p.name}")
                p.start()
                restarted.append(p.name)
        was_estop = self.fault is not None and "E-STOP" in self.fault
        self.power_up()
        if restarted:
            time.sleep(1.5)
        self.fault = None
        self._held_directly = False
        if "motion" in restarted:        # a fresh motion has no fault
            self.event("RESET (motion restarted: home it again)")
            return None
        r = udp_request(self.arm["cmd_port"], {"cmd": "RESET", "rehome": was_estop})
        self.event("RESET" + (" (drivers re-initialised after e-stop)" if was_estop else ""))
        return None if r and r.get("ok") else f"motion: {r and r.get('error')}"

    def state(self, timer):
        now = time.monotonic()
        with self.lock:
            events = list(self.events)
        return {"t": time.time(), "fault": self.fault, "estop": self.estop,
                "power": self.io.power_on, "paused": self.pause_reasons,
                "hands": self.hands, "select_s": round(max(0.0, self.select_until - now), 1),
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
            elif act == "start":
                err = sup.open_select("dashboard")
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
    ap.add_argument("--real-vision", action="store_true",
                    help="with --sim: use the real camera app (rehearse before the arm is built)")
    args = ap.parse_args()
    cfg = load_json("supervisor.json")
    sup = Supervisor(cfg, args.sim, args.real_vision)
    # Gripper first, then actuator power (drivers need ~2 s to boot), then the rest.
    for name in ("gripper", "motion", "vision"):
        if name == "motion":
            sup.power_up()
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
        sup.event("shutting down: motors stopped; actuator power goes off with this process")
        sup.shutdown()


if __name__ == "__main__":
    main()
