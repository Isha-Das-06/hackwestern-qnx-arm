"""
fake_vision: stands in for the camera app when testing the supervisor.
Sends the same 5 Hz heartbeat the real vision app sends (to UDP 5622).

    python3 fake_vision.py               (supervisor --sim starts it for you)
Kill it with kill -9 to rehearse the crash demo: the supervisor pauses the
arm, restarts this, and the arm carries on.
Pretend a hand is in view:  echo 1 > /tmp/fake_hands   (echo 0 to clear).
It prints the START window it hears back from the supervisor.
"""

import json
import os
import random
import socket
import time

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config", "supervisor.json")) as f:
    PORT = json.load(f)["vision_port"]


def hands():
    try:
        with open("/tmp/fake_hands") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setblocking(False)
print(f"fake_vision: booting 2 s (like the camera app), then heartbeat to udp {PORT}, "
      f"pid {os.getpid()}", flush=True)
time.sleep(2.0)
armed = False
while True:
    s.sendto(json.dumps({
        "t": time.time(), "fake": True, "fps": round(random.uniform(14, 16), 1),
        "state": "IDLE", "labels": ["egg", "empty", "cup", "block"],
        "confidence": [0.97, 0.99, 0.95, 0.96], "hands": hands()}).encode(),
        ("127.0.0.1", PORT))
    try:
        msg = json.loads(s.recv(1024))
        if (msg.get("select_s", 0) > 0) != armed:
            armed = not armed
            print(f"fake_vision: pointing {'ARMED' if armed else 'disarmed'}", flush=True)
    except (BlockingIOError, ValueError):
        pass
    time.sleep(0.2)
