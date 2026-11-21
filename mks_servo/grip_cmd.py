"""
grip_cmd: send one command to gripper_link and print its reply.

    python3 grip_cmd.py status
    python3 grip_cmd.py open
    python3 grip_cmd.py grip egg        (egg / cup / block, see grip_profiles.json)
    python3 grip_cmd.py hold
    python3 grip_cmd.py relax
    python3 grip_cmd.py watch           (status 5x per second until Ctrl-C)
"""

import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config", "gripper.json")) as f:
    PORT = json.load(f)["cmd_port"]


def send(msg):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    s.sendto(json.dumps(msg).encode(), ("127.0.0.1", PORT))
    try:
        return json.loads(s.recv(4096))
    except socket.timeout:
        return {"ok": False, "error": "no reply: is gripper_link running?"}


def short(r):
    t = r.get("timing", {})
    return (f"{r.get('state')} obj={r.get('object')} ang={r.get('angle')} "
            f"fsr={r.get('fsr1')},{r.get('fsr2')} slip={r.get('slip')} "
            f"backoffs={r.get('over_max')} age={r.get('link_age_ms')}ms "
            f"jitter max={t.get('jitter_max_ms')}ms missed={t.get('missed_total')}"
            + ("" if r.get("ok", True) else f"  ERROR: {r.get('error')}"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1].upper()
    if cmd == "WATCH":
        while True:
            print(short(send({"cmd": "STATUS"})), flush=True)
            time.sleep(0.2)
    msg = {"cmd": cmd}
    if cmd == "GRIP":
        msg["object"] = sys.argv[2] if len(sys.argv) > 2 else "egg"
    r = send(msg)
    print(json.dumps(r) if "-v" in sys.argv else short(r))
    sys.exit(0 if r.get("ok") else 1)
