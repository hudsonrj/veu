#include "veu_ui.h"
#include "veu_pins.h"
#include <SPI.h>

static const uint16_t C_BG = 0x0841;      // near black
static const uint16_t C_PANEL = 0x10A2;
static const uint16_t C_GOLD = 0xE5C6;    // #e8c27a-ish
static const uint16_t C_MIST = 0xDEFB;
static const uint16_t C_DIM = 0x8410;
static const uint16_t C_TEAL = 0x3F9A;    // #7fe7d4-ish
static const uint16_t C_ERR = 0xF28A;
static const uint16_t C_NAV = 0x2124;

static SPIClass touchSPI(VSPI);

void veuUiBegin(TFT_eSPI& tft, XPT2046_Touchscreen& ts) {
  pinMode(VEU_TFT_BL, OUTPUT);
  digitalWrite(VEU_TFT_BL, HIGH);
  ledcSetup(0, 5000, 8);
  ledcAttachPin(VEU_TFT_BL, 0);
  ledcWrite(0, 200);

  pinMode(VEU_LED_R, OUTPUT);
  pinMode(VEU_LED_G, OUTPUT);
  pinMode(VEU_LED_B, OUTPUT);
  digitalWrite(VEU_LED_R, HIGH);
  digitalWrite(VEU_LED_G, HIGH);
  digitalWrite(VEU_LED_B, HIGH);

  tft.init();
  tft.setRotation(1); // landscape 320×240
  tft.fillScreen(C_BG);

  touchSPI.begin(VEU_TOUCH_CLK, VEU_TOUCH_MISO, VEU_TOUCH_MOSI, VEU_TOUCH_CS);
  ts.begin(touchSPI);
  ts.setRotation(1);
}

void veuUiSetBright(uint8_t v) {
  ledcWrite(0, v);
}

static void setRgb(bool on, bool err) {
  // active LOW
  digitalWrite(VEU_LED_R, err ? LOW : HIGH);
  digitalWrite(VEU_LED_G, on && !err ? LOW : HIGH);
  digitalWrite(VEU_LED_B, HIGH);
}

static void drawHeader(TFT_eSPI& tft, const char* title, const VeuState& st) {
  tft.fillRect(0, 0, VEU_SCREEN_W, 28, C_PANEL);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_PANEL);
  tft.drawString("véu", 8, 6, 2);
  tft.setTextColor(C_MIST, C_PANEL);
  tft.drawString(title, 48, 8, 1);
  tft.setTextDatum(TR_DATUM);
  tft.setTextColor(st.kernelOn ? C_TEAL : C_ERR, C_PANEL);
  tft.drawString(st.kernelOn ? "k·on" : "k·off", VEU_SCREEN_W - 8, 8, 1);
}

static void drawNav(TFT_eSPI& tft, VeuScreen scr) {
  const char* tabs[] = {"home", "miss", "inbox", "cap", "breath", "cfg"};
  const int n = 6;
  const int w = VEU_SCREEN_W / n;
  tft.fillRect(0, VEU_SCREEN_H - 28, VEU_SCREEN_W, 28, C_NAV);
  for (int i = 0; i < n; i++) {
    bool on = (int)scr == (i + (int)SCR_HOME);
    // map: home=2, mission=3, ... settings=7 → index 0..5
    on = ((int)scr - (int)SCR_HOME) == i;
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(on ? C_GOLD : C_DIM, C_NAV);
    tft.drawString(tabs[i], w * i + w / 2, VEU_SCREEN_H - 14, 1);
    if (on) {
      tft.drawFastHLine(w * i + 6, VEU_SCREEN_H - 3, w - 12, C_GOLD);
    }
  }
}

