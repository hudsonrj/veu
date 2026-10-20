#pragma once
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include "veu_state.h"
#include "veu_config.h"

void veuUiBegin(TFT_eSPI& tft, XPT2046_Touchscreen& ts);
void veuUiSetBright(uint8_t v);
void veuUiDraw(TFT_eSPI& tft, VeuScreen scr, const VeuState& st, const VeuConfig& cfg, const String& flash);
bool veuUiTouch(XPT2046_Touchscreen& ts, int16_t& x, int16_t& y);
int veuUiHitNav(int16_t x, int16_t y);          // -1 none, 0..n tab
int veuUiHitBreath(int16_t x, int16_t y);       // 0..3
bool veuUiHitCapture(int16_t x, int16_t y);
bool veuUiHitPrimary(int16_t x, int16_t y);     // big CTA
