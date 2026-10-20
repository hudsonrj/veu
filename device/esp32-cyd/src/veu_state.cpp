#include "veu_state.h"

const char* veuScreenName(VeuScreen s) {
  switch (s) {
    case SCR_BOOT: return "boot";
    case SCR_WIFI: return "wifi";
    case SCR_HOME: return "véu";
    case SCR_MISSION: return "missão";
    case SCR_INBOX: return "inbox";
    case SCR_CAPTURE: return "captura";
    case SCR_BREATH: return "fôlego";
    case SCR_SETTINGS: return "ajustes";
    default: return "?";
  }
}
