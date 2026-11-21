"""
arm_cmd: send one command to motion.py and print its reply.

    python3 arm_cmd.py status
    python3 arm_cmd.py home
    python3 arm_cmd.py pick 1 3 egg      (from pocket 1 to pocket 3, object egg)
    python3 arm_cmd.py jog lift 5        (move a joint by +5 arm degrees)
    python3 arm_cmd.py teach 2           (save the current pose as pocket 2)
    python3 arm_cmd.py pause | resume | stop | reset | reset-rehome
    python3 arm_cmd.py watch             (status 5x per second until Ctrl-C)
    python3 arm_cmd.py wait              (until motion is idle; exit 1 on FAULT)

Teaching pockets: home, then jog each joint until the jaws sit in a pocket,
then `teach N`. It's written into config/arm.json.
"""

import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config", "arm.json")) as f:
    PORT = json.load(f)["cmd_port"]


def send(msg):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    s.sendto(json.dumps(msg).encode(), ("127.0.0.1", PORT))
    try:
        return json.loads(s.recv(8192))
    except socket.timeout:
        return {"ok": False, "error": "no reply: is motion.py running?"}


def short(r):
    t = r.get("timing") or {}
    return (f"{r.get('state')} {r.get('step') or ''} | joints={r.get('joints')} "
            f"homed={r.get('homed')} picks={r.get('picks_done')} last={r.get('last_result')} "
            f"| jitter max={t.get('jitter_max_ms')}ms missed={t.get('missed_total')}"
            + (f"  FAULT: {r['fault']}" if r.get("fault") else "")
            + ("" if r.get("ok", True) else f"  ERROR: {r.get('error')}"))


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd = argv[0].upper()
    if cmd == "WATCH":
        while True:
            print(short(send({"cmd": "STATUS"})), flush=True)
            time.sleep(0.2)
    if cmd == "WAIT":
        last = None
        while True:
            r = send({"cmd": "STATUS"})
            line = short(r)
            if r.get("state") != last:
                print(line, flush=True)
                last = r.get("state")
            if r.get("state") == "FAULT" or not r.get("ok", True):
                return 1
            if not r.get("busy"):
                return 0
            time.sleep(0.1)
    msg = {"cmd": cmd}
    if cmd == "PICK":
        msg.update({"from": argv[1], "to": argv[2], "label": argv[3]})
    elif cmd == "JOG":
        msg.update({"joint": argv[1], "deg": float(argv[2])})
    elif cmd == "TEACH":
        msg["pocket"] = argv[1]
    elif cmd == "RESET-REHOME":
        msg = {"cmd": "RESET", "rehome": True}
    elif cmd == "FAULT":
        msg["reason"] = " ".join(argv[1:]) or "manual fault"
    r = send(msg)
    print(short(r))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
