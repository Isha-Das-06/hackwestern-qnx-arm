// fsr_test.ino: check both FSRs before flashing the full gripper firmware.
// Prints both readings over USB serial at 20 Hz (Arduino-Pico, board "Raspberry Pi Pico 2").
//
// Divider on each jaw: 3V3 -> FSR -> GP26 (or GP27) -> 3.3k -> GND.
// More force = lower FSR resistance = higher count.

const int PIN_FSR1 = 26;  // ADC0
const int PIN_FSR2 = 27;  // ADC1
const int SAMPLES = 8;    // same averaging as pico_gripper.ino

uint16_t readFsr(int pin) {
  uint32_t sum = 0;
  for (int i = 0; i < SAMPLES; i++) sum += analogRead(pin);
  return sum / SAMPLES;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);  // 0..4095
}

void loop() {
  uint16_t f1 = readFsr(PIN_FSR1), f2 = readFsr(PIN_FSR2);
  Serial.printf("fsr1=%4u (%.2f V)  fsr2=%4u (%.2f V)\n",
                f1, f1 * 3.3f / 4095, f2, f2 * 3.3f / 4095);
  delay(50);
}
