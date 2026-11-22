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

On an ordinary operating system, a busy program can delay everything else. QNX 8's scheduler is priority-based and preemptive: the highest-priority ready thread runs, and a lower-priority thread cannot push it aside. We run the stock QNX Everywhere image on the Pi. Each job is its own process, started with `on -p` so the priority is explicit.

- **Deterministic timing.** Grip control is priority 30, with a hard deadline every 10 ms (100 Hz). Arm motion is also priority 30 (50 Hz). The supervisor is priority 40 and reads the safety pins at 100 Hz. Vision, which can afford to be late, is priority 10. We loaded all four cores with six busy loops at normal priority. The grip loop's worst lateness was **0.49 ms, with zero missed deadlines**. Motion stayed within about 1 ms. The same grip code, started at priority 10 under the same load, was up to **137 ms late** and missed **124** deadlines.
- **Spatial isolation.** QNX is a microkernel, so a crash stays inside one process. Vision, grip control, arm motion and the supervisor each have their own memory. The UART drivers (`devc-serpl011` on UART3, UART4 and UART5) and the GPIO driver are processes of their own. Vision cannot corrupt the grip loop or the motor drivers by crashing.
- **Crash recovery.** Grip control heartbeats at 20 Hz, motion at 10 Hz, vision at 5 Hz. Kill the vision process mid-move and the supervisor, still at priority 40, pauses motion in place: the motors stay enabled and the grip holds. It restarts vision, then resumes the same move. A vision crash is never a fault.

## Safety, layer by layer

We designed for failure first. Every layer has a defined safe state:

1. **Emergency stop:** a hardware button cuts motor power. Its sense wire is normally-closed, so a loose wire also reads as "stop".
2. **Supervisor:** priority 40. If grip control or motion dies or goes silent, if the force readings go stale, or if motion reports its own fault (blocked, stall, timeout, slip), it latches a FAULT, tells the arm to stop and hold, and lights the fault LED. If the motion process itself is dead, the supervisor opens the motor ports and sends the hold command on the UART. Only a deliberate reset clears a fault.
3. **Process-owned outputs.** Actuator power is a 100% PWM the supervisor holds on GPIO18. The servo pulse is a hardware PWM grip control holds on GPIO19. Both go through QNX's GPIO driver, so `kill -9` on that process stops the pulses: supervisor death drops actuator power. The Pico only streams the two force sensors. If those frames stop, the grip process holds the last angle and the supervisor faults. Every close, back-off and slip check is a decision inside the priority-30 loop.
4. **Force limits:** if either jaw goes over the object's maximum force, the gripper backs off. If the force drops while carrying, it flags a slip and stops.
5. **Motion limits:** soft joint limits, stall detection, and every bad request refused before anything moves.
6. **AI limits:** unknown objects and full target boxes are refused, not guessed at.

## How we built it

- **AI on QNX:** hand tracking runs on **TensorFlow Lite through QNX's ported `tflite_runtime`** (the QNX 8 aarch64 port on oss.qnx.com), using the QNX AI workshop hand-tracking models. We ported QNX's C++ sample to Python and run that process at priority 10, so inference cannot preempt the grip loop. Objects are recognised by a small classifier you teach on the spot with about five examples.
- **Camera:** OpenCV can't open cameras on QNX. A small C process, `pv_cam`, opens the camera with QNX camapi (the same API as the AI workshop) and streams frames to Python on a pipe. Python keeps only the newest frame.
- **Hardware:** a 3D-printed two-joint arm and two closed-loop steppers on QNX serial drivers (`devc-serpl011`, UART3 for the lift, UART5 for the base). Force sensors in both jaws are read by a Raspberry Pi Pico and streamed over UART4. The servo is a hardware PWM from the grip process, so the jaw moves only when that QNX process commands it.
- **Operator pages:** two web pages served by the Pi. One shows the camera and what the robot thinks is in each box; the other shows the arm, live force readings, and live timing for every process.
- **Audit trail:** every move, a health sample every 10 seconds, and live gripper force go to a **Vultr** server and into **Tiger Data**. The dashboard is [http://66.42.92.71/](http://66.42.92.71/). The robot never waits on the cloud; unplug the network and it keeps working.

## Beyond the robot

**Who it helps.** More than 1.5 million Canadians live with a disability that affects how they use their hands, from causes such as arthritis, tremor or stroke. The things they struggle with most are the fragile ones, and an assistive arm like the Kinova JACO costs US$35,000 or more. Our arm is controlled by pointing, so there's nothing to grip or press. It's built from a Raspberry Pi, a Pico and 3D-printed parts. The safety work from the industrial side carries straight over: a gripper that never lets go on a crash, an AI that refuses rather than guesses, and a hardware e-stop.

**The hardware, and what we'd fabricate next.** A working, 3D-printed two-joint arm with two closed-loop stepper motors, a servo gripper with force sensors in both jaws, a Pico handling the sensors, and a fail-safe e-stop circuit. Right now the electronics are hand-soldered on a protoboard. The next version is a custom PCB that combines the Pico, the force-sensor circuit, the UART links to the motors and the e-stop input on one board, so it's smaller, sturdier and easier to build again.

**History and audit trail on Tiger Data.** Every pick, a health sample every 10 seconds (frame rate, frame timing, on-time percentage, CPU use), and the gripper's force readings go into **TimescaleDB on Tiger Data**. Moves and health samples are stored in hypertables, a 1-minute continuous aggregate powers the history charts without re-scanning raw rows, and compression keeps a long history small. For a pharma line, that's an audit trail: what was moved, when, where to, and whether the robot was running on time. The live dashboard is [http://66.42.92.71/](http://66.42.92.71/).

**Running the dashboard on Vultr.** A **Vultr** cloud server runs that page and writes into Tiger Data. Open [http://66.42.92.71/](http://66.42.92.71/). Move history refreshes every 10 seconds: how many picks finished, reaction time, frames under the 200 ms budget, and the latest moves. The gripper chart refreshes every second for the last 2 minutes: both jaw sensors, the target force, the max, the jaw angle, and whether the grip is holding, at about 10 samples a second. It's off the robot's critical path on purpose: if the network drops, the robot keeps working and only the history pauses.

## Challenges we ran into

- **The camera on QNX.** OpenCV couldn't open it. QNX's camapi could, so `pv_cam` is its own process and Python never talks to the camera driver directly.
- **Two motors, two firmwares.** One motor driver ignored the standard move command, so the motion process runs it at a set speed on the QNX serial driver and stops it from the pulse count.
- **A priority surprise.** A child of the supervisor inherited priority 40, so vision briefly outranked grip control at 30. On QNX, priority is inherited unless you set it. We now start every process with `on -p`: supervisor 40, grip and motion 30, vision 10.
- **Lighting.** "Is this box empty?" depends on a reference photo, so a shadow can make empty boxes look full. We retake the photo before each demo.

## Accomplishments that we're proud of

- A measured real-time result: **0.49 ms** late at priority 30 versus **137 ms** and 124 missed deadlines at priority 10, from the same grip loop, with six CPU hogs running.
- You can crash the AI while the arm carries an object, and nothing gets dropped. (We proved this with simulated motors first.)
- Six independent safety layers, each with a defined safe state.

## What we learned

Real-time doesn't mean fast; it means **never late**. The camera can take its time, but the grip can't. And on a robot, how it fails matters as much as how it works.

## What's next for the project

- Calibrate the force sensors to real units, and grip real vials and tubes.
- A custom PCB joining the Pico, force-sensor circuit and motor connectors.
- Move to **QNX OS for Safety**, which is certified for medical devices (IEC 62304), and test with people who struggle to grip.
