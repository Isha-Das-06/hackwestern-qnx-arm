# hackwestern-qnx-arm

Tabletop pick-and-place for Hack Western 13 (QNX track). It runs on QNX 8 on a
Raspberry Pi 4. You point at one of four boxes, the camera says what is in it,
and the arm moves that object to an empty box with a grip force for that object.

The objects are a pill bottle, a squeeze bottle, and a blister of pills. Inside
the code those ids stay `egg`, `cup`, and `block`. The consoles show the real names.

QNX owns every decision that moves something. The Pico 2 only streams force
readings. The Pi drives the gripper servo. If the supervisor dies, actuator
power drops.

## Processes

The supervisor starts the other three. Each is its own QNX process.

| Process | Priority | What it does |
|---|---|---|
| `supervisor` (`mks_servo/supervisor.py`) | 40 | Safety pins, heartbeats, sticky faults. Dashboard on port 8090 |
| `motion` (`mks_servo/motion.py`) | 30 | Both SERVO42C joints: home, soft limits, the pick-and-place sequence. UDP 5611, status on 5612 at 10 Hz |
| `gripper_link` (`mks_servo/gripper_link.py`) | 30 | 100 Hz force loop. UDP 5601, status on 5602 at 20 Hz |
| `vision` (`python/pointing.py --arm`) | 10 | Camera, hand tracking, classifier. Operator console on port 8080. Heartbeat to the supervisor on UDP 5622 at 5 Hz |

On the Pi the trees are split. Arm code lives in `~/mks_servo`. Vision lives in
`~/pickvision`, and the supervisor starts it with `run_pi.sh --arm`.

Vision sends a label, not a force number:

```json
{"cmd": "PICK", "from": 1, "to": 3, "label": "egg"}
```

`motion` checks that label against `mks_servo/config/grip_profiles.json`, then
tells `gripper_link` to grip. The same windows are in `config/grip.yml` so the
operator console can show them. Keep the two files the same.

| Id | On screen | Grip | Target | Max |
|---|---|---|---|---|
| `block` | Pills | light | 14 | 100 |
| `egg` | Pill bottle | medium | 25 | 150 |
| `cup` | Squeeze bottle | firm | 20 | 120 |

Targets and maxes are raw FSR counts on the stronger jaw, tuned from grips on
the real pads. If the jaws reach the closed angle first and the stronger jaw
peaked at `contact_force` (12), that still counts as a grip.

## Run it on the Pi

```sh
cd ~/mks_servo
./start_robot.sh                              # real robot
./start_robot.sh --sim                        # fake Pico, motors, and vision
./start_robot.sh --sim --real-vision          # real camera app, fake arm
./start_robot.sh --no-estop --no-start-button # buttons not wired; START from the console or dashboard
./stop_robot.sh
```

Dashboard: `http://<pi-ip>:8090` (STOP, START, Reset, Home, Open gripper, live
force, loop timing, event log). Operator console: `http://<pi-ip>:8080`.
Logs: `/tmp/robot/`.

The real robot needs `/dev/ser3`, `/dev/ser4`, and `/dev/ser5`. Bring them up
once as root (also sets the safety pins off and the servo line idle):

```sh
echo 'sh /data/home/qnxuser/mks_servo/uart_setup.sh' >> /usr/etc/startup/post_startup.sh
```

From a Windows laptop, `sync_to_pi.bat` copies `mks_servo/` to `~/mks_servo` and
`python/`, `qnx/`, and `run_pi.sh` to `~/pickvision`. It leaves the Pi's taught
pockets (`~/mks_servo/config/taught.json`) and its vision config alone.

## What a move is

1. Press START (green button, operator console, or dashboard). That opens a 15 s window. One START is one move.
2. Point at the box with the object for 1 s. The classifier names it. Pointing means an index finger out and the other fingers curled. A fingertip reaching in from the edge of the frame counts too.
3. Point at an empty box for 1 s. A box that already has something is refused.
4. `motion` runs `MOVE_TO_PICK → LOWER → GRIP → LIFT → MOVE_TO_PLACE → LOWER → RELEASE → HOME`. The base only turns at travel height (64 mm), so the jaws clear the bottles in the other docks.

Pocket angles are taught joint positions in `taught.json` on the Pi (defaults in
`mks_servo/config/arm.json` until then). There is no inverse kinematics.

A hand in the camera pauses the arm and holds the grip. The arm continues once
the hand has been gone for 1 s. Vision dying does the same pause, then the
supervisor restarts vision and resumes. That is not a fault.

These are faults, and only Reset clears them:

