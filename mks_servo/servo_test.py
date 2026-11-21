#!/usr/bin/env python3
"""
Two MKS SERVO42C drivers on a Raspberry Pi 4 running QNX.

    motor 1: /dev/ser3  (UART3, GPIO4 TX / GPIO5 RX)
    motor 2: /dev/ser5  (UART5, GPIO12 TX / GPIO13 RX)

Run `sudo sh uart_setup.sh` once per boot first.

    python3 servo_test.py loopback     # Pi-side check, TX jumpered to RX, no drivers
    python3 servo_test.py status       # read encoder/pulses/error/stall from both
    python3 servo_test.py init         # sketch init: accel, microsteps, stall protection
    python3 servo_test.py move 1 40    # motor 1, 40 mm forward
    python3 servo_test.py move both -40 --speed 10
    python3 servo_test.py seek 1       # motor 1 forward until it meets resistance
    python3 servo_test.py seek both --reverse --error 6
    python3 servo_test.py run          # interactive continuous run (g/s/r/+/-/p/q)

Safety: Ctrl-C, SIGTERM, a stall, or a command that still has no valid
reply after retries stops and releases BOTH motors. 12 V must be on Vmot.
"""

import argparse
import math
import os
import select
import signal
import sys
import time

from mks_servo import Servo42C, ServoError

# port, address, firmware ("1.1" uses checksums; "1.0" doesn't)
MOTORS = {
    "1": ("/dev/ser3", 0xE0, "1.1"),
    "2": ("/dev/ser5", 0xE0, "1.0"),
}

RUN_SPEED = 15                 # 0-127, ~30 mm/s on the 12.7 mm wheel
MIN_SPEED = 5                  # below this the shaft often doesn't turn
DIR_FORWARD = 1                # 0 = CW, 1 = CCW
MM_PER_REV = 12.7 * math.pi
BIG_PULSE_COUNT = 4_720_000    # continuous run, re-sent every REISSUE_S
REISSUE_S = 8.0
STALL_POLL_S = 0.5
POLLED_MOVE_S = 0.02           # encoder poll for V1.0 fixed moves
SEEK_SPEED = 8                 # not MIN_SPEED: a shaft that fails to start reads as blocked
SEEK_ERROR_DEG = 10.0          # shaft this far behind = blocked; motor 1 lags up to ~5.3 deg turning freely at speed 8
SEEK_CONFIRM_POLLS = 3         # readings in a row, so a start-up jolt doesn't count
SEEK_BACKOFF_DEG = 2.0


def mm_to_pulses(mm):
    return int(abs(mm) / MM_PER_REV * Servo42C.PULSES_PER_REV)


def deg_to_pulses(deg):
    return int(abs(deg) / 360.0 * Servo42C.PULSES_PER_REV)


class AngleTracker:
    """Total degrees turned, from an encoder that wraps every revolution (V1.0).

    Polled fast enough that the shaft turns < 180 deg between reads.
    """

    def __init__(self, motor):
        self.motor = motor
        self.last = motor.encoder_degrees()
        self.total = 0.0

    def update(self):
        angle = self.motor.encoder_degrees()
        self.total += (angle - self.last + 180.0) % 360.0 - 180.0
        self.last = angle
        return abs(self.total)


def open_motors(which):
    names = ["1", "2"] if which == "both" else [which]
    return {n: Servo42C(*MOTORS[n][:2], name=f"motor{n}", firmware=MOTORS[n][2])
            for n in names}


def stop_all(motors):
    for m in motors.values():
        m.safe_stop()


def install_stop_handlers(motors):
    def handler(signum, frame):
        print("\nsignal received, stopping motors")
        stop_all(motors)
        sys.exit(1)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


# ----------------------------------------------------------------------
# Subcommands
# ----------------------------------------------------------------------

def cmd_loopback(args):
    """With TX jumpered to RX on each port, bytes written should come back."""
    ok = True
    for n, (port, _, _) in MOTORS.items():
        m = Servo42C(port, name=f"motor{n}")
        pattern = bytes(range(256))
        m._drain()
        os.write(m.fd, pattern)
        got = b""
        deadline = time.monotonic() + 1.0
        while len(got) < len(pattern) and time.monotonic() < deadline:
            got += m._read_available(deadline - time.monotonic())
        passed = got == pattern
        ok &= passed
        print(f"motor{n} {port}: {'PASS' if passed else 'FAIL'} ({len(got)}/256 bytes back)")
        m.close()
    return 0 if ok else 1


def print_status(name, m):
    try:
        print(f"motor{name}: encoder={m.encoder_degrees():.2f} deg  "
              f"pulses={m.pulses_received()}  "
              f"shaft_err={m.shaft_error_degrees():.3f} deg  "
              f"stalled={'YES' if m.is_stalled() else 'no'}  "
              f"moves_done={m.moves_completed}")
    except ServoError as e:
        print(e)


