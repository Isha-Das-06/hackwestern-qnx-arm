# hackwestern-qnx-arm

Tabletop pick-and-place robot for Hack Western 13 (QNX track). Everything runs on QNX 8 on a
Raspberry Pi 4: hand pointing picks the object and where it goes, a classifier says what it is,
and QNX moves a two-joint arm and grips with a force limit for that object.

Four processes, each its own QNX process at its own priority:

| Process | Priority | What it does |
|---|---|---|
| `supervisor` (`mks_servo/supervisor.py`) | 40 | Starts and watches the others, e-stop, dashboard on port 8090 |
| `motion` (`mks_servo/motion.py`) | 30 | Both SERVO42C steppers: homing, soft limits, pick-and-place |
| `gripper_link` (`mks_servo/gripper_link.py`) | 30 | 100 Hz force loop for the gripper (Pico 2 over UART) |
| `vision` (`python/pointing.py --arm`) | 10 | Camera, hand tracking, classifier, operator console on port 8080 |

## Run it on the Pi

```sh
cd ~/mks_servo
./start_robot.sh                       # real robot; dashboard on http://<pi-ip>:8090
./start_robot.sh --sim                 # fake Pico, motors and vision
./start_robot.sh --sim --real-vision   # real camera app, fake arm
./stop_robot.sh
```

From a Windows laptop, `sync_to_pi.bat` copies both code trees to the Pi.

## Vision (PickVision)

- **Hand pointing:** hold your index finger over a box for 1 s to pick it ("from"), then point at the box it goes to ("to").
- **Object classifier:** learns egg / cup / block from ~5 examples each; flags anything else as unknown.
- **Operator console:** web page on port 8080 (QNX OpenCV has no GUI).
- With `--arm`, each move goes to `motion` as a PICK; `motion` picks the grip force from the label on the QNX side.

Vision on its own, on the Pi (`~/pickvision/run_pi.sh`, stop with `run_pi.sh stop`) or on a laptop:

```
python -m venv python\.venv
python\.venv\Scripts\pip install -r python\requirements.txt
python\.venv\Scripts\python python\pointing.py --web 8080
```

## Folders

| Folder | What's in it |
|---|---|
| `mks_servo/` | Arm side: stepper driver, `motion`, `gripper_link`, `supervisor`, test tools, JSON config, dashboard |
| `pico_gripper/` | Pico 2 firmware: FSR stream + servo, freezes the servo if QNX goes quiet |
| `docs/` | `GRIPPER.md`, `MOTION.md`, `SUPERVISOR.md`: wiring, protocols, test results |
| `python/` | Vision app: `pointing.py` (main loop), `classifier.py`, `handtrack_tflite.py`, `qnx_camera.py`, `web_ui.py`, `arm_link.py` |
| `qnx/` | `pv_cam.c`: small C bridge to the QNX camera API (OpenCV can't open cameras on QNX) |
| `models/` | Hand tracking models (palm + landmarks, from the QNX AI workshop / MediaPipe) |
| `config/` | Vision config: box positions, taught examples |
| `cloud/` | Optional history dashboard (Vultr + Tiger Data). The robot never depends on it |
| `design/` | Console design versions and a mock server |
| `src/`, `CMakeLists.txt` | Older C++ vision version (backup) |

The hand tracker is a Python port of the tracker in [QNX AI workshop](https://github.com/qnx/QNX-AI-workshop). QNX SDK headers aren't included; they come with the QNX SDK.

More detail: `GAMEPLAN.md`, `CHAT_SUMMARY.md`, and the files in `docs/`.