- E-stop pressed, or its wire open. Actuator power is already off.
- `gripper_link` or `motion` dies or goes silent. If `motion` died, the supervisor stops the drivers itself.
- The Pico FSR link goes stale. `gripper_link` holds the last servo angle.
- `motion` reports its own stop: obstruction, stall, timeout, or the object slipping while it is being carried.

A grip that never reaches the target (empty pocket, or the jaws hit the force
cap) opens over that pocket and the arm goes home. The object is still in its dock.

## Hardware

| Thing | Connection |
|---|---|
| Lift, SERVO42C firmware 1.1 | UART3 `/dev/ser3`, GPIO4 TX / GPIO5 RX. Position in mm |
| Base, SERVO42C firmware 1.0 | UART5 `/dev/ser5`, GPIO12 TX / GPIO13 RX. Position in degrees |
| Pico 2 FSR board | UART4 `/dev/ser4`, Pi GPIO8 TX / GPIO9 RX. Two FSRs on Pico GP26 and GP27, ~200 Hz frames |
| Gripper servo | Pi hardware PWM, GPIO19 (pin 35), 50 Hz. Separate 5 V. `gripper_link` sets the pulse |
| Actuator power enable | GPIO18, held with a 100% PWM by the supervisor |
| Fault LED | GPIO27. On = fault, blinking = paused |
| E-stop | NC contact, GPIO17 to GND. 0 = OK, 1 = pressed or wire broken. The other contact cuts actuator power in hardware |
| START | GPIO23 to GND. 0 = pressed |

`--no-estop` ignores GPIO17, because an unwired pulled-up pin reads as pressed
and would hold power off. The dashboard then shows the e-stop as not connected.
`--no-start-button` ignores GPIO23.

Flash `pico_gripper/pico_gripper.ino` to a Pico 2 (Tenstar RP2350, Earle
Philhower core). The firmware never moves the servo. Jaw travel is clamped in
`mks_servo/config/gripper.json` (15° open side, 84° closed side).

Wiring, frame bytes, and bench notes: `docs/GRIPPER.md`, `docs/MOTION.md`,
`docs/SUPERVISOR.md`. The grip numbers the robot uses are the ones in
`grip_profiles.json` and `grip.yml`.

## Vision on its own

On the Pi, without the arm:

```sh
~/pickvision/run_pi.sh          # console at http://<pi-ip>:8080
~/pickvision/run_pi.sh stop
```

On a laptop (same `pointing.py`; a window instead of the browser, and picks are
simulated):

```bat
run_python.bat
```

That creates `python\.venv`, installs `python\requirements.txt`, and downloads
the hand model if `models\hand_landmarker.task` is missing.

The camera path on QNX is `qnx/pv_cam` (`make -C qnx`). OpenCV cannot open a
camera there, so the C bridge uses QNX camapi and `python/qnx_camera.py` reads
frames from its pipe. Camera headers come with the QNX SDK and are not in this
repo. The hand tracker is a Python port of the tracker in the
[QNX AI workshop](https://github.com/qnx/QNX-AI-workshop).

Teach the classifier from the console: photo of the empty tray, then about five
examples of each object. Boxes are stored in `config/tray.yml`, examples in
`config/classifier_py.npz`. An empty pocket is "pixels match the empty photo."
Anything that matches neither the examples nor empty is unknown.

## Layout

| Path | What it is |
|---|---|
| `mks_servo/` | Supervisor, motion, gripper loop, SERVO42C driver, JSON config, robot dashboard, simulators (`fake_pico.py`, `fake_vision.py`, `sim_servo.py`) |
| `pico_gripper/` | Pico 2 firmware: FSR stream only |
| `python/` | Vision app: `pointing.py`, `classifier.py`, `handtrack_tflite.py`, `fingertip.py`, `arm_link.py`, `qnx_camera.py`, `web_ui.py` |
| `python/web/` | Operator console (port 8080) |
| `qnx/` | `pv_cam.c`, the QNX camera bridge |
| `models/` | Palm and landmark models |
| `config/` | Tray boxes, taught examples, grip windows for the console |
| `docs/` | Wiring, protocols, and what was tested on the Pi |
| `cloud/` | Optional move history (Vultr + Tiger Data). No `config/cloud.json` means cloud off. The robot runs without it |
| `design/` | Earlier console mockups |
| `src/`, `CMakeLists.txt` | Earlier C++ vision app. The robot runs the Python app |

`GAMEPLAN.md` and `CHAT_SUMMARY.md` are working notes from the hackathon, not the
current behavior of this branch.
