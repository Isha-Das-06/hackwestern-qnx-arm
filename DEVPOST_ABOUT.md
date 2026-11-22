## Inspiration

Pharmaceutical labs and pharmacies handle thousands of fragile items a day: glass vials, ampoules, sample tubes. A robot doing that work has two jobs that can't fail. It has to grip each item with exactly the right force, and it has to stay safe when something goes wrong, because a dropped vial is lost product, a contamination risk, or a person cut by broken glass.

Those are **real-time** problems. A grip correction that arrives 100 ms late is too late. So we asked: what does a pick-and-place robot look like when it's built on a real-time operating system from the start, with safety designed in at every layer?

We built it on **QNX**, the RTOS used in cars and medical devices, and ran everything on a Raspberry Pi with no cloud in the control path. Then we realised the same robot answers a second problem: people with arthritis, tremor or stroke struggle with exactly the same fragile objects, and assistive arms like the Kinova JACO cost US$35,000 or more.

## What it does

- A camera watches a tray of boxes. An operator **points** at a box for one second to choose it, with no controller or keyboard and nothing to touch.
- On-device AI recognises what's in the box. If it isn't sure, it says **Unknown** and refuses to pick it, instead of guessing.
- The operator points at an empty box, and the arm moves the object there. If the target box isn't empty, it refuses that too.
- Force sensors in the gripper's jaws close the grip to the target force for that object, and no harder: firm for a block, gentle for an egg (our stand-in for a glass vial).

## Why an RTOS, and why QNX

On an ordinary operating system, a busy program can delay everything else. On QNX, the most important task always runs first.

- **Deterministic timing.** Grip control runs at a high real-time priority, 100 times a second. We loaded every CPU core on the Pi and measured it: never more than **half a millisecond late, zero missed deadlines**. The exact same code at normal priority was up to **137 ms late** and missed over a hundred deadlines.
- **Process isolation.** Vision, grip control, arm motion and the supervisor are separate QNX processes with their own memory. A crash in one can't corrupt the others.
- **Crash recovery.** A supervisor watches a heartbeat from every process. Kill the AI mid-move, and the arm stops and holds the object, vision is restarted, and the move finishes.

## Safety, layer by layer

We designed for failure first. Every layer has a defined safe state:

1. **Emergency stop:** a hardware button cuts motor power. Its sense wire is normally-closed, so a loose wire also reads as "stop".
2. **Supervisor:** if grip control, motion, or the link to the gripper goes silent, it faults, stops the arm and holds. Only a deliberate reset clears it.
3. **Gripper watchdog:** a small Pico controller drives the gripper, but only QNX makes decisions. If QNX goes quiet for 100 ms, the Pico freezes the gripper in place instead of letting go.
4. **Force limits:** if either jaw goes over the object's maximum force, the gripper backs off. If the force drops while carrying, it flags a slip and stops.
5. **Motion limits:** soft joint limits, stall detection, and every bad request refused before anything moves.
6. **AI limits:** unknown objects and full target boxes are refused, not guessed at.

## How we built it

- **AI on QNX:** hand tracking runs on **TensorFlow Lite through QNX's ported `tflite_runtime`**, using the QNX AI workshop hand-tracking models. We ported QNX's C++ sample to Python. Objects are recognised by a small classifier you teach on the spot with about five examples.
- **Camera:** OpenCV can't open cameras on QNX, so we wrote a C program on QNX's camera API.
- **Hardware:** a 3D-printed two-joint arm, two closed-loop stepper motors over UART, and a servo gripper with force sensors in both jaws, read by a Raspberry Pi Pico that talks to the Pi over UART.
- **Operator pages:** two web pages served by the Pi. One shows the camera and what the robot thinks is in each box; the other shows the arm, live force readings, and live timing for every process.
- **Audit trail:** every move and a health sample go to a **Vultr** server and into **Tiger Data** (see below). The robot never waits on the cloud; unplug the network and it keeps working.

## Beyond the robot

**Who it helps.** More than 1.5 million Canadians live with a disability that affects how they use their hands, from causes such as arthritis, tremor or stroke. The things they struggle with most are the fragile ones, and an assistive arm like the Kinova JACO costs US$35,000 or more. Our arm is controlled by pointing, so there's nothing to grip or press. It's built from a Raspberry Pi, a Pico and 3D-printed parts. The safety work from the industrial side carries straight over: a gripper that never lets go on a crash, an AI that refuses rather than guesses, and a hardware e-stop.

**The hardware, and what we'd fabricate next.** A working, 3D-printed two-joint arm with two closed-loop stepper motors, a servo gripper with force sensors in both jaws, a Pico handling the sensors, and a fail-safe e-stop circuit. Right now the electronics are hand-soldered on a protoboard. The next version is a custom PCB that combines the Pico, the force-sensor circuit, the UART links to the motors and the e-stop input on one board, so it's smaller, sturdier and easier to build again.

**History and audit trail on Tiger Data.** Every pick, and a health sample every 10 seconds (frame rate, frame timing, on-time percentage, CPU use), go into **TimescaleDB on Tiger Data**. Moves and health samples are stored in hypertables, a 1-minute continuous aggregate powers the history charts without re-scanning raw rows, and compression keeps a long history small. For a pharma line, that's an audit trail: what was moved, when, where to, and whether the robot was running on time.

**Running the dashboard on Vultr.** A **Vultr** cloud server runs our history service and dashboard. The Pi sends each move and health sample to it, the server writes them into Tiger Data, and anyone on the team can open the dashboard from anywhere. It's off the robot's critical path on purpose: if the network drops, the robot keeps working and only the history pauses.

## Challenges we ran into

- **The camera on QNX.** OpenCV couldn't open it, so we wrote our own camera program.
- **Two motors, two firmwares.** One motor driver ignored the standard move command, so we run it at a set speed and stop it ourselves at the target.
- **A priority surprise.** Processes started by the supervisor inherited its high priority, so the vision program briefly outranked grip control. That's exactly the kind of bug an RTOS makes you think about. Now each process starts at its own priority.
- **Lighting.** "Is this box empty?" depends on a reference photo, so a shadow can make empty boxes look full. We retake the photo before each demo.

## Accomplishments that we're proud of

- A measured real-time result: under half a millisecond versus 137 ms, from the same code.
- You can crash the AI while the arm carries an object, and nothing gets dropped. (We proved this with simulated motors first.)
- Six independent safety layers, each with a defined safe state.

## What we learned

Real-time doesn't mean fast; it means **never late**. The camera can take its time, but the grip can't. And on a robot, how it fails matters as much as how it works.

## What's next for the project

- Calibrate the force sensors to real units, and grip real vials and tubes.
- A custom PCB joining the Pico, force-sensor circuit and motor connectors.
- Move to **QNX OS for Safety**, which is certified for medical devices (IEC 62304), and test with people who struggle to grip.
