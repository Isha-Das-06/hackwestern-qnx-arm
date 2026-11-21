"""
fake_vision: stands in for the camera app when testing the supervisor.
Sends the same 5 Hz heartbeat the real vision app sends (to UDP 5622).

    python3 fake_vision.py               (supervisor --sim starts it for you)
Kill it with kill -9 to rehearse the crash demo: the supervisor pauses the
arm, restarts this, and the arm carries on.
"""

import json
import os
import random
import socket
import time

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config", "supervisor.json")) as f:
    PORT = json.load(f)["vision_port"]

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print(f"fake_vision: booting 2 s (like the camera app), then heartbeat to udp {PORT}, "
      f"pid {os.getpid()}", flush=True)
time.sleep(2.0)
while True:
    s.sendto(json.dumps({
        "t": time.time(), "fake": True, "fps": round(random.uniform(14, 16), 1),
        "state": "IDLE", "labels": ["egg", "empty", "cup", "block"],
        "confidence": [0.97, 0.99, 0.95, 0.96]}).encode(), ("127.0.0.1", PORT))
    time.sleep(0.2)
