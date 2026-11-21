# Motion: the pick-and-place task

`mks_servo/motion.py` owns both SERVO42C ports. It takes a `PICK` from vision and does the whole move:

`IDLE → MOVE_TO_PICK → LOWER → GRIP → LIFT → MOVE_TO_PLACE → LOWER → RELEASE → HOME → IDLE`, and `FAULT` from any state.

```sh
on -p 30 python3 motion.py          # real motors
python3 motion.py --sim 4           # fake motors (sim_servo.py), 4x speed
python3 arm_cmd.py pick 1 3 egg     # pocket 1 -> pocket 3, egg grip profile
python3 arm_cmd.py watch
```

## Safety rules (one sentence each)

- Pocket positions are fixed, taught joint angles stored in `config/arm.json`. There's no inverse kinematics.
- Every target is checked against the joint's soft limits before anything moves.
- Targets are absolute encoder positions, so errors never build up from one move to the next.
- Both joints move together, with speeds scaled so they arrive at the same time.
- Every move has a time limit and a progress check. A joint that stops moving is a fault. This matters for motor 2, whose V1.0 firmware has no stall detection.
- Any fault means stop and **hold**: the motors stay enabled and the gripper keeps its grip.
- `PAUSE` (the supervisor sends it while vision is down) stops and holds. `RESUME` continues the same move.
- If the object slips while it's being carried, the arm stops and holds (`FAULT`).
- If the grip fails at the pick pocket (empty pocket, or too stiff), the jaws open over that pocket and the arm goes home. That's safe because the object is still resting in its pocket.

## Commands (UDP JSON to 127.0.0.1:5611, or `arm_cmd.py`)

| Command | What it does |
|---|---|
| `PICK {from,to,label}` | Full pick and place. Only accepted when IDLE, homed, the pockets are known, `from` ≠ `to`, and `label` has a grip profile |
| `HOME` | Sets the zero, then goes to `home_pose` |
| `JOG {joint,deg}` | Moves one joint relative to where it is, for teaching |
| `TEACH {pocket}` | Saves the current pose as that pocket in `arm.json` |
| `PAUSE` / `RESUME` | Hold, then carry on |
| `FAULT {reason}` / `STOP` | Stop and hold. Sticky until `RESET` |
| `RESET` (`{"rehome": true}` after an e-stop) | Clears the fault. With rehome it re-initialises the drivers and homes again |

Telemetry and heartbeat: status JSON is sent to UDP 5612 at 10 Hz, including the main-loop jitter.

## Homing

- **base:** `marked_zero`. Before starting motion, park the arm on the zero mark (`homing.marked_pose`).
- **lift:** `marked_zero`, or `hard_stop`, which drives down slowly with Surya's `run_until_blocked` until the shaft is blocked, then backs off 2°.

## Setting up on the real arm

1. Measure each `gear_ratio` (motor degrees per arm degree) and check `dir_bit_positive`. Run `arm_cmd.py jog lift 5`: the lift should go **up**. If it goes down, flip the bit.
2. Set `min_deg` and `max_deg` for each joint to the safe range.
3. Teach the pockets: run `home`, jog until the jaws sit in pocket 1, then `teach 1`. Repeat for 2, 3 and 4.
4. Measure the real speed. If moves time out, change `deg_per_s_per_speed`. The current value of 3.8 is an estimate.
5. Pick each object 10 times and check for drift.

## Tested on the Pi (fake motors + fake Pico)

| Test | Result |
|---|---|
| Home, then pick 1 → 3 egg | `done`. Every step ran in order |
| Same pocket, unknown pocket, unknown object, jog past limit | Rejected without moving |
| PAUSE mid-move, then RESUME | Held, then finished the pick |
| Base motor jams | `FAULT: base is not moving`, held |
| FAULT from supervisor mid-move | Stopped and held. PICK refused until RESET |
| Object slips while carrying | `FAULT: object slipped`, held |
| Empty pocket | `grip failed: NO_OBJECT`, jaws opened, went home |
| `kill -9 gripper_link` while carrying | Motion: `FAULT`, held. Pico froze 105 ms later, still gripping |
| Lift hard-stop homing | Homed, went to home pose |
| Main loop at `on -p 30` | Jitter max ≈ 0.2–1 ms, 0 missed |
