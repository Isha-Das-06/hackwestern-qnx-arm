import time
from mks_servo import Servo42C
m = Servo42C("/dev/ser5", 0xE0, name="motor2", firmware="1.0")
p0, e0 = m.pulses_received(), m.encoder_degrees()
print("before: enc=%.2f pulses=%d" % (e0, p0))
m.enable(True)
try:
    m.move(1, 10, 11830)
    print("FD accepted")
    end = time.monotonic() + 10
    while time.monotonic() < end and m.moves_completed == 0:
        time.sleep(0.2)
        m._drain()
    print("completion frame seen:", m.moves_completed > 0)
finally:
    m.safe_stop()
time.sleep(0.2)
p1, e1 = m.pulses_received(), m.encoder_degrees()
print("after: enc=%.2f pulses=%d  (moved %d pulses)" % (e1, p1, p1 - p0))
