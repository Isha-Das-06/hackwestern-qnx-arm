import os, select, termios, time
fd = os.open("/dev/ser5", os.O_RDWR | os.O_NOCTTY)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
termios.tcflush(fd, termios.TCIOFLUSH)
def rd(s=0.25):
    buf, end = b"", time.monotonic() + s
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], end - time.monotonic())
        if r: buf += os.read(fd, 64)
    return buf
for cmd in (0x30, 0x33, 0x39, 0x3A, 0x3E, 0x30, 0x30):
    pkt = bytes([0xE0, cmd, (0xE0 + cmd) & 0xFF])
    os.write(fd, pkt)
    print(pkt.hex(' '), '->', rd().hex(' ') or '-')
