# pickvision — chat summary (Hack Western 13, Nov 20–22 2026)

Short, readable record of what was built and decided while working with Claude.
For full details see `GAMEPLAN.md`. No passwords in this file.

## The project
Team robot for the **QNX track** ("embedded system on QNX that uses AI").
A tabletop arm picks objects from a tray. **My part = the vision:**
- **Hand pointing:** index fingertip (hand landmark 8), held ~1 s on a box.
- **Object classifier:** egg / cup / block / empty per box.
- The classifier result picks the **grip strength range** (`config/grip.yml`).

## Decisions
| Decision | Why |
|---|---|
| "Pinch" = gripper strength, **not** a hand gesture | Team clarified |
| Select by **1 s dwell** + a real **pointing shape** (index out, middle + ring curled) | Placing objects by hand mustn't trigger picks |
| **Python only** is the final version (old C++ in `src/` = backup) | Team decision |
| Rules-style classifier first (colour + shape, learns from ~5 examples/object); Teachable Machine optional | Simple, fast, works on QNX |
| **Two points per move** (Surya, Nov 21): point at the object's box, then at the box it goes to | Robot needs a "to" place; the "to" box must look empty |
| 4 boxes: 3 tray pockets + 1 extra; any box can be "from" or "to" | Flexible |

## How a move works
1. Point at the box with the object, hold 1 s (blue ring), pull hand away → it identifies the object.
2. "point where it goes" → point at the target box, hold 1 s (orange ring), pull away → it checks that box is empty.
3. Sends `[pick] from=4 to=3 obj=cup grip=[150,260]`.
Refuses if: "from" box empty / unknown object / "to" box not empty / no target chosen in 10 s.

## What runs where
- **Laptop:** `run_python.bat` (window + keys: `c` draw boxes, `b` empty photo, TAB + `1/2/3` teach egg/cup/block, `m` mask, `x` clear, `q` quit).
- **QNX Pi** (QNX 8.0, `qnxuser@192.168.8.247`): same Python code. Web page at `http://192.168.8.247:8080` replaces the window.
  - Update: `sync_to_pi.bat`. Start: `~/pickvision/run_pi.sh`. Stop: `~/pickvision/run_pi.sh stop`.
  - Installed from QNX's apk repo: `python3-numpy`, `python3-opencv`, `python3-tflite-runtime`.
  - Hand tracking = Python port of the QNX AI workshop tracker (2 TFLite models): palm 62 ms + landmarks 28 ms.
  - Camera: OpenCV can't open cameras on QNX → small C helper `qnx/pv_cam.c` (QNX camera API). USB camera = unit 4.
  - Whole app ≈ 8–9 fps on the Pi.

## Tested
- Laptop desk test: point → 1 s → pick worked 3/3; cup/block labels followed when shuffled.
- **Two-point move live-tested Nov 21:** cup P4 → P3 sent; "to" box with a cup refused; no target → timed out.
- Pi: full app runs (camera + tracker + web page); two-point version copied and test-run OK.
- Not yet: real-hand pointing on the **Pi camera** (needs the mount).

## Lessons from testing
- Camera must see the **whole hand incl. palm** (tracker finds the palm first).
- Lighting changes break "empty" → press `b` again right before each judge.
- Wood block on wood desk is borderline → use a brightly coloured block.
- Pointing limits loosened after live test (index bend < 90°, middle/ring > 70°) + 0.3 s slip allowance.
- Windows swaps camera numbers after reboot (USB cam was 1, then 0).
- Windows SSH to the Pi needs `-c aes128-ctr -o MACs=hmac-sha2-256`. QNX has no `pkill` (use `run_pi.sh stop`).

## Still open (needs the team)
- **How `[pick]` reaches the robot's control task** (QNX message / socket / pipe). It carries `from`, `to`, object, grip.
- Arm needs a saved position for each of the 4 boxes.
- Real grip numbers in `config/grip.yml` (placeholders now: egg 80–140, cup 150–260, block 300–600).
- Camera mount over the tray; then on the Pi web page: draw 4 boxes, empty photo, teach real egg/cup/block.
- Shuffle accuracy test, backup video.

## Prizes (from the Devpost page)
- Main: **Best Use of QNX** ($1,000 / 2× $250). Must run on QNX + use a QNX open-source AI module (we use QNX TFLite runtime + workshop models).
- Also enter: **Best Hardware Prototype (PCBWay)**, **Best Health Hack (Sun Life)** (pitch: grip help for people who can't grip well), **Most Adventurous**.
- Optional: **Tiger Data + Vultr** as a cloud history/timing dashboard (robot stays real-time and offline-capable on the Pi).
- No limit on sponsor tracks. Select them on both the live site and Devpost (must match). Sponsors shortlist; general judging (overall 1st–3rd) is for everyone.
- Rules: **no slide decks**, 3 min demo + 1 min Q&A per judge. Devpost deadline **Sun 9:00 AM**, demo fair **Sun 12–1 PM**.
- Judging criteria include **Design**, so the console page was rebuilt (see below).

## Operator console (built Nov 21, second chat)
Open `http://192.168.8.247:8080` (Pi) or `http://localhost:8080` (laptop: `python\.venv\Scripts\python python\pointing.py --web 8080`).
- **Final design = v3** (dark). Files: `python/web/` (same as `design/console_v3/`). Older v2 kept in `design/console_v2/`.
- **Mock to preview designs without a camera:** double-click `design\run_mock.bat` → `http://localhost:8090`
  (v3: `python design/mock_server.py console_v3 8091 --wide`).
- **Live screen:** big status bar (instruction, hold bar, countdown, red errors with the fix), camera with box labels,
  Boxes list, **Real-time health** (reaction time, % frames under 200 ms, vision CPU, time-per-frame chart; details folded),
  Recent moves (fills the space under the camera) or a moves strip, "All moves" table.
- **Sounds** (speaker icon or S), **presentation mode** (F, full screen), shortcuts list (?).
- **Set up** = 3-step checklist: mark boxes (draw all 4 or **redraw one**), empty-tray photo, teach (put ONE object in any box → Teach; it finds the box; refuses if several boxes are full).
- "Robot arm: simulated" label until the real control task is wired.
- UX research + plan: `design/UX_GAMEPLAN.md`. Skill used: Anthropic `frontend-design` (installed in `~/.claude/skills`).
- Backend: `web_ui.py` serves `python/web/`, `/state` JSON, `/stream` clean MJPEG, `/cmd` (cancel, redraw, teach). `sync_to_pi.bat` copies `python/web` too.

## Pi notes from this chat
- Laptop training (5 cup / 5 block) copied to the Pi; backups in `~/pickvision/config_backup/`.
- USB camera on QNX supports at most **800×600** (no 1280×720); asking for other sizes still gave 640×480.
  Switching sizes back-to-back **jammed the camera** → fixed by rebooting the Pi. Don't experiment with sizes.
- `run_pi.sh stop` kills any command mentioning `python/pointing.py`, including your own ssh command.
- After a reboot the Pi clock may read 1970 until it syncs; the page now shows times using the laptop's clock.
- On the Pi: ~10 fps, 100% frames under 200 ms, vision uses ~64% CPU.
