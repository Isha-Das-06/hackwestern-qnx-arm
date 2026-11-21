import time
from mks_servo import Servo42C
m = Servo42C("/dev/ser5", 0xE0, name="motor2", firmware="1.0")
print("before: enc=%.2f pulses=%d" % (m.encoder_degrees(), m.pulses_received()))
m.enable(True)
try:
    print("F6 speed 10 ->", m.transact(0xF6, [10]).hex())
    time.sleep(1.0)
    print("during: enc=%.2f pulses=%d" % (m.encoder_degrees(), m.pulses_received()))
finally:
    m.safe_stop()
time.sleep(0.3)
print("after stop: enc=%.2f pulses=%d" % (m.encoder_degrees(), m.pulses_received()))
print("En pin status 3A ->", m.transact(0x3A).hex())
