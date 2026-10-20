/**
 * Véu OS · companion na placa amarela (CYD ESP32-2432S028R / 61115)
 *
 * Extrai o potencial do hardware:
 *  - TFT ILI9341 240×320 touch → painéis Véu (home/missão/inbox/captura/fôlego)
 *  - WiFi → sync com kernel (/device/esp32/*)
 *  - RGB LED → kernel on/erro
 *  - LDR → brilho automático
 *  - Touch → navegação e ações
 *  - AP portal veu-placa → provisionamento sem cabo
 *
 * Flash:  pio run -e cyd -t upload
 * Portal: SSID veu-placa / senha veuvela1 → http://192.168.4.1
 */

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include "veu_pins.h"
#include "veu_config.h"
#include "veu_state.h"
#include "veu_ui.h"
#include "veu_net.h"

TFT_eSPI tft = TFT_eSPI();
XPT2046_Touchscreen ts(VEU_TOUCH_CS, VEU_TOUCH_IRQ);

VeuConfig cfg;
VeuState st;
VeuScreen screen = SCR_BOOT;
String flashMsg;
uint32_t lastFetch = 0;
uint32_t lastTouch = 0;
uint32_t lastLdr = 0;
bool portalMode = false;

static const char* BREATH_IDS[] = {"guided", "semi", "free", "auto"};

static void go(VeuScreen s) {
  screen = s;
  veuUiDraw(tft, screen, st, cfg, flashMsg);
}

static void refreshState(bool force = false) {
  if (!force && millis() - lastFetch < 12000) return;
  if (WiFi.status() != WL_CONNECTED) return;
  flashMsg = "sync…";
  veuUiDraw(tft, screen, st, cfg, flashMsg);
  if (veuFetchState(cfg, st)) {
    flashMsg = "sync ok";
  } else {
    flashMsg = st.error.length() ? st.error : "sync falhou";
  }
  lastFetch = millis();
  veuUiDraw(tft, screen, st, cfg, flashMsg);
}

static void autoBright() {
  if (millis() - lastLdr < 2500) return;
  lastLdr = millis();
  int ldr = analogRead(VEU_LDR); // 0..4095, darker → higher on many CYD
  // map ambient to backlight (invert-ish)
  int b = map(constrain(ldr, 200, 3500), 200, 3500, 240, 40);
  cfg.bright = (uint8_t)b;
  veuUiSetBright(cfg.bright);
}

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.println("\nvéu · esp32-cyd boot");

  veuConfigLoad(cfg);
  veuUiBegin(tft, ts);
  go(SCR_BOOT);
  delay(600);

  if (!cfg.ssid.length() || !veuWifiConnect(cfg, 18000)) {
    portalMode = true;
    veuWifiPortalBegin();
    go(SCR_WIFI);
    Serial.println("portal AP veu-placa");
    return;
  }

  Serial.print("wifi ");
  Serial.println(WiFi.localIP());
  screen = SCR_HOME;
  refreshState(true);
}

void loop() {
  if (portalMode) {
    if (veuWifiPortalLoop(cfg)) {
      flashMsg = "salvo · reboot";
      veuUiDraw(tft, SCR_WIFI, st, cfg, flashMsg);
      delay(900);
      ESP.restart();
    }
    // long-press top-left unused in portal
    delay(10);
    return;
  }

  autoBright();

  if (millis() - lastFetch > 15000) {
    refreshState(false);
  }

  int16_t x, y;
  if (veuUiTouch(ts, x, y) && millis() - lastTouch > 280) {
    lastTouch = millis();
    Serial.printf("touch %d,%d\n", x, y);

    int nav = veuUiHitNav(x, y);
    if (nav >= 0) {
      go((VeuScreen)(SCR_HOME + nav));
      if (nav == 0) refreshState(true);
      return;
    }

    if (screen == SCR_CAPTURE && veuUiHitCapture(x, y)) {
      flashMsg = "enviando…";
      veuUiDraw(tft, screen, st, cfg, flashMsg);
      bool ok = veuPostEvent(cfg, "capture", "nota da placa amarela");
      flashMsg = ok ? "nota no Véu" : "falha envio";
      veuUiDraw(tft, screen, st, cfg, flashMsg);
      return;
    }

    if (screen == SCR_BREATH) {
      int b = veuUiHitBreath(x, y);
      if (b >= 0) {
        flashMsg = String("fôlego · ") + BREATH_IDS[b];
        veuUiDraw(tft, screen, st, cfg, flashMsg);
        if (veuPostEvent(cfg, "breath", BREATH_IDS[b])) {
          st.breath = BREATH_IDS[b];
          flashMsg = "ok · " + st.breath;
        } else {
          flashMsg = "kernel recusou";
        }
        veuUiDraw(tft, screen, st, cfg, flashMsg);
        return;
      }
    }

    if (screen == SCR_SETTINGS && y > 60 && y < 100) {
      // tap WiFi row → re-enter portal
      portalMode = true;
      veuWifiPortalBegin();
      go(SCR_WIFI);
      return;
    }

    if (screen == SCR_HOME && y > 40 && y < 100) {
      refreshState(true);
    }
  }

  delay(12);
}
