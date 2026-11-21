# hackwestern-qnx-arm
## Branch `surya`: arm firmware

- `mks_servo/`: Surya's SERVO42C stepper driver and tests (from the Pi), plus the
  QNX gripper force loop (`gripper_link.py`), its test tools and JSON config.
- `pico_gripper/pico_gripper.ino`: Pico 2 firmware (FSR stream + servo, freezes if QNX goes quiet).
- `docs/GRIPPER.md`: wiring, frame format, how to run, and test results.
