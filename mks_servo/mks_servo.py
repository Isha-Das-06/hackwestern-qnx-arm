"""
MKS SERVO42C UART driver for QNX (Raspberry Pi 4), ported from mks_servo42c.ino.

Protocol, mode CR_UART:
    firmware V1.1.x:  request [addr, cmd, payload..., chk]   reply [addr, data..., chk]
    firmware V1.0.x:  request [addr, cmd, payload...]        reply [addr, data...]
    chk = sum of all previous bytes & 0xFF

V1.0 differences seen on real hardware: no checksums, the encoder read
(0x30) returns only a 16-bit angle, acceleration (0xA4) and stall
protection (0x88) get no reply (init() skips them), and the 0xFD move is
acknowledged but never runs. Use run() (0xF6) plus stop() on V1.0.

A 0xFD move sends two replies: [addr, 0x01(, chk)] when it starts and
[addr, 0x02(, chk)] later when the pulse count finishes. The second one
arrives whenever the move ends, so the reader skips over it and counts it
in `moves_completed` instead of treating it as garbage.

Only uses the Python standard library (os, termios, select), because
pyserial isn't installed on the QNX image.
"""

import os
import select
import termios
import time


class ServoError(Exception):
    """A command got no valid reply, or the driver reported failure."""


def checksum(data):
    return sum(data) & 0xFF