def cmd_status(args):
    motors = open_motors(args.motor)
    for n, m in motors.items():
        print_status(n, m)
    return 0


def cmd_init(args):
    motors = open_motors(args.motor)
    for n, m in motors.items():
        m.init()
        print(f"motor{n}: init OK")
    return 0


def cmd_move(args):
    motors = open_motors(args.motor)
    install_stop_handlers(motors)
    direction = DIR_FORWARD if args.mm >= 0 else DIR_FORWARD ^ 1
    pulses = mm_to_pulses(args.mm)
    target_deg = abs(args.mm) / MM_PER_REV * 360.0
    trackers, done = {}, set()
    try:
        for n, m in motors.items():
            if m.is_stalled():
                m.clear_stall()
            m.enable(True)
            if m.has_checksum:
                m.move(direction, args.speed, pulses)
            else:
                # V1.0 ignores 0xFD: run at constant speed and stop on the encoder.
                trackers[n] = AngleTracker(m)
                m.run(direction, args.speed)
            print(f"motor{n}: moving {args.mm} mm ({pulses} pulses) at speed {args.speed}")

        deadline = time.monotonic() + args.timeout
        last_stall_check = time.monotonic()
        while time.monotonic() < deadline:
            time.sleep(POLLED_MOVE_S)
            for n, m in motors.items():
                if n in done:
                    continue
                if n in trackers:
                    if trackers[n].update() >= target_deg:
                        m.stop()
                        done.add(n)
                elif m.moves_completed > 0:
                    done.add(n)
            if len(done) == len(motors):
                print("move complete")
                return 0
            if time.monotonic() - last_stall_check >= STALL_POLL_S:
                last_stall_check = time.monotonic()
                for n, m in motors.items():
                    if m.is_stalled():
                        raise ServoError(f"motor{n} stalled")
        raise ServoError("timed out waiting for move to complete")
    except ServoError as e:
        print(f"FAULT: {e}")
        stop_all(motors)
        return 1
    finally:
        for m in motors.values():
            m.safe_stop()


def start_turning(m, direction, speed, limit_deg):
    """V1.1 gets a 0xFD move of `limit_deg`, so it stops by itself if the Pi
    dies. V1.0 ignores 0xFD, so it runs at constant speed until stop()."""
    if m.has_checksum:
        m.move(direction, speed, deg_to_pulses(limit_deg))
    else:
        m.run(direction, speed)


def run_until_blocked(m, direction, speed=SEEK_SPEED, error_deg=SEEK_ERROR_DEG,
                      max_deg=360.0, backoff_deg=SEEK_BACKOFF_DEG, timeout=30.0):
    """Turn until something stops the shaft, then back off `backoff_deg`.

    Returns the degrees turned before contact, and leaves the motor enabled
    and holding. Raises ServoError, after stopping and releasing the motor,
    if it turns `max_deg` without meeting resistance or a command fails.

    Resistance shows up as shaft error (0x39): the driver's target keeps
    advancing while a blocked shaft doesn't, so the gap grows. Both firmware
    versions report it, unlike stall protection, which V1.0 doesn't have.

    V1.1's stall protection is off during the seek. It trips within about
    0.3 s of the shaft stopping, before the error check, and it releases the
    shaft; re-arming it after a trip was followed by a ~60 deg jump.
    """
    try:
        if m.is_stalled():
            m.clear_stall()
        if m.has_checksum:
            m.set_protection(False)
        m.enable(True)
        tracker = AngleTracker(m)
        # Driver-side limit, past max_deg so the software check below trips first.
        start_turning(m, direction, speed, max_deg * 1.2)
        over, peak = 0, 0.0
        deadline = time.monotonic() + timeout
        while True:
            time.sleep(POLLED_MOVE_S)
            turned = tracker.update()
            err = m.shaft_error_degrees()
            if abs(err) >= error_deg:
                over += 1
                if over >= SEEK_CONFIRM_POLLS:
                    break
            else:
                over = 0
                peak = max(peak, abs(err))
            if turned >= max_deg or time.monotonic() > deadline:
                raise ServoError(f"{m.name}: no resistance after {turned:.0f} deg "
                                 f"(largest shaft error {peak:.2f} deg)")
        m.stop()
        contact = tracker.total
        # The error's sign says which way the shaft was pushing, even if it
        # was already against the obstacle and hardly turned.
        toward = 1.0 if err >= 0 else -1.0

        if backoff_deg > 0:
            # The target is ahead of the blocked shaft, so it has to come back
            # through that gap before the shaft moves; hence the generous limit.
            start_turning(m, direction ^ 1, speed, backoff_deg + 45.0)
            deadline = time.monotonic() + 5.0
            while (contact - tracker.total) * toward < backoff_deg:
                if time.monotonic() > deadline:
                    raise ServoError(f"{m.name}: couldn't back off the obstacle")
                time.sleep(POLLED_MOVE_S)
                tracker.update()
            m.stop()
        return abs(contact)
    except BaseException:
        m.safe_stop()
        raise
    finally:
        if m.has_checksum:
            m.set_protection(True)


