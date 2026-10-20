#include "veu_config.h"
#include <Preferences.h>

bool veuConfigLoad(VeuConfig& out) {
  Preferences p;
  if (!p.begin(VEU_NVS_NS, true)) return false;
  out.ssid = p.getString(VEU_NVS_WIFI_SSID, "");
  out.pass = p.getString(VEU_NVS_WIFI_PASS, "");
  out.baseUrl = p.getString(VEU_NVS_BASE, VEU_DEFAULT_BASE);
  out.token = p.getString(VEU_NVS_TOKEN, "");
  out.bright = p.getUChar(VEU_NVS_BRIGHT, 200);
  p.end();
  if (out.baseUrl.endsWith("/")) out.baseUrl.remove(out.baseUrl.length() - 1);
  return true;
}

bool veuConfigSave(const VeuConfig& in) {
  Preferences p;
  if (!p.begin(VEU_NVS_NS, false)) return false;
  p.putString(VEU_NVS_WIFI_SSID, in.ssid);
  p.putString(VEU_NVS_WIFI_PASS, in.pass);
  p.putString(VEU_NVS_BASE, in.baseUrl);
  p.putString(VEU_NVS_TOKEN, in.token);
  p.putUChar(VEU_NVS_BRIGHT, in.bright);
  p.end();
  return true;
}

void veuConfigClearWifi() {
  Preferences p;
  if (!p.begin(VEU_NVS_NS, false)) return;
  p.remove(VEU_NVS_WIFI_SSID);
  p.remove(VEU_NVS_WIFI_PASS);
  p.end();
}
