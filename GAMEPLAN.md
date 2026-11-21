# pickvision — gameplan (Hack Western 13, QNX track)

My part: **hand pointing + pocket classifier**.

**Team decision: the final version is Python only.** The same Python code runs on the
laptop and on the team's QNX Pi. The old C++ version (`src/`, `run.bat`, `build.bat`,
`CMakeLists.txt`) is **not used anymore**. It's only kept as a backup and reference.

## Does it match the team plan?

| Team plan | What's built | Status |
|---|---|---|
| Index fingertip (landmark 8) picks the pocket | Yes. Fingertip is averaged over 5 frames | ✅ |
| Confirm after ~1 s dwell | `Selector(dwell_ms=1000)` in `python/logic.py`, for both points | ✅ |
| Placing/shuffling objects mustn't trigger a pick | Only a **pointing hand** (index out, middle + ring curled) selects. Turn it off with `--no-point-check` | ✅ |
| No pinch gesture | None. "Pinch" stays the gripper's word | ✅ |
| Point at the object's box, then at the box it goes to (Surya, Nov 21) | Two points per move. The "to" box must look empty or it refuses. There are 4 boxes (3 tray pockets + 1 extra), and any box can be "from" or "to" | ✅ live-tested Nov 21: cup P4 → P3 sent; "to" box with a cup refused; no-choice timed out |
| Classifier picks grip strength | Object → `config/grip.yml` window → `[pick]` message | ✅ (placeholder numbers) |
| Rules classifier first (colour + shape) | Colour + shape features. It learns its thresholds from ~5 examples per object instead of hand-typed numbers | ✅ (variant) |
| Teachable Machine TFLite model later | Not done. `tflite-runtime` is already on the Pi | ⏳ optional |
| Click pocket positions on a photo | Press `c` (or the web button) and drag a box per pocket. Saved to `config/tray.yml` | ✅ |
| Accuracy test on ~20 photos/object/pocket | No photo-capture or offline-test tool yet | ⏳ Saturday |
| Runs on QNX | Yes, the Python app runs on the team Pi | ✅ |

## Files (all Python)

