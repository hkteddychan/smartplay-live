#pragma once
// ---------------------------------------------------------------------------
// CYD speaker output.
//
// The board has an onboard class-D amp fed from GPIO26, with a 2P Molex
// PicoBlade socket ("SPEAK", P4) — the speaker itself is optional, so this
// may stay silent.
//
// How GPIO26 reaches the amp: the ESP32's I2S peripheral can drive its
// internal DAC instead of the digital pins, and in that mode the two DAC
// channels land on GPIO25 / GPIO26 (legacy i2s_types_legacy.h):
//
//   I2S_DAC_CHANNEL_RIGHT_EN = 1  -> DAC channel 0 on GPIO25
//   I2S_DAC_CHANNEL_LEFT_EN  = 2  -> DAC channel 1 on GPIO26  <-- the amp
//
// The canonical CYD example uses i2s_set_dac_mode(I2S_DAC_CHANNEL_LEFT_EN),
// and the community pin map lists IO26 as "connected to amp" — they agree.
//
// GPIO25 is the *other* DAC channel and also the XPT2046 touch clock, so the
// right channel is deliberately unused.
//
// Legacy driver/i2s.h is required: the DAC path only exists in the old API.
// ---------------------------------------------------------------------------
#include <Arduino.h>

enum AudioPath : uint8_t {
  AUDIO_PATH_NONE = 0,
  AUDIO_PATH_AMP = 1,       // I2S DAC left  -> GPIO26 (the onboard amp)  ← use this
  AUDIO_PATH_AMP_ALT = 2,   // I2S DAC right -> GPIO25 (touch clock — avoid)
  AUDIO_PATH_PWM_26 = 3,    // LEDC PWM      -> GPIO26 (fallback, buzzier)
};

#if !defined(ESP32)
#error "cyd_audio.h targets the classic ESP32 (internal DAC)"
#endif

#include "driver/i2s.h"

#define AUDIO_PWM_PIN 26
#define AUDIO_SAMPLE_RATE 16000
#define AUDIO_I2S_PORT I2S_NUM_0

static bool s_i2sReady = false;
static uint16_t s_pwmFreq = 0;

// Amplitude in 16-bit units.  The internal DAC consumes the top 8 bits, so
// 4000 lands around 6% of full scale — audible but quiet.
#define AUDIO_DAC_AMP 4000

inline const char *audioPathName(AudioPath p) {
  switch (p) {
    case AUDIO_PATH_AMP: return "I2S-DAC-L(GPIO26)";
    case AUDIO_PATH_AMP_ALT: return "I2S-DAC-R(GPIO25)";
    case AUDIO_PATH_PWM_26: return "PWM(GPIO26)";
    default: return "none";
  }
}

// Bring up the I2S TX peripheral once; the DAC channel is switched per call.
inline bool audioI2sInit() {
  if (s_i2sReady) return true;

  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate = AUDIO_SAMPLE_RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;  // stereo, L and R slots
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 6;
  cfg.dma_buf_len = 64;
  cfg.tx_desc_auto_clear = true;

  if (i2s_driver_install(AUDIO_I2S_PORT, &cfg, 0, nullptr) != ESP_OK) return false;

  // DAC mode ignores the digital pins.
  i2s_pin_config_t pins = {};
  pins.bck_io_num = I2S_PIN_NO_CHANGE;
  pins.ws_io_num = I2S_PIN_NO_CHANGE;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_set_pin(AUDIO_I2S_PORT, &pins);

  s_i2sReady = true;
  return true;
}

// Play a quiet sine burst on one of the DAC channels.
inline bool audioDacTone(AudioPath path, uint16_t freqHz, uint16_t ms, uint16_t amp) {
  if (!audioI2sInit()) return false;
  if (path == AUDIO_PATH_AMP) i2s_set_dac_mode(I2S_DAC_CHANNEL_LEFT_EN);
  else if (path == AUDIO_PATH_AMP_ALT) i2s_set_dac_mode(I2S_DAC_CHANNEL_RIGHT_EN);
  else return false;

  const uint32_t total = (uint32_t)AUDIO_SAMPLE_RATE * ms / 1000;
  const uint32_t chunk = 256;  // frames per write
  static int16_t buf[chunk * 2];

  uint32_t done = 0;
  while (done < total) {
    uint32_t n = total - done;
    if (n > chunk) n = chunk;
    for (uint32_t i = 0; i < n; i++) {
      uint32_t t = done + i;
      // raised-cosine envelope: no click at either end
      double env = 0.5 - 0.5 * cos(2.0 * M_PI * (double)t / (double)total);
      double s = sin(2.0 * M_PI * (double)freqHz * (double)t / (double)AUDIO_SAMPLE_RATE);
      int16_t v = (int16_t)(s * env * (double)amp);
      buf[i * 2] = v;      // left  -> DAC channel 1 (GPIO26, the amp)
      buf[i * 2 + 1] = v;  // right -> DAC channel 0 (GPIO25, touch clock)
    }
    size_t written = 0;
    i2s_write(AUDIO_I2S_PORT, buf, n * 4, &written, pdMS_TO_TICKS(500));
    done += n;
  }
  return true;
}

// Play a quiet square burst on GPIO26 (LEDC, 8-bit).
inline bool audioPwmTone(AudioPath path, uint16_t freqHz, uint16_t ms, uint16_t amp) {
  if (path != AUDIO_PATH_PWM_26) return false;

  const uint16_t maxDuty = 255;
  const uint16_t peak = amp > maxDuty ? maxDuty : amp;  // caller passes a duty
  static const uint8_t RES = 8;

  if (s_pwmFreq != freqHz) {
    ledcAttach(AUDIO_PWM_PIN, freqHz, RES);
    s_pwmFreq = freqHz;
  }

  const uint32_t steps = ms / 4;  // 4 ms steps
  for (uint32_t i = 0; i < steps; i++) {
    double env = 0.5 - 0.5 * cos(2.0 * M_PI * (double)i / (double)steps);
    uint16_t duty = (uint16_t)(env * peak);
    ledcWrite(AUDIO_PWM_PIN, duty);
    delay(4);
  }
  ledcWrite(AUDIO_PWM_PIN, 0);
  return true;
}

// One entry point for every path. amp is 16-bit scale for the DAC paths and
// a 0-255 duty for PWM.  Returns false if the path could not be driven.
inline bool audioTone(AudioPath path, uint16_t freqHz, uint16_t ms, uint16_t amp) {
  switch (path) {
    case AUDIO_PATH_AMP:
    case AUDIO_PATH_AMP_ALT:
      return audioDacTone(path, freqHz, ms, amp);
    case AUDIO_PATH_PWM_26:
      return audioPwmTone(path, freqHz, ms, amp);
    default:
      return false;
  }
}

inline void audioStop() {
  if (s_i2sReady) i2s_set_dac_mode(I2S_DAC_CHANNEL_DISABLE);
  ledcWrite(AUDIO_PWM_PIN, 0);
}
