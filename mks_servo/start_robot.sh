#!/bin/sh
# One command to start the whole robot:   ./start_robot.sh        (real hardware)
#                                          ./start_robot.sh --sim  (no hardware)
# Buttons not wired yet:  ./start_robot.sh --no-estop --no-start-button
#   (either one alone works too; START then comes from the console or dashboard)
# Stop it:  ./stop_robot.sh      Dashboard: http://<pi-ip>:8090
# Logs: /tmp/robot/supervisor.log (and gripper.log, motion.log, vision.log)
cd "$(dirname "$0")" || exit 1
mkdir -p /tmp/robot

SIM=0
for a in "$@"; do [ "$a" = "--sim" ] && SIM=1; done
if [ "$SIM" = 0 ]; then
    for n in 3 4 5; do
        [ -e /dev/ser$n ] || { echo "/dev/ser$n missing: run  su -c 'sh uart_setup.sh'  (or add it to post_startup.sh)"; exit 1; }
    done
fi
./stop_robot.sh quiet
nohup on -p 40 python3 supervisor.py "$@" > /tmp/robot/supervisor.log 2>&1 &
sleep 3
tail -n 8 /tmp/robot/supervisor.log
IP=$(ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" {print $2; exit}')
echo "dashboard: http://${IP:-<pi-ip>}:8090"