| File | What's in it |
|---|---|
| `python/pointing.py` | main app: camera loop, drawing, keys / web buttons |
| `python/handtrack_tflite.py` | hand tracker: Python port of the QNX workshop tracker, same 2 `.tflite` models |
| `python/logic.py` | pocket boxes, fingertip smoothing, pointing-shape check, 1 s dwell state machine |
| `python/classifier.py` | empty/egg/cup/block classifier |
| `python/qnx_camera.py` + `qnx/pv_cam.c` | QNX camera (OpenCV can't open cameras on QNX, so a tiny C helper reads camapi) |
| `python/web_ui.py` | web page view + buttons (QNX OpenCV has no windows) |
| `run_python.bat` | start it on the laptop |
| `run_pi.sh` | start/stop it on the Pi |
| `sync_to_pi.bat` | copy the code from the laptop to the Pi and restart it there |

`qnx/pv_cam.c` is C, but it's just the camera helper. All the app logic is Python.

## Run it (laptop)

Double-click `run_python.bat`. The first run sets up its own Python environment
(takes a few minutes). It uses the same hand tracker code and the same 2 `.tflite`
models as the Pi. Only the engine that runs them differs: OpenCV on the laptop,
`tflite-runtime` on the Pi. It picks the engine by itself.

Hold your hand up: you should see a green hand skeleton. Then:

1. **`c`** drags a box around each box, in order (4 boxes: the 3 pockets, then the extra box). Saved automatically.
2. Clear the tray and keep your hand out of view, then press **`b`** to photograph the empty pockets.
3. Put an object in a pocket and press **TAB** until that pocket has the white
   outline. Then press **`1`** egg / **`2`** cup / **`3`** block. Do 5–10 per object,
   moving it a little each time. It saves automatically.
4. Point at the box with the object and hold for 1 s (blue ring), then pull your
   hand away. It identifies the object and says "point where it goes".
5. Point at the box it should go to and hold for 1 s (orange ring), then pull your
   hand away. It checks that box is empty and "sends" the move. The terminal shows
   `[pick] from=1 to=4 obj=egg grip=[80,140]`. You have 10 s to choose the "to" box.

Other keys: `m` shows what the classifier sees (pink = object), `x` wipes samples, `q` quits.
Camera: `run_python.bat --cam 1` for another camera (Windows swaps the numbers after a reboot).

## Run it on the QNX Pi ✅ working

Verified Nov 21 on the team Pi (QNX 8.0, reports **Raspberry Pi 4B**, IP 192.168.8.247):

| Piece | How | Status |
|---|---|---|
| Libraries | `python3-numpy`, `python3-opencv`, `python3-tflite-runtime` from QNX's apk repo (installed) | ✅ |
| Hand tracking | `python/handtrack_tflite.py`, no `mediapipe` needed | ✅ palm 62 ms, landmarks 28 ms |
| Camera | `qnx/pv_cam.c` + `python/qnx_camera.py` | ✅ USB C270 = **unit 4**, 640x480 ~19 fps (unit 1 is a test pattern) |
| Screen | `python/web_ui.py` | ✅ http://192.168.8.247:8080 |
| Whole app | `python/pointing.py` auto-detects QNX: camera unit 4, no mirror, web view | ✅ ~8–9 fps end to end |

- **Update the Pi with new code:** double-click `sync_to_pi.bat` (copies code only, the Pi keeps its own pockets + training).
- **Start by hand:** `ssh qnxuser@192.168.8.247`, then `~/pickvision/run_pi.sh`.
- **Stop:** `~/pickvision/run_pi.sh stop`
- Open **http://192.168.8.247:8080** on a laptop on the same Wi-Fi. The buttons there replace the
  keys. Drag pocket boxes on the picture.

**What I changed on the team Pi:** installed the 3 Python packages above (+ their libraries),
created `~/pickvision/`, and added one SSH key line for this laptop to `~/.ssh/authorized_keys`.

## How a pick flows

```
camera ─▶ hand tracker ─▶ fingertip (smoothed) + pointing shape? ─▶ which pocket?
          (palm + 21 landmarks)                                        │ held 1 s
                                                                       ▼
             wait until hand is OFF the pocket ◀── selected
                         │ (the hand hides the object while pointing)
                         ▼
             classify 5 frames, majority vote ─▶ empty / unknown → refuse
                         │ egg / cup / block
                         ▼
             point at the "to" box, held 1 s, hand away
                         ▼
             is the "to" box empty? ─▶ no / not sure → refuse
                         │ yes
                         ▼
             [pick] from box, to box, object, grip_min, grip_max
                         │ (how it reaches the robot: waiting on the team)
                         ▼
             control task (owns motors + grip sensors)
```

Vision never drives a motor. It sends **one** message per pick. Vision can be slow
or even killed while the control task keeps going.

## Weekend timeline

- **Sat (camera mounted):** run `sync_to_pi.bat`, open the web page, draw the real
  pockets, empty photo, 5–10 samples per object per pocket.
- **Sat:** real-hand pointing test on the Pi camera, shuffle accuracy test. Teachable
  Machine model only if there's time.
- **Sat evening:** test under venue lighting and re-capture `b` and samples there.
  **Record a backup video.**
- **Sun morning:** hands off unless something breaks.

## Learned from the desk test (Nov 21, USB camera)

- Point → 1 s hold → pull away → `[pick] pocket=2 obj=block grip=[300,600]` worked
  3/3, pointing from the side. Cup/block labels followed the objects when shuffled.
- **The camera must see the judge's whole hand, palm included.** The tracker finds the
  palm first, so a fingertip poking in from the edge isn't detected at all.
- **Lighting drift breaks "empty".** Re-press `b` (all pockets empty) right before
  each judge.
- **Wood block on a wood desk is borderline**: it was once read as "empty". Use a
  brightly coloured block.
- Pointing-shape thresholds look fine: real point ≈ index 45–50° bend, others 190–250°;
  flat hand ≈ index 73°, others 40–50°; fist ≈ 245°+ for all.

## Need from the team

- **Interface**: how should `[pick]` reach the control task? (QNX message, socket, or
  a file/pipe.) Once they say, I wire it into `FakeRobot` in `python/pointing.py`.
  It now carries `from` and `to` box numbers, so the arm needs a position for each of the 4 boxes.
- **Grip numbers**: fill in `config/grip.yml` from the pressure tests (raw sensor units).
- **Camera mount**: top-down over the tray, seeing the whole hand. The pockets sit on
  a 145 mm arc, so the boxes won't be in a row. That's fine, `c` handles any layout.
- **Block + cup colours**: bright and not white. The egg and a white cup look alike from above.
- **Cup vs 46 mm jaw gap**: still open. A paper cup rim is usually 70+ mm.

## Known gaps / risks

- Nobody has done point → dwell → classify with a real hand **on the Pi camera** yet
  (the Pi's camera was pointing at cables). It works on the laptop.
- `sync_to_pi.bat` hasn't been tested end to end since the stop fix.
- The camera code is camapi, not the Sensor Framework API itself. Say "camera API" in
  the pitch if asked.
- Two people in view: it follows the biggest hand. The arm is also treated as
  "covering" a pocket, so the robot never classifies through an arm.
