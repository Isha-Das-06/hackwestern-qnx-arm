# Gripper: Pico 2 firmware + QNX force loop

**QNX makes every grip decision. The Pico is a dumb I/O board. If QNX goes
silent, the hardware holds where it is.**

## Wiring (pins chosen for this build)

| Signal | Pico 2 | Raspberry Pi 4 |
|---|---|---|
| FSR jaw 1 | GP26 / ADC0 (3V3 → FSR → GP26 → 10 kΩ → GND) | |
| FSR jaw 2 | GP27 / ADC1 (same divider) | |
| Servo signal | GP16 | |
| Servo power | none: use a separate 5–6 V supply (through the e-stop relay), with grounds joined | |
| Pico TX → Pi RX | GP0 (pin 1) | GPIO9, pin 21 (UART4 RX) |
| Pico RX ← Pi TX | GP1 (pin 2) | GPIO8, pin 24 (UART4 TX) |
| Ground | any GND (for example pin 3) | GND pin 25 |

- Both sides use 3.3 V logic, so the wires connect directly with no level shifter.
- **Power everything down before you connect UART or ground wires.** Hot-plugging them once reset the Pi.
- GPIO8 and GPIO9 are also SPI0 pins. Nothing on this robot uses SPI0, so `uart_setup.sh` switches them to UART4 (alt 4).

## Flashing the Pico 2

1. In Arduino IDE, add the board URL
   `https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json`,
   then install **Raspberry Pi Pico/RP2040/RP2350**.
2. Choose the board **Raspberry Pi Pico 2**.
3. Open `pico_gripper/pico_gripper.ino` and upload it. Hold BOOTSEL while plugging in the USB the first time.
4. Before the jaws go on, set `ANGLE_MIN` and `ANGLE_MAX` in the `.ino` to the real jaw travel. This is the hard clamp.

Status LED: solid means QNX is in control. Blinking means it's waiting for QNX, or it has frozen because the link was lost.

## Frames

- **Pico → Pi** (10 bytes, 200 Hz): `AA 55 fsr1_lo fsr1_hi fsr2_lo fsr2_hi angle flags seq xor`
  - FSR values are 12-bit (0–4095), little-endian, and each one is the average of 8 reads.
  - flags: bit 0 = link-loss freeze active; bit 1 = servo not attached yet (no command has arrived since boot).
- **Pi → Pico** (6 bytes, 100 Hz): `AA 56 angle flags seq xor`. flags bit 0 = hold.
- `xor` is the XOR of all bytes before it.

## Pi side (`mks_servo/`)

| File | What it is |
|---|---|
| `gripper_link.py` | The 100 Hz force loop on QNX. Run it with `on -p 30`. |
| `grip_cmd.py` | Sends `open`, `grip egg`, `hold`, `relax`, `status` or `watch` to the loop |
| `fake_pico.py` | Pretends to be the Pico on a pseudo-terminal, for testing without hardware |
| `config/gripper.json` | Port, angles, step sizes, timeouts, UDP ports |
| `config/grip_profiles.json` | Force `target` and `max` for each object. **These are placeholders: tune them, egg first** |

Each 10 ms cycle does the following:
1. Read the newest FSR frame.
2. If either jaw is above `max`, back off 3° at once. While closing, it then tries again at ¼ speed; after 3 back-offs it gives up, holds, and reports `OVER_FORCE`.
3. When `GRIP`: close 0.5° per cycle until the average force reaches `target`, then go to `GRIPPED` and hold. If the jaws close fully without reaching target, go to `NO_OBJECT`.
4. When `GRIPPED` (and it really reached target): if force falls below 50% of target, set `slip` (motion decides whether to re-grip or abort).
5. If no frame has arrived for 50 ms, go to `STALE` and hold the angle.

Commands are one JSON object per UDP packet to `127.0.0.1:5601`, for example `{"cmd":"GRIP","object":"egg"}`. The reply is the status JSON. That same status goes to UDP `127.0.0.1:5602` at 20 Hz, which acts as the heartbeat and telemetry for the supervisor and dashboard. It includes loop jitter, worst case and missed deadlines.

### Running it

```sh
cd ~/mks_servo
su -c "sh uart_setup.sh"                 # until it's in post_startup.sh
on -p 30 python3 gripper_link.py &       # real Pico on /dev/ser4
python3 grip_cmd.py watch
```

To test without a Pico:
```sh
python3 fake_pico.py &                    # prints /dev/ttypN
on -p 30 python3 gripper_link.py --port $(cat /tmp/fake_pico_port) &
python3 grip_cmd.py grip egg
```

### Start UARTs at boot (needs root, once)

```sh
su
echo 'sh /data/home/qnxuser/mks_servo/uart_setup.sh' >> /usr/etc/startup/post_startup.sh
```
Then reboot and check with `ls /dev/ser*`. You should see `ser3`, `ser4` and `ser5`.

## Tested on the Pi (with fake_pico, no real Pico yet)

| Test | Result |
|---|---|
| GRIP egg (soft object) | Closed at 50°/s and stopped at 615 counts (target 600), then held |
| Stiffer object | Stopped at 815 counts, below the 900 max |
| Too stiff (1° of servo travel jumps past max) | Backed off 3 times, then `OVER_FORCE`, holding open. Safe, but not a grip |
| Object slips out | `slip=True` |
| Nothing in the jaws | Closed fully, then `NO_OBJECT` |
| `kill -9 gripper_link` while gripping | The fake Pico froze **100 ms** after the last command |
| 6 busy-loop CPU hogs, gripper_link at `on -p 30` | Jitter max **0.49 ms**, **0 missed** deadlines |
| Same hogs, gripper_link at normal priority 10 | Jitter max **137 ms**, **124 missed**. This is the demo contrast |

Tuning tip: the servo only moves in whole degrees. If the real egg goes to
`OVER_FORCE`, widen the gap between `target` and `max` in `grip_profiles.json`.

## Other change

`Servo42C.safe_stop()` now stops and **keeps holding** instead of releasing the shaft, because an arm must never drop its load on a fault. `release()` is the explicit way to free the shaft. The originals are backed up on the Pi in `~/mks_servo/backup_before_gripper/`.

## Not done yet

- The real Pico hasn't been flashed or tested. This firmware hasn't been compiled here, since there's no Arduino toolchain on this laptop.
- `/dev/ser4` hasn't been brought up yet, because that needs root.
- Calibrating FSR counts against real force, and tuning the egg profile.
- `motion` (homing, pocket table, coordinated moves), `supervisor`, and the e-stop GPIO.
