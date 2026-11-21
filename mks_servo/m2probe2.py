import os, select, termios, time
fd = os.open("/dev/ser5", os.O_RDWR | os.O_NOCTTY)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
termios.tcflush(fd, termios.TCIOFLUSH)
def rd(s=0.3):
    buf, end = b"", time.monotonic() + s
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], end - time.monotonic())
        if r: buf += os.read(fd, 64)
    return buf
tests = [
    ("disable F3 00", b"\xe0\xf3\x00"),
    ("microsteps 84 EC", b"\xe0\x84\xec"),
    ("accel A4 0050", b"\xe0\xa4\x00\x50"),
    ("protect 88 01", b"\xe0\x88\x01"),
    ("stall 3E", b"\xe0\x3e"),
    ("en pin 3A", b"\xe0\x3a"),
]
for name, pkt in tests:
    os.write(fd, pkt)
    print(f"{name:18} {pkt.hex(' '):14} -> {rd().hex(' ') or '-'}")
