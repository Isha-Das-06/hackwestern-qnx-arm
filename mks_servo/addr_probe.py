#!/usr/bin/env python3
"""Try SERVO42C-style and SERVO42D-style frames at 115200 and dump replies."""
import os, select, termios, time

def ck(b):
    return bytes(b) + bytes([sum(b) & 0xFF])

PACKETS = {
    "42C addr E0 read encoder": ck([0xE0, 0x30]),
    "42C addr 30 read encoder": ck([0x30, 0x30]),
    "42C addr 30 read stall":   ck([0x30, 0x3E]),
    "42D addr 30 read encoder": ck([0xFA, 0x30, 0x31]),
    "42D addr 30 read carry":   ck([0xFA, 0x30, 0x30]),
    "42D addr 30 read status":  ck([0xFA, 0x30, 0xF1]),
    "42D addr 01 read encoder": ck([0xFA, 0x01, 0x31]),
    "42D broadcast read enc":   ck([0xFA, 0x00, 0x31]),
}

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

for port in ("/dev/ser3", "/dev/ser5"):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    configure(fd)
    for name, pkt in PACKETS.items():
        os.write(fd, pkt)
        print(f"{port} {name:26} {pkt.hex(' '):18} -> {read_for(fd, 0.25).hex(' ') or '-'}")
    os.close(fd)
