// Pico 2 force-sensor board (Arduino-Pico core by Earle Philhower).
//
// This board is deliberately DUMB. It only streams averaged FSR readings to
// the Pi at ~200 Hz. QNX on the Pi makes every grip decision AND drives the
// servo itself (hardware PWM on Pi GPIO19), so nothing here can move the jaws.
//
// Board: Tenstar RP2350 USB-A (FQBN rp2040:rp2040:rpipico2; go by the GPIO labels
// on the board). Wiring (see docs/GRIPPER.md):
//   FSR jaw 1  -> GP26 (ADC0), divider: 3V3 - FSR - GP26 - 3.3k - GND
//   FSR jaw 2  -> GP27 (ADC1), divider: 3V3 - FSR - GP27 - 3.3k - GND
//   UART0 TX   -> GP0  -> Pi GPIO9 RX (Pi pin 21)
//   GND        -> GND  -> Pi GND (Pi pin 25)
//   Power      -> its USB-A plug in a Pi USB port. Never also feed 5V/VSYS.
//
// Pico -> Pi frame (10 bytes, ~200 Hz):
//   0xAA 0x55 fsr1_lo fsr1_hi fsr2_lo fsr2_hi 0 0 seq xor
//   fsr values: 0..4095 (12-bit ADC, average of FSR_SAMPLES reads), little-endian
//   the two zero bytes are unused (they carried the servo angle and flags when
//   the Pico drove the servo); xor = XOR of the 9 bytes before it

#include <Arduino.h>

const int PIN_FSR1 = 26;
const int PIN_FSR2 = 27;

const uint32_t FRAME_PERIOD_US = 5000;  // 200 Hz telemetry
const int FSR_SAMPLES = 8;              // ADC reads averaged per FSR per frame
const uint32_t BAUD = 115200;

uint8_t txSeq = 0;
uint32_t nextFrameUs = 0;

static uint16_t readFsr(int pin) {
  uint32_t sum = 0;
  for (int i = 0; i < FSR_SAMPLES; i++) sum += analogRead(pin);
  return (uint16_t)(sum / FSR_SAMPLES);
}

static void sendFrame() {
  uint16_t f1 = readFsr(PIN_FSR1);
  uint16_t f2 = readFsr(PIN_FSR2);
  uint8_t fr[10] = {0xAA, 0x55,
                    (uint8_t)(f1 & 0xFF), (uint8_t)(f1 >> 8),
                    (uint8_t)(f2 & 0xFF), (uint8_t)(f2 >> 8),
                    0, 0, txSeq++, 0};
  for (int i = 0; i < 9; i++) fr[9] ^= fr[i];
  Serial1.write(fr, sizeof fr);
  if (txSeq % 100 == 0) Serial.printf("fsr1=%4u fsr2=%4u\n", f1, f2);   // USB, 2 Hz: alive check
}

void setup() {
  analogReadResolution(12);
  Serial1.setTX(0);
  Serial1.setRX(1);
  Serial1.begin(BAUD);
  Serial.begin(115200);          // USB serial, for debugging only
  nextFrameUs = micros();
}

void loop() {
  uint32_t now = micros();
  if ((int32_t)(now - nextFrameUs) >= 0) {
    nextFrameUs += FRAME_PERIOD_US;
    if ((int32_t)(now - nextFrameUs) > (int32_t)FRAME_PERIOD_US) nextFrameUs = now;  // fell behind
    sendFrame();
  }
}
