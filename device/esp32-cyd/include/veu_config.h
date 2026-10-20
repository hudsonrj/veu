#pragma once
#include <Arduino.h>

// NVS keys
#define VEU_NVS_NS "veu"
#define VEU_NVS_WIFI_SSID "ssid"
#define VEU_NVS_WIFI_PASS "pass"
#define VEU_NVS_BASE "base"     // https://veu.ch8ai.com.br
#define VEU_NVS_TOKEN "token"   // device bearer
#define VEU_NVS_BRIGHT "bright" // 0-255 backlight PWM

#ifndef VEU_DEFAULT_BASE
#define VEU_DEFAULT_BASE "https://veu.ch8ai.com.br"
#endif

struct VeuConfig {
  String ssid;
  String pass;
  String baseUrl;
  String token;
  uint8_t bright;
};

bool veuConfigLoad(VeuConfig& out);
bool veuConfigSave(const VeuConfig& in);
void veuConfigClearWifi();
