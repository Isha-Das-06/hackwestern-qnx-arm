from mks_servo import Servo42C
m = Servo42C("/dev/ser3", 0xE0, name="motor1", firmware="1.1")
print("En state before:", m.transact(0x3A)[0], "(1 = enabled, 2 = disabled)")
m.enable(True)
print("En state after F3 01:", m.transact(0x3A)[0])
m.enable(False)
print("En state after F3 00:", m.transact(0x3A)[0])