static void drawHome(TFT_eSPI& tft, const VeuState& st) {
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_BG);
  tft.drawString("véu os · placa", 12, 40, 2);
  tft.setTextColor(C_MIST, C_BG);
  tft.drawString(st.clock.length() ? st.clock : "--:--", 12, 68, 4);

  tft.fillRoundRect(12, 110, 140, 54, 6, C_PANEL);
  tft.setTextColor(C_DIM, C_PANEL);
  tft.drawString("inbox", 22, 118, 1);
  tft.setTextColor(C_TEAL, C_PANEL);
  tft.drawNumber(st.unread, 22, 132, 4);

  tft.fillRoundRect(168, 110, 140, 54, 6, C_PANEL);
  tft.setTextColor(C_DIM, C_PANEL);
  tft.drawString("jobs", 178, 118, 1);
  tft.setTextColor(C_GOLD, C_PANEL);
  String j = String(st.jobsRunning) + "/" + String(st.jobsQueued);
  tft.drawString(j, 178, 136, 2);

  tft.setTextColor(C_DIM, C_BG);
  tft.drawString(st.breath.length() ? ("fôlego · " + st.breath) : "fôlego · —", 12, 176, 1);
  if (st.note.length()) {
    tft.setTextColor(C_MIST, C_BG);
    tft.drawString(st.note.substring(0, 42), 12, 194, 1);
  }
}

static void drawMission(TFT_eSPI& tft, const VeuState& st) {
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_BG);
  tft.drawString("missão", 12, 40, 2);
  tft.fillRoundRect(12, 68, 296, 120, 8, C_PANEL);
  tft.setTextColor(C_MIST, C_PANEL);
  String title = st.missionTitle.length() ? st.missionTitle : "(sem missão ativa)";
  // wrap roughly
  tft.drawString(title.substring(0, 34), 22, 80, 2);
  if (title.length() > 34) tft.drawString(title.substring(34, 68), 22, 100, 2);
  tft.setTextColor(C_TEAL, C_PANEL);
  tft.drawString(st.missionStatus.length() ? st.missionStatus : "—", 22, 140, 2);
}

static void drawInbox(TFT_eSPI& tft, const VeuState& st) {
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_BG);
  tft.drawString("nervos · hoje", 12, 40, 2);
  tft.fillRoundRect(12, 70, 140, 80, 8, C_PANEL);
  tft.setTextColor(C_DIM, C_PANEL);
  tft.drawString("msgs", 24, 82, 1);
  tft.setTextColor(C_MIST, C_PANEL);
  tft.drawNumber(st.msgs, 24, 100, 4);
  tft.fillRoundRect(168, 70, 140, 80, 8, C_PANEL);
  tft.setTextColor(C_DIM, C_PANEL);
  tft.drawString("não lidas", 180, 82, 1);
  tft.setTextColor(C_TEAL, C_PANEL);
  tft.drawNumber(st.unread, 180, 100, 4);
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("toque home p/ atualizar do kernel", 12, 170, 1);
}

static void drawCapture(TFT_eSPI& tft) {
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_BG);
  tft.drawString("captura rápida", 12, 40, 2);
  tft.setTextColor(C_MIST, C_BG);
  tft.drawString("manda um pulso ao Véu", 12, 68, 1);
  tft.fillRoundRect(40, 100, 240, 64, 10, C_GOLD);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_BG, C_GOLD);
  tft.drawString("TOQUE · enviar nota", 160, 132, 2);
}

static void drawBreath(TFT_eSPI& tft, const VeuState& st) {
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_BG);
  tft.drawString("fôlego", 12, 40, 2);
  const char* modes[] = {"guiado", "semi", "livre", "autônomo"};
  const char* ids[] = {"guided", "semi", "free", "auto"};
  for (int i = 0; i < 4; i++) {
    int x = 12 + (i % 2) * 154;
    int y = 70 + (i / 2) * 56;
    bool on = st.breath == ids[i] || st.breath == modes[i];
    tft.fillRoundRect(x, y, 142, 48, 8, on ? C_GOLD : C_PANEL);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(on ? C_BG : C_MIST, on ? C_GOLD : C_PANEL);
    tft.drawString(modes[i], x + 71, y + 24, 2);
  }
}

static void drawSettings(TFT_eSPI& tft, const VeuConfig& cfg, const VeuState& st) {
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_BG);
  tft.drawString("ajustes · CYD", 12, 40, 2);
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("WiFi", 12, 68, 1);
  tft.setTextColor(C_MIST, C_BG);
  tft.drawString(cfg.ssid.length() ? cfg.ssid : "(portal: veu-placa)", 12, 82, 2);
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("kernel", 12, 112, 1);
  tft.setTextColor(C_MIST, C_BG);
  tft.drawString(cfg.baseUrl.substring(0, 40), 12, 126, 1);
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("token", 12, 148, 1);
  tft.setTextColor(C_MIST, C_BG);
  String tok = cfg.token.length() ? (cfg.token.substring(0, 8) + "…") : "(vazio)";
  tft.drawString(tok, 12, 162, 1);
  if (st.error.length()) {
    tft.setTextColor(C_ERR, C_BG);
    tft.drawString(st.error.substring(0, 48), 12, 186, 1);
  }
}

