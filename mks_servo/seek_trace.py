"""Trace run_until_blocked on one motor: python3 seek_trace.py 1 [--reverse]"""
import sys
import time

import servo_test as st
from mks_servo import Servo42C

n = sys.argv[1]
direction = st.DIR_FORWARD ^ 1 if "--reverse" in sys.argv else st.DIR_FORWARD
m = Servo42C(*st.MOTORS[n][:2], name=f"motor{n}", firmware=st.MOTORS[n][2])
t0 = time.monotonic()
state = {"enc": 0.0, "polls": 0}


def log(msg):
    print(f"{time.monotonic() - t0:6.2f}s  {msg}", flush=True)


def wrap(name, on_call):
    real = getattr(m, name)

    def wrapper(*a, **k):
        result = real(*a, **k)
        on_call(a, result)
        return result
    setattr(m, name, wrapper)


def on_err(a, err):
    state["polls"] += 1
    if abs(err) > 5 or state["polls"] % 10 == 0:
        log(f"enc={state['enc']:8.2f}  err={err:+7.2f}")


wrap("encoder_degrees", lambda a, r: state.update(enc=r))
wrap("shaft_error_degrees", on_err)
wrap("is_stalled", lambda a, r: r and log("STALLED (protection tripped)"))
for cmd in ("stop", "run", "move", "clear_stall", "enable", "set_protection"):
    wrap(cmd, lambda a, r, cmd=cmd: log(f"{cmd}{a}"))

try:
    turned = st.run_until_blocked(m, direction)
    log(f"DONE: blocked after {turned:.1f} deg")
except st.ServoError as e:
    log(f"FAULT: {e}")
finally:
    m.safe_stop()
    log(f"final: enc={m.encoder_degrees():.2f} err={m.shaft_error_degrees():+.2f} "
        f"stalled={m.is_stalled()}")
