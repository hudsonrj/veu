#include "veu_net.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ArduinoJson.h>

static WebServer server(80);
static DNSServer dns;
static bool portalActive = false;
static bool portalSaved = false;
static VeuConfig* portalCfg = nullptr;

static String htmlEscape(const String& s) {
  String o;
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (c == '<') o += "&lt;";
    else if (c == '>') o += "&gt;";
    else if (c == '"') o += "&quot;";
    else o += c;
  }
  return o;
}

static void handleRoot() {
  VeuConfig tmp;
  veuConfigLoad(tmp);
  String page =
      "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
      "<title>véu · placa</title>"
      "<style>body{font-family:system-ui;background:#0c0e12;color:#ecf2f8;padding:1.2rem}"
      "input,button{width:100%;padding:.7rem;margin:.35rem 0;border-radius:.4rem;border:1px solid #445;background:#151922;color:#ecf2f8}"
      "button{background:#e8c27a;color:#0a0c10;font-weight:700;border:0}"
      "h1{color:#e8c27a;font-size:1.2rem}label{font-size:.75rem;color:#8a939c}</style>"
      "<h1>véu · placa amarela</h1>"
      "<p>CYD ESP32-2432S028 · liga ao kernel</p>"
      "<form method=POST action=/save>"
      "<label>WiFi SSID</label><input name=ssid value='" +
      htmlEscape(tmp.ssid) +
      "'>"
      "<label>WiFi senha</label><input name=pass type=password>"
      "<label>URL do Véu</label><input name=base value='" +
      htmlEscape(tmp.baseUrl.length() ? tmp.baseUrl : VEU_DEFAULT_BASE) +
      "'>"
      "<label>Token do dispositivo</label><input name=token value='" +
      htmlEscape(tmp.token) +
      "'>"
      "<button type=submit>salvar e reiniciar</button></form>";
  server.send(200, "text/html", page);
}

static void handleSave() {
  if (!portalCfg) {
    server.send(500, "text/plain", "no cfg");
    return;
  }
  portalCfg->ssid = server.arg("ssid");
  portalCfg->pass = server.arg("pass");
  portalCfg->baseUrl = server.arg("base");
  portalCfg->token = server.arg("token");
  if (!portalCfg->bright) portalCfg->bright = 200;
  veuConfigSave(*portalCfg);
  portalSaved = true;
  server.send(200, "text/html",
              "<!doctype html><meta name=viewport content='width=device-width'>"
              "<body style='background:#0c0e12;color:#7fe7d4;font-family:system-ui;padding:2rem'>"
              "<h1>ok</h1><p>reiniciando a placa…</p></body>");
}

bool veuWifiConnect(VeuConfig& cfg, uint32_t timeoutMs) {
  if (!cfg.ssid.length()) return false;
  WiFi.mode(WIFI_STA);
  WiFi.begin(cfg.ssid.c_str(), cfg.pass.c_str());
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    delay(200);
  }
  return WiFi.status() == WL_CONNECTED;
}

void veuWifiPortalBegin() {
  portalActive = true;
  portalSaved = false;
  WiFi.mode(WIFI_AP);
  WiFi.softAP("veu-placa", "veuvela1");
  delay(100);
  dns.start(53, "*", WiFi.softAPIP());
  server.on("/", HTTP_GET, handleRoot);
  server.on("/save", HTTP_POST, handleSave);
  server.onNotFound(handleRoot);
  server.begin();
}

bool veuWifiPortalLoop(VeuConfig& cfg) {
  portalCfg = &cfg;
  if (!portalActive) return false;
  dns.processNextRequest();
  server.handleClient();
  return portalSaved;
}

static bool httpGet(const VeuConfig& cfg, const String& path, String& body) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  String url = cfg.baseUrl + path;
  http.setTimeout(12000);
  http.begin(url);
  if (cfg.token.length()) {
    http.addHeader("Authorization", "Bearer " + cfg.token);
  }
  http.addHeader("X-Veu-Device", "esp32-cyd");
  int code = http.GET();
  body = http.getString();
  http.end();
  return code >= 200 && code < 300;
}

static bool httpPost(const VeuConfig& cfg, const String& path, const String& json, String& body) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  String url = cfg.baseUrl + path;
  http.setTimeout(12000);
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Veu-CSRF", "1");
  http.addHeader("X-Veu-Device", "esp32-cyd");
  if (cfg.token.length()) {
    http.addHeader("Authorization", "Bearer " + cfg.token);
  }
  int code = http.POST(json);
  body = http.getString();
  http.end();
  return code >= 200 && code < 300;
}

bool veuFetchState(const VeuConfig& cfg, VeuState& st) {
  String body;
  if (!httpGet(cfg, "/device/esp32/state", body)) {
    st.ok = false;
    st.kernelOn = false;
    st.error = "sem link · confira URL/token/WiFi";
    return false;
  }
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    st.ok = false;
    st.error = "json inválido";
    return false;
  }
  st.ok = doc["ok"] | false;
  st.kernelOn = doc["kernel"] | st.ok;
  st.product = doc["product"] | "véu";
  st.breath = doc["breath"] | "guided";
  st.missionTitle = doc["mission"]["title"] | "";
  st.missionStatus = doc["mission"]["status"] | "";
  st.unread = doc["inbox"]["unread"] | 0;
  st.msgs = doc["inbox"]["msgs"] | 0;
  st.jobsRunning = doc["jobs"]["running"] | 0;
  st.jobsQueued = doc["jobs"]["queued"] | 0;
  st.clock = doc["clock"] | "";
  st.note = doc["note"] | "";
  st.error = doc["error"] | "";
  st.fetchedAt = millis();
  return st.ok || st.kernelOn;
}

bool veuPostEvent(const VeuConfig& cfg, const char* type, const char* payload) {
  JsonDocument doc;
  doc["type"] = type;
  doc["payload"] = payload;
  doc["device"] = "esp32-cyd";
  String json;
  serializeJson(doc, json);
  String body;
  return httpPost(cfg, "/device/esp32/event", json, body);
}
