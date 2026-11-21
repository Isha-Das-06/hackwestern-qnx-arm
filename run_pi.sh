#!/bin/sh
# Start the pointing + classifier app on the QNX Pi.
#   ssh qnxuser@<pi-ip>    then:   ~/pickvision/run_pi.sh
# Then open http://<pi-ip>:8080 in a browser on the same network.
# Extra options pass through, e.g.  ./run_pi.sh --cam 1   (another QNX camera unit)
# Stop it:  ~/pickvision/run_pi.sh stop
cd "$(dirname "$0")" || exit 1

stop_old() {
    # Only this app's processes (QNX has no pkill; pidin lists pid + arguments).
    for p in $(pidin -f aA 2>/dev/null | grep -E "python/pointing.py|pickvision/qnx/pv_cam" \
               | grep -v grep | awk '{print $1}'); do
        [ "$p" != "$$" ] && kill "$p" 2>/dev/null
    done
    sleep 1
}

stop_old
[ "$1" = "stop" ] && { echo "stopped"; exit 0; }
[ -x qnx/pv_cam ] || make -s -C qnx || exit 1   # build the camera bridge once
exec python3 python/pointing.py "$@"
