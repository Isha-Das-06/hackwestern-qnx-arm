#!/bin/sh
# CPU-hog demo: N busy loops at normal priority for S seconds (default 6 x 30 s).
#   ./hog.sh          ./hog.sh 8 60
# Watch the dashboard: vision FPS drops, but the gripper force loop (prio 30)
# and motion (prio 30) keep their timing, because QNX schedules by priority.
N=${1:-6}; S=${2:-30}
echo "starting $N CPU hogs for $S s"
i=0; PIDS=""
while [ $i -lt $N ]; do
    python3 -c "while True: pass" & PIDS="$PIDS $!"
    i=$((i + 1))
done
sleep "$S"
kill $PIDS 2>/dev/null
echo "hogs stopped"
