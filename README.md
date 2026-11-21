# hackwestern-qnx-arm — vision (PickVision)

Vision side of the Hack Western 13 pick-and-place robot (QNX track). Runs on QNX 8 on a Raspberry Pi 4.

- **Hand pointing:** hold your index finger over a box for 1 s to pick it ("from"), then point at the box it goes to ("to").
- **Object classifier:** learns egg / cup / block from ~5 examples each; flags anything else as unknown.
- **Grip:** the object picks the grip strength range from `config/grip.yml`.
- **Operator console:** web page on port 8080 (QNX OpenCV has no GUI).

Each move prints `[pick] from=N to=M obj=X grip=[lo,hi]`. Not wired to the arm's control task yet.

## Run it

**On the QNX Pi** (code lives in `~/pickvision`):

```sh
~/pickvision/run_pi.sh        # start, then open http://<pi-ip>:8080
~/pickvision/run_pi.sh stop   # stop
```

From a Windows laptop, `sync_to_pi.bat` copies the code to the Pi and restarts it.

**On a laptop:**

```
python -m venv python\.venv
python\.venv\Scripts\pip install -r python\requirements.txt
python\.venv\Scripts\python python\pointing.py --web 8080
```

## Folders

| Folder | What's in it |
|---|---|
| `python/` | The app: `pointing.py` (main loop), `classifier.py`, `handtrack_tflite.py`, `qnx_camera.py`, `web_ui.py`, `web/` (console page) |
| `qnx/` | `pv_cam.c`: small C bridge to the QNX camera API (OpenCV can't open cameras on QNX) |
| `models/` | Hand tracking models (palm + landmarks, from the QNX AI workshop / MediaPipe) |
| `config/` | Box positions, taught examples, grip ranges |
| `cloud/` | Optional history dashboard: Vultr server + Tiger Data (TimescaleDB). The robot never depends on it. See `cloud/README.md` |
| `design/` | Console design versions and a mock server to preview the page without a camera |
| `src/`, `CMakeLists.txt` | Older C++ version (backup) |

The hand tracker is a Python port of the tracker in [QNX AI workshop](https://github.com/qnx/QNX-AI-workshop). QNX SDK headers aren't included; they come with the QNX SDK.

More detail: `GAMEPLAN.md`, `CHAT_SUMMARY.md`.
