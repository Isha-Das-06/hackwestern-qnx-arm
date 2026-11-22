# Supervisor, e-stop, dashboard and demo

```
                 ┌──────────────────────────── supervisor (prio 40) ───────────────────────────┐
                 │ starts + watches everything · e-stop GPIO17 · dashboard :8090              │
                 └──────▲──────────────────────────▲──────────────────────────▲───────────────┘
              heartbeat │ 5 Hz            heartbeat │ 10 Hz          heartbeat │ 20 Hz
  ┌──────────────────────┴───┐   PICK    ┌──────────┴──────────┐  GRIP   ┌────┴───────────────┐  UART4  ┌──────────┐
  │ vision (normal prio)     │ ────────▶ │ motion (prio 30)    │ ──────▶ │ gripper_link       │ ──────▶ │ Pico 2   │
  │ hand + classifier        │  UDP 5611 │ pick-and-place      │ UDP5601 │ 100 Hz force loop  │ ◀────── │ FSR+servo│
  └──────────────────────────┘           │ SERVO42C x2 (UART3/5)│        │ (prio 30)          │         └──────────┘
                                         └─────────────────────┘         └────────────────────┘
```

## One command

```sh
cd ~/mks_servo
./start_robot.sh          # real robot (needs /dev/ser3, ser4 and ser5, see GRIPPER.md)
./start_robot.sh --sim    # fake Pico, fake motors, fake vision: rehearse anywhere
./start_robot.sh --sim --real-vision   # real camera app, fake arm
./stop_robot.sh
```

The dashboard is at `http://<pi-ip>:8090`. It has STOP, Reset, Home and Open gripper buttons, and shows live force bars, every process's loop timing, and the event log. Logs are in `/tmp/robot/*.log`.

## Rules (one sentence each)

1. If the e-stop is pressed, or its wire is broken, that's a FAULT. The hardware has already cut motor power; the software just refuses to move until RESET.
2. If `gripper_link` or `motion` dies or goes silent, that's a FAULT: stop and hold. If motion is the one that died, the supervisor sends STOP to the drivers itself.
3. If the Pico link goes stale, that's a FAULT. The Pico has already frozen the servo on its own.
   If motion faults by itself (a joint pushing against something, a stall, a timeout, the object slipping), the supervisor latches that FAULT too. Motion is already holding; the fault LED (GPIO27, pin 13) comes on and Reset is needed.
4. If vision dies or goes silent, motion is PAUSED (holding), vision is restarted, and motion RESUMES once vision's heartbeat is back. A vision crash is never a fault.
5. A FAULT is sticky: only Reset clears it. Reset restarts any dead process, and after an e-stop it re-homes the arm.

## E-stop wiring (hardware team)

- A latching mushroom button whose **main contact** cuts 12–24 V to both SERVO42Cs and the servo's 5–6 V, through a relay or contactor.
- Its **second, normally-closed contact** goes between **GPIO17 (pin 11)** and **GND (pin 9)**. `uart_setup.sh` turns on the pull-up, so:
  - the pin reads **0** when everything is OK;
  - it reads **1** when the button is pressed **or a wire comes loose** (fail-safe).
- After an e-stop, the base motor was unpowered, so park the base on its zero mark before you press Reset.

## Demo script (2 minutes)

1. **The pick.** Run `./start_robot.sh`. The judge points and pinches at the egg pocket, then at an empty pocket. On the dashboard, the force bar rises to the egg's green line and stops.
2. **Real-time under load.** Run `./hog.sh 6 30` and do another pick. Vision FPS drops, but the gripper (100 Hz) and motion stay around 1 ms late at worst, with **0 missed** deadlines. The line to use: "QNX schedules by priority."
   - For contrast, `on -p 10 python3 gripper_link.py` under the same hog showed **137 ms** jitter and **124 missed** deadlines (see GRIPPER.md).
3. **Crash recovery.** While the arm carries the egg, run `kill -9 <vision pid>` (the pid is on the dashboard). The arm stops and holds the egg, vision comes back, and the arm finishes.
4. **The e-stop.** Press it. Power is cut in hardware, the dashboard shows FAULT, and Reset is refused until the button is released.
5. The pitch line: "QNX makes every decision; the hardware fails to a safe hold if QNX goes silent."

## Tested on the Pi (`--sim`: fake Pico, fake motors, fake vision)

| Test | Result |
|---|---|
| `kill -9` vision while carrying | PAUSED and holding (gripper still GRIPPED), vision restarted, RESUMED, pick `done` |
| E-stop pressed mid-move | FAULT, arm held. Reset refused while pressed; after release, Reset re-homed |
| `kill -9 gripper_link` | FAULT. Reset restarted it |
| `kill -9 motion` mid-move | FAULT, STOP sent to the drivers (simulated in sim). Reset restarted motion, which re-homed |
| Pico link lost (fake Pico paused) | FAULT "Pico link stale" |
| 6 CPU hogs during a pick | Gripper worst 0.5 ms, motion worst 1.05 ms, supervisor worst 8 ms, 0 missed |
| Dashboard from the laptop | `http://192.168.8.247:8090/state` answers |

Seen once and not reproduced in 3 later runs: the supervisor loop was 1.2 s late, during a CPU-hog run. Gripper and motion timing were fine in that run. Keep an eye on it.
