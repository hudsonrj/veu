#pragma once
#include <Arduino.h>

struct VeuState {
  bool ok = false;
  bool kernelOn = false;
  String product;
  String breath;       // guided|semi|free|auto
  String missionTitle;
  String missionStatus;
  int unread = 0;
  int msgs = 0;
  int jobsRunning = 0;
  int jobsQueued = 0;
  String clock;
  String note;         // short status line from kernel
  String error;
  uint32_t fetchedAt = 0;
};

enum VeuScreen : uint8_t {
  SCR_BOOT = 0,
  SCR_WIFI,
  SCR_HOME,
  SCR_MISSION,
  SCR_INBOX,
  SCR_CAPTURE,
  SCR_BREATH,
  SCR_SETTINGS,
  SCR_COUNT
};

const char* veuScreenName(VeuScreen s);
