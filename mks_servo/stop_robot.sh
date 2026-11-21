#!/bin/sh
# Stop the robot software. The supervisor tells motion to STOP first, so the
# motors stop and stay enabled (holding). It does NOT open the gripper.
# QNX has no pkill, so find our processes with pidin.
for p in $(pidin -f aA 2>/dev/null | grep -E "python3 supervisor.py" | grep -v grep | awk '{print $1}'); do
    kill "$p" 2>/dev/null           # SIGTERM: supervisor shuts its children down
done
sleep 2
# Anything left over (e.g. supervisor was kill -9'd): stop it too.
for p in $(pidin -f aA 2>/dev/null | grep -E "python3 (gripper_link|motion|fake_pico|fake_vision|supervisor)\.py|python/pointing.py|pickvision/qnx/pv_cam" \
           | grep -v grep | awk '{print $1}'); do
    [ "$p" != "$$" ] && kill -9 "$p" 2>/dev/null
done
[ "$1" = "quiet" ] || echo "robot stopped"
