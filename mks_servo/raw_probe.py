#!/usr/bin/env python3
"""Send a few SERVO42C reads at several baud rates and dump whatever comes back."""
import os, select, sys, termios, time

PORTS = sys.argv[1:] or ["/dev/ser3", "/dev/ser5"]
BAUDS = [115200, 38400, 57600, 19200, 9600]
COMMANDS = [b"\xe0\x30\x10", b"\xe0\x3e\x1e", b"\xe0\x3a\x1a"]

def configure(fd, baud):
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = getattr(termios, f"B{baud}")
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)

def read_for(fd, seconds):
    buf, end = b"", time.monotonic() + seconds
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], end - time.monotonic())
        if r:
            buf += os.read(fd, 64)
    return buf

for port in PORTS:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    for baud in BAUDS:
        configure(fd, baud)
        idle = read_for(fd, 0.1)
        line = f"{port} {baud:>6}: idle={idle.hex(' ') or '-'}"
        for cmd in COMMANDS:
            os.write(fd, cmd)
            line += f" | {cmd.hex(' ')} -> {read_for(fd, 0.2).hex(' ') or '-'}"
        print(line)
    configure(fd, 115200)
    os.close(fd)
