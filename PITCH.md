# Demo pitch: 3 minutes + 1 minute Q&A (no slides)

**Roles**
- **Talker (one person):** says everything below and keeps eye contact with the judge.
- **Fixer (one person):** stands at the laptop and dashboard. If something breaks, the Fixer quietly switches to the backup, and the Talker keeps talking.

**One line we want every judge to repeat:**
> "A pharma-style pick-and-place robot on QNX that never drops what it's holding, even when its own AI crashes."

---

## The script (about 3:00)

**0:00–0:25 · Hook (industry problem → RTOS)**
> "Pharma labs and pharmacies move thousands of fragile things a day: glass vials, ampoules, sample tubes. A robot doing that can't be late and can't fail unsafely. A grip correction that's 100 ms late means a broken vial. So we built a pick-and-place arm on QNX, a real-time OS, with safety designed in at every layer. It all runs on this Raspberry Pi, with no cloud in the control loop."

**0:25–1:05 · Live pick (the judge does it)**
- *"Point at the egg's box and hold for a second."* The page shows "Egg". (Say once: "The egg is our stand-in for a glass vial.")
- *"Now point at an empty box."* The arm picks up the egg and carries it over.
- While it moves, point at the force bars: *"Force sensors in the jaws. It closes to the egg's target force and stops, every 10 ms, on QNX."*
- Optional, in one line: point at a box with something unknown in it. *"It isn't sure what that is, so it refuses. It never guesses."*

**1:05–1:45 · RTOS proof (the QNX centrepiece)**
- Fixer runs `./hog.sh 6 30` (it loads every CPU core).
> "We've just maxed out every core on the Pi. The camera slows down, and that's fine. The grip loop: still under a millisecond late, zero missed deadlines. Same code at normal priority was 137 ms late. That's the difference between an RTOS and a normal OS: the critical task always wins."

**1:45–2:25 · Break it (safety)**
- Start a second pick. While the arm is carrying: *"Go ahead, kill the AI."* The Fixer types `kill -9 <pid>`, or the judge does it.
> "The AI just crashed. Each part is its own isolated QNX process, so nothing else is affected. The arm stops and holds, the supervisor restarts vision, and the move finishes."
- Then press the e-stop: *"Hardware e-stop: power is cut. The wire is normally-closed, so even a loose wire means stop. Software won't move again until a deliberate reset."*

**2:25–2:45 · Bridge to healthcare**
> "And the same problem shows up at home. People with arthritis, tremor or stroke struggle with exactly these fragile objects. Assistive arms cost over 35,000 US dollars. This one is controlled by pointing, with nothing to grip, on hardware that costs a fraction of that."

**2:45–3:00 · Close (pick the line for the judge in front of you)**
- **QNX judge / general:** "Real-time grip control, process isolation, crash recovery and on-device AI through QNX's TensorFlow Lite. A cannot-fail system, and you just watched it not fail."
- **Health judge (Sun Life):** "Industrial safety, brought to assistive care: e-stop, a gripper that never lets go on a crash, and an AI that refuses rather than guesses."
- **Hardware judge (PCBWay):** "Right now it's hand-soldered on a protoboard. Next version: a custom PCB joining the Pico, the force-sensor circuit and the motor connectors on one board."
- **Tiger Data judge:** open the history dashboard. "Every move and a health sample every 10 seconds go into TimescaleDB hypertables on Tiger Data. A 1-minute continuous aggregate draws these charts, and compression keeps the history small. In pharma terms, it's an audit trail."
- **Vultr judge:** "This dashboard and our history service run on a Vultr server. The Pi sends to it, and it writes to Tiger Data. It's deliberately off the critical path: pull the network and the robot keeps working."

**Sponsor judges first:** if the judge is from a sponsor, give their track 20–30 seconds of the 3 minutes, not just the closing line. Shorten the RTOS part a little to make room.

**Keep it honest:** it's a prototype. If asked, say plainly: "We use an egg, not real vials, and standard QNX 8.0, not the safety-certified version."

---

**Between judges:** run `./stop_robot.sh` then `./start_robot.sh`, put the egg back in its box, and retake the empty-tray photo if the light has changed.

---

## If something breaks

| Problem | What to do |
|---|---|
| Arm or motors won't move | Fixer runs `./start_robot.sh --sim --real-vision`: real camera and pointing, simulated arm, same dashboard. Say: "We'll show you the arm logic in simulation; here's the video of the real arm." |
| Camera frozen | Unplug and replug the webcam's USB, then restart the app. Meanwhile, play the backup video. |
| Pointing is unreliable for this judge | The Talker does the pointing. Make sure the whole hand, palm included, is in view. |
| Boxes show the wrong labels | Retake the empty-tray photo (lighting changed). |

**Have ready on the table:** a 60–90 second backup video of a real pick (film it as soon as the arm works), the dashboard open on the laptop, spare USB cable, and a printed QR code linking to the Devpost page.

**Rule:** only demo what has worked 3 times in a row that morning. Don't change code after that.

---

## Q&A: likely questions

- **"Which QNX AI module did you use?"** TensorFlow Lite, through QNX's ported `tflite_runtime`, running the hand-tracking models from the QNX AI workshop. We ported the C++ sample to Python.
- **"Why QNX and not Linux?"** Hard priorities and process isolation. Under full CPU load the grip loop stayed under a millisecond late; at normal priority it was 137 ms late. And when one process crashes, the others carry on.
- **"Would this really work in a pharma line?"** Not as-is: it's a hackathon prototype. The architecture is what transfers: an RTOS, isolated processes, a supervisor, hardware e-stop, force-limited grip, and an audit trail. The next steps would be real vials, calibrated force, and QNX OS for Safety.
- **"What's a microkernel / why does isolation matter?"** In QNX, drivers and apps run as separate processes with their own memory, not inside the kernel. So when our AI crashed, it couldn't take the grip control or the OS down with it.
- **"Is this safety-certified?"** No. It runs standard QNX 8.0. QNX does make a certified version for medical devices, and our design (e-stop, fail-safe wiring, hold-on-crash) follows the same ideas.
- **"What breaks first?"** Lighting: the empty-box check depends on a reference photo, so we retake it before each demo. Second, the force sensors read raw values, not newtons; calibrating them is next.
- **"What did you build this weekend?"** All of it, at the hackathon: the vision and classifier, the grip control, the motion code, the supervisor and the dashboards. We started from the QNX workshop hand tracker and a teammate's motor driver. (Edit this to be exactly true for your team.)
- **"Did you use AI tools?"** Answer honestly. Judges value that.
- **"How much would it cost?"** Add up your real parts list before the demo and say the number.

---

## Before judging starts (checklist)

1. Pi on, robot started with `./start_robot.sh`, and the dashboard open at `http://192.168.8.247:8090`.
2. Camera page open at `http://192.168.8.247:8080`. Retake the empty-tray photo.
3. Egg, cup and block each taught (5 of 5).
4. Run one full pick and one crash test. Both work? Freeze the code.
5. Backup video on the laptop, ready to play.
6. Phone hotspot ready in case the venue Wi-Fi drops (the laptop needs to reach the Pi).
