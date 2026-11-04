#pragma once
// ---------------------------------------------------------------------------
// Shared screen geometry + palette for the SmartPLAY CYD firmware.
// RGB565 values (TFT_eSPI uses 16-bit colour).
// ---------------------------------------------------------------------------
#include <Arduino.h>

static const int SCR_W = 320, SCR_H = 240;
static const int HEADER_H = 30, FOOTER_H = 24;
static const int BODY_Y = HEADER_H;
static const int BODY_H = SCR_H - HEADER_H - FOOTER_H;

#define C_BG ((uint16_t)0x10C8)
#define C_BAR ((uint16_t)0x342A)
#define C_CARD ((uint16_t)0x2644)
#define C_CARD_HOT ((uint16_t)0x1ED8)
#define C_TEXT ((uint16_t)0xFFFF)
#define C_DIM ((uint16_t)0xE6B8)
#define C_GOOD ((uint16_t)0x6730)
#define C_ACCENT ((uint16_t)0x07FF)
#define C_WARN ((uint16_t)0xFEE0)