def cmd_seek(args):
    motors = open_motors(args.motor)
    install_stop_handlers(motors)
    direction = DIR_FORWARD ^ 1 if args.reverse else DIR_FORWARD
    try:
        for n, m in motors.items():
            print(f"motor{n}: turning until blocked (speed {args.speed}, "
                  f"error limit {args.error} deg)")
            turned = run_until_blocked(m, direction, args.speed, args.error,
                                       args.max_deg, timeout=args.timeout)
            print(f"motor{n}: blocked after {turned:.1f} deg, "
                  f"backed off {SEEK_BACKOFF_DEG} deg")
        return 0
    except ServoError as e:
        print(f"FAULT: {e}")
        stop_all(motors)
        return 1
    finally:
        for m in motors.values():
            m.safe_stop()


def cmd_run(args):
    motors = open_motors(args.motor)
    install_stop_handlers(motors)
    for m in motors.values():
        m.init()

    selected = list(motors)
    direction, speed, running = DIR_FORWARD, RUN_SPEED, False
    last_issue = last_poll = 0.0

    def start():
        nonlocal running, last_issue
        for n in selected:
            m = motors[n]
            if m.is_stalled():
                m.clear_stall()
            m.enable(True)
            if m.has_checksum:
                m.move(direction, speed, BIG_PULSE_COUNT, retries=2)
            else:
                m.run(direction, speed)
        running, last_issue = True, time.monotonic()

    def stop():
        nonlocal running
        stop_all(motors)
        running = False

    print("keys: 1/2/b select motor, g start, s stop, r reverse, + - speed, p status, q quit")
    print(f"selected={selected} dir={direction} speed={speed}")
    try:
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if ready:
                key = sys.stdin.readline().strip()
                if key in ("1", "2"):
                    if key not in motors:
                        print(f"motor{key} not opened"); continue
                    selected = [key]
                elif key == "b":
                    selected = list(motors)
                elif key == "g":
                    start()
                elif key == "s":
                    stop()
                elif key == "r":
                    direction ^= 1
                    if running: start()
                elif key in ("+", "-"):
                    speed = min(127, speed + 1) if key == "+" else max(MIN_SPEED, speed - 1)
                    if running: start()
                elif key == "p":
                    for n, m in motors.items():
                        print_status(n, m)
                elif key == "q":
                    break
                print(f"selected={selected} dir={direction} speed={speed} running={running}")

            now = time.monotonic()
            if running and now - last_issue >= REISSUE_S:
                start()
            if running and now - last_poll >= STALL_POLL_S:
                last_poll = now
                for n, m in motors.items():
                    if m.is_stalled():
                        raise ServoError(f"motor{n} stalled")
    except ServoError as e:
        print(f"FAULT: {e}")
        if any(m.consecutive_failures for m in motors.values()):
            print("communication lost; check wiring, CR_UART mode, 115200 baud")
        stop_all(motors)
        return 1
    finally:
        stop_all(motors)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("loopback")
    for name in ("status", "init", "run"):
        s = sub.add_parser(name)
        s.add_argument("motor", nargs="?", default="both", choices=["1", "2", "both"])
    s = sub.add_parser("move")
    s.add_argument("motor", choices=["1", "2", "both"])
    s.add_argument("mm", type=float, help="distance; negative reverses")
    s.add_argument("--speed", type=int, default=RUN_SPEED)
    s.add_argument("--timeout", type=float, default=60.0)
    s = sub.add_parser("seek")
    s.add_argument("motor", choices=["1", "2", "both"])
    s.add_argument("--reverse", action="store_true")
    s.add_argument("--speed", type=int, default=SEEK_SPEED)
    s.add_argument("--error", type=float, default=SEEK_ERROR_DEG,
                   help="shaft error in degrees that counts as blocked")
    s.add_argument("--max-deg", type=float, default=360.0,
                   help="give up after turning this far")
    s.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()
    handlers = {"loopback": cmd_loopback, "status": cmd_status, "init": cmd_init,
                "move": cmd_move, "seek": cmd_seek, "run": cmd_run}
    try:
        return handlers[args.cmd](args)
    except ServoError as e:
        print(f"FAULT: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
