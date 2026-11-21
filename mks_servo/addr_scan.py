#!/usr/bin/env python3
"""Scan SERVO42C addresses at 115200, with and without checksum (V1.1 vs V1.0 firmware)."""
import os, select, sys, termios, time

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ser3"
ADDRS = list(range(0xE0, 0xEA)) + [0x30]

def configure(fd):
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = termios.B115200
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)

def read_for(fd, s):
    buf, end = b"", time.monotonic() + s
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], end - time.monotonic())
        if r:
            buf += os.read(fd, 64)
    return buf

fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY)
configure(fd)
found = False
for addr in ADDRS:
    for label, pkt in (("chk", bytes([addr, 0x30, (addr + 0x30) & 0xFF])),
                       ("no-chk", bytes([addr, 0x30]))):
        os.write(fd, pkt)
        reply = read_for(fd, 0.2)
        if reply:
            found = True
            print(f"{PORT} addr 0x{addr:02X} {label:6} {pkt.hex(' ')} -> {reply.hex(' ')}")
print("replies found" if found else f"{PORT}: no replies at any address")
os.close(fd)