class Servo42C:
    # Defaults from the working pelletizer sketch.
    MSTEP_VALUE = 236
    ACC_VALUE = 0x0050
    PULSES_PER_REV = MSTEP_VALUE * 200

    def __init__(self, port, addr=0xE0, name=None, firmware="1.1",
                 timeout=0.15, retries=3):
        self.port = port
        self.addr = addr
        self.name = name or port
        self.has_checksum = firmware != "1.0"
        self.timeout = timeout
        self.retries = retries
        self.moves_completed = 0
        self.consecutive_failures = 0
        self.done_frame = self._frame([addr, 0x02])
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
        self._configure_port()

    def _frame(self, data):
        data = bytes(data)
        return data + bytes([checksum(data)]) if self.has_checksum else data

    # ------------------------------------------------------------------
    # Serial port
    # ------------------------------------------------------------------

    def _configure_port(self):
        # Raw 115200 8N1, no flow control, no echo, no line editing.
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0                                                  # iflag
        attrs[1] = 0                                                  # oflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL       # cflag
        attrs[3] = 0                                                  # lflag
        attrs[4] = termios.B115200                                    # ispeed
        attrs[5] = termios.B115200                                    # ospeed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _read_available(self, wait):
        ready, _, _ = select.select([self.fd], [], [], max(wait, 0))
        if not ready:
            return b""
        return os.read(self.fd, 64)

    def _drain(self):
        """Throw away stale input, but count any 'move complete' frames in it."""
        buf = b""
        while True:
            chunk = self._read_available(0.002)
            if not chunk:
                break
            buf += chunk
        self.moves_completed += buf.count(self.done_frame)

    def _valid(self, frame):
        if frame[0] != self.addr:
            return False
        return not self.has_checksum or frame[-1] == checksum(frame[:-1])

    def _read_frame(self, length):
        """Wait for a valid `length`-byte frame from our address.

        The 'move complete' frame is byte-for-byte the same as the normal
        reply to 0x3E ('not stalled'). It's skipped while waiting, and only
        used as the reply if nothing else arrives.
        """
        done = self.done_frame
        skipped_done = False
        buf = b""
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            buf += self._read_available(deadline - time.monotonic())
            while len(buf) >= length or buf[:len(done)] == done:
                if buf[:len(done)] == done:
                    self.moves_completed += 1
                    skipped_done = True
                    buf = buf[len(done):]
                    deadline = min(deadline, time.monotonic() + 0.02)
                    continue
                frame = buf[:length]
                if self._valid(frame):
                    return frame
                buf = buf[1:]
        if skipped_done and length == len(done):
            self.moves_completed -= 1
            return done
        return None

    def transact(self, cmd, payload=b"", data_len=1, retries=None):
        """Send one command; return the reply's data bytes (no addr, no checksum)."""
        packet = self._frame([self.addr, cmd] + list(payload))
        reply_len = 1 + data_len + (1 if self.has_checksum else 0)
        attempts = 1 + (self.retries if retries is None else retries)
        for _ in range(attempts):
            self._drain()
            os.write(self.fd, packet)
            frame = self._read_frame(reply_len)
            if frame is not None:
                self.consecutive_failures = 0
                return frame[1:1 + data_len]
        self.consecutive_failures += 1
        raise ServoError(f"{self.name}: no valid reply to 0x{cmd:02X}")

    def _command(self, cmd, payload=b"", retries=None):
        """Commands whose reply is one status byte, 1 = OK."""
        status = self.transact(cmd, payload, 1, retries)[0]
        if status != 0x01:
            raise ServoError(f"{self.name}: 0x{cmd:02X} returned status {status}")

    # ------------------------------------------------------------------
    # Commands (same bytes as the working Arduino sketch)
    # ------------------------------------------------------------------

    def enable(self, on=True):
        self._command(0xF3, [0x01 if on else 0x00])
        # 0x3A reads the enable state: 1 = enabled, 2 = disabled. With the En
        # menu set to L, 0xF3 is inverted and moves are accepted but never run.
        # The state updates a few ms after the 0xF3 reply, so re-read briefly.
        if on:
            for _ in range(5):
                time.sleep(0.02)
                if self.transact(0x3A)[0] == 0x01:
                    return
            raise ServoError(f"{self.name}: still disabled after enable; set the En menu to H")

    def set_acceleration(self, acc):
        self._command(0xA4, acc.to_bytes(2, "big"))

    def set_microsteps(self, mstep):
        self._command(0x84, [mstep])

    def set_enable_active_high(self):
        """0x85 01: En = H, so 0xF3 01 enables. The factory default L inverts 0xF3."""
        self._command(0x85, [0x01])

    def set_protection(self, on=True):
        self._command(0x88, [0x01 if on else 0x00])

    def clear_stall(self):
        self._command(0x3D)

    def stop(self):
        self._command(0xF7)

    def run(self, direction, speed):
        """0xF6: turn at constant speed until stop(). Works on V1.0 and V1.1."""
        self._command(0xF6, [(speed & 0x7F) | ((direction & 0x01) << 7)])

    def move(self, direction, speed, pulses, retries=0):
        """0xFD: run `pulses` microsteps. direction 0 = CW, 1 = CCW, speed 0-127.

        Not retried by default: if the reply was lost but the driver
        heard the command, sending it again would add a second move.
        """
        val = (speed & 0x7F) | ((direction & 0x01) << 7)
        payload = bytes([val]) + int(pulses).to_bytes(4, "big")
        self._command(0xFD, payload, retries)

    def is_stalled(self):
        return self.transact(0x3E)[0] == 0x01

    def encoder_degrees(self):
        if not self.has_checksum:
            value = int.from_bytes(self.transact(0x30, data_len=2), "big")
            return value * 360.0 / 0x10000
        data = self.transact(0x30, data_len=6)
        carry = int.from_bytes(data[0:4], "big", signed=True)
        value = int.from_bytes(data[4:6], "big")
        return (carry * 0x10000 + value) * 360.0 / 0x10000

    def pulses_received(self):
        return int.from_bytes(self.transact(0x33, data_len=4), "big", signed=True)

    def shaft_error_degrees(self):
        raw = int.from_bytes(self.transact(0x39, data_len=2), "big", signed=True)
        return raw * 360.0 / 0x10000

    # ------------------------------------------------------------------
    # Helpers matching the sketch's init order
    # ------------------------------------------------------------------

    def init(self):
        """Enable, set accel + microsteps, enable stall protection, release.

        V1.0 firmware doesn't answer 0xA4 or 0x88, so those are skipped there.
        """
        if self.has_checksum:
            self.set_enable_active_high()
        self.enable(True)
        if self.has_checksum:
            self.set_acceleration(self.ACC_VALUE)
        self.set_microsteps(self.MSTEP_VALUE)
        if self.has_checksum:
            self.set_protection(True)
        self.enable(False)

    def safe_stop(self):
        """Best-effort stop AND HOLD. Never raises; used on faults.

        On an arm, releasing the shaft on a fault would drop the load, so this
        only stops the motor and leaves it enabled (holding torque on).
        Call release() explicitly when you really want the shaft free.
        """
        try:
            self.stop()
        except (ServoError, OSError):
            pass

    def release(self):
        """Best-effort stop + disable (shaft turns freely). Never raises."""
        for action in (self.stop, lambda: self.enable(False)):
            try:
                action()
            except (ServoError, OSError):
                pass
