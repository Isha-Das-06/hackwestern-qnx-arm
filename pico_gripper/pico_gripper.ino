// Pico 2 gripper I/O board (Arduino-Pico core by Earle Philhower).
//
// This board is deliberately DUMB. QNX on the Pi makes every grip decision.
// The Pico only:
//   1. streams averaged FSR readings to the Pi at ~200 Hz,
//   2. moves the servo to the angle in the latest valid command (clamped),
//   3. FREEZES the servo where it is if no valid command arrives for 100 ms.
// It never squeezes harder and never opens on its own.
//
// Wiring (pins picked for this build, see docs/GRIPPER.md):
//   FSR jaw 1  -> GP26 (ADC0), divider: 3V3 - FSR - GP26 - 10k - GND
//   FSR jaw 2  -> GP27 (ADC1), same divider
//   Servo PWM  -> GP16 (servo gets its own 5-6 V supply; grounds joined)
//   UART0 TX   -> GP0 (pin 1)  -> Pi GPIO9 RX (pin 21)
//   UART0 RX   -> GP1 (pin 2)  <- Pi GPIO8 TX (pin 24)
//   GND        -> Pi GND (pin 25 or any GND)
//
// Pico -> Pi frame (10 bytes, ~200 Hz):
//   0xAA 0x55 fsr1_lo fsr1_hi fsr2_lo fsr2_hi angle flags seq xor
//   fsr values: 0..4095 (12-bit ADC, average of FSR_SAMPLES reads), little-endian
//   flags bit0 = link-loss freeze active, bit1 = servo not attached yet
//   xor = XOR of the 9 bytes before it
//
// Pi -> Pico frame (6 bytes, 100 Hz):
//   0xAA 0x56 angle flags seq xor
//   flags bit0 = hold (angle is still applied; it is just informational)

#include <Arduino.h>
#include <Servo.h>

// ---- Pins and limits --------------------------------------------------------
const int PIN_FSR1 = 26;
const int PIN_FSR2 = 27;
const int PIN_SERVO = 16;

// Absolute servo clamp. Set these after checking the jaw travel by hand so the
// servo can never drive the jaws into each other or past fully open.
const uint8_t ANGLE_MIN = 10;
const uint8_t ANGLE_MAX = 170;

const uint32_t LINK_TIMEOUT_MS = 100;   // no valid command for this long -> freeze
const uint32_t FRAME_PERIOD_US = 5000;  // 200 Hz telemetry
const int FSR_SAMPLES = 8;              // ADC reads averaged per FSR per frame
const uint32_t BAUD = 115200;

// ---- State ------------------------------------------------------------------
Servo servo;
bool servoAttached = false;   // stays limp until QNX sends the first command
uint8_t currentAngle = 0;     // last angle written to the servo
uint32_t lastCmdMs = 0;       // millis() of the last valid command
bool everGotCmd = false;
uint8_t txSeq = 0;
uint32_t nextFrameUs = 0;

// Receive parser
uint8_t rxBuf[6];
int rxLen = 0;

static uint16_t readFsr(int pin) {
  uint32_t sum = 0;
  for (int i = 0; i < FSR_SAMPLES; i++) sum += analogRead(pin);
  return (uint16_t)(sum / FSR_SAMPLES);
}

static bool linkFrozen() {
  return everGotCmd && (millis() - lastCmdMs > LINK_TIMEOUT_MS);
}

static void applyCommand(uint8_t angle) {
  if (angle < ANGLE_MIN) angle = ANGLE_MIN;
  if (angle > ANGLE_MAX) angle = ANGLE_MAX;
  if (!servoAttached) {
    servo.attach(PIN_SERVO);
    servoAttached = true;
  }
  servo.write(angle);
  currentAngle = angle;
}

// Byte-at-a-time parser: hunt for 0xAA 0x56, then collect 6 bytes and check xor.
static void pollUart() {
  while (Serial1.available()) {
    uint8_t b = (uint8_t)Serial1.read();
    if (rxLen == 0 && b != 0xAA) continue;
    if (rxLen == 1 && b != 0x56) { rxLen = (b == 0xAA) ? 1 : 0; continue; }
    rxBuf[rxLen++] = b;
    if (rxLen < 6) continue;
    rxLen = 0;
    uint8_t x = 0;
    for (int i = 0; i < 5; i++) x ^= rxBuf[i];
    if (x != rxBuf[5]) continue;          // bad checksum: ignore, don't reset timer
    // Valid command. Even after a freeze, a fresh valid command un-freezes:
    // QNX is talking again and is back in charge.
    lastCmdMs = millis();
    everGotCmd = true;
    applyCommand(rxBuf[2]);
  }
}

static void sendFrame() {
  uint16_t f1 = readFsr(PIN_FSR1);
  uint16_t f2 = readFsr(PIN_FSR2);
  uint8_t flags = 0;
  if (linkFrozen()) flags |= 0x01;
  if (!servoAttached) flags |= 0x02;
  uint8_t fr[10] = {0xAA, 0x55,
                    (uint8_t)(f1 & 0xFF), (uint8_t)(f1 >> 8),
                    (uint8_t)(f2 & 0xFF), (uint8_t)(f2 >> 8),
                    currentAngle, flags, txSeq++, 0};
  for (int i = 0; i < 9; i++) fr[9] ^= fr[i];
  Serial1.write(fr, sizeof fr);
}

void setup() {
  analogReadResolution(12);
  Serial1.setTX(0);
  Serial1.setRX(1);
  Serial1.begin(BAUD);
  Serial.begin(115200);          // USB serial, for debugging only
  pinMode(LED_BUILTIN, OUTPUT);
  nextFrameUs = micros();
}

void loop() {
  pollUart();
  // Freeze = simply don't touch the servo. It keeps the last angle (holding).
  // Nothing to do here on purpose: that's the whole failsafe.

  uint32_t now = micros();
  if ((int32_t)(now - nextFrameUs) >= 0) {
    nextFrameUs += FRAME_PERIOD_US;
    if ((int32_t)(now - nextFrameUs) > (int32_t)FRAME_PERIOD_US) nextFrameUs = now;  // fell behind
    sendFrame();
    // LED: solid = QNX in control, blinking = frozen / waiting for QNX.
    bool ok = everGotCmd && !linkFrozen();
    digitalWrite(LED_BUILTIN, ok ? HIGH : ((millis() / 250) & 1));
  }
}