static void drawWifi(TFT_eSPI& tft) {
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(C_GOLD, C_BG);
  tft.drawString("ligar WiFi", 12, 40, 2);
  tft.setTextColor(C_MIST, C_BG);
  tft.drawString("1. conecte em  veu-placa", 12, 80, 2);
  tft.drawString("2. abra  http://192.168.4.1", 12, 108, 2);
  tft.drawString("3. SSID · senha · URL · token", 12, 136, 2);
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("token: app Placa no Véu SO", 12, 170, 1);
}

void veuUiDraw(TFT_eSPI& tft, VeuScreen scr, const VeuState& st, const VeuConfig& cfg, const String& flash) {
  tft.fillScreen(C_BG);
  if (scr == SCR_WIFI || scr == SCR_BOOT) {
    drawHeader(tft, scr == SCR_BOOT ? "boot" : "wifi", st);
    if (scr == SCR_WIFI) drawWifi(tft);
    else {
      tft.setTextDatum(MC_DATUM);
      tft.setTextColor(C_GOLD, C_BG);
      tft.drawString("véu", 160, 110, 4);
      tft.setTextColor(C_DIM, C_BG);
      tft.drawString("placa amarela · CYD", 160, 150, 2);
      if (flash.length()) {
        tft.setTextColor(C_MIST, C_BG);
        tft.drawString(flash, 160, 180, 1);
      }
    }
    setRgb(false, false);
    return;
  }
  drawHeader(tft, veuScreenName(scr), st);
  switch (scr) {
    case SCR_HOME: drawHome(tft, st); break;
    case SCR_MISSION: drawMission(tft, st); break;
    case SCR_INBOX: drawInbox(tft, st); break;
    case SCR_CAPTURE: drawCapture(tft); break;
    case SCR_BREATH: drawBreath(tft, st); break;
    case SCR_SETTINGS: drawSettings(tft, cfg, st); break;
    default: break;
  }
  drawNav(tft, scr);
  if (flash.length()) {
    tft.fillRect(0, 28, VEU_SCREEN_W, 16, C_PANEL);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(C_TEAL, C_PANEL);
    tft.drawString(flash.substring(0, 48), 8, 30, 1);
  }
  setRgb(st.kernelOn, st.error.length() > 0);
}

bool veuUiTouch(XPT2046_Touchscreen& ts, int16_t& x, int16_t& y) {
  if (!ts.tirqTouched() && !ts.touched()) return false;
  if (!ts.touched()) return false;
  TS_Point p = ts.getPoint();
  // map raw → 320×240 landscape (typical CYD calibration)
  x = map(p.x, 200, 3700, 0, VEU_SCREEN_W);
  y = map(p.y, 240, 3800, 0, VEU_SCREEN_H);
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  if (x >= VEU_SCREEN_W) x = VEU_SCREEN_W - 1;
  if (y >= VEU_SCREEN_H) y = VEU_SCREEN_H - 1;
  return true;
}

int veuUiHitNav(int16_t x, int16_t y) {
  if (y < VEU_SCREEN_H - 28) return -1;
  int w = VEU_SCREEN_W / 6;
  int i = x / w;
  if (i < 0 || i > 5) return -1;
  return i;
}

int veuUiHitBreath(int16_t x, int16_t y) {
  for (int i = 0; i < 4; i++) {
    int bx = 12 + (i % 2) * 154;
    int by = 70 + (i / 2) * 56;
    if (x >= bx && x < bx + 142 && y >= by && y < by + 48) return i;
  }
  return -1;
}

bool veuUiHitCapture(int16_t x, int16_t y) {
  return x >= 40 && x <= 280 && y >= 100 && y <= 164;
}

bool veuUiHitPrimary(int16_t x, int16_t y) {
  return veuUiHitCapture(x, y);
}
