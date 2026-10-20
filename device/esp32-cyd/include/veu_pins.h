#pragma once
// Cheap Yellow Display · ESP32-2432S028R (placa amarela / SKU 61115)
// Specs: ESP32-WROOM-32 · TFT 2.8" ILI9341 240×320 · touch XPT2046
//        WiFi + BT · RGB LED · LDR · microSD · 5V USB

// TFT (HSPI) — also set via platformio build_flags for TFT_eSPI
#define VEU_TFT_MISO 12
#define VEU_TFT_MOSI 13
#define VEU_TFT_SCLK 14
#define VEU_TFT_CS   15
#define VEU_TFT_DC    2
#define VEU_TFT_RST  -1
#define VEU_TFT_BL   21

// Touch (VSPI)
#define VEU_TOUCH_IRQ  36
#define VEU_TOUCH_MOSI 32
#define VEU_TOUCH_MISO 39
#define VEU_TOUCH_CLK  25
#define VEU_TOUCH_CS   33

// RGB LED (active LOW on most CYD boards)
#define VEU_LED_R 4
#define VEU_LED_G 16
#define VEU_LED_B 17

// microSD (VSPI shared bus)
#define VEU_SD_MISO 19
#define VEU_SD_MOSI 23
#define VEU_SD_SCK  18
#define VEU_SD_CS    5

// LDR (light sensor)
#define VEU_LDR 34

// Free-ish GPIOs on extended header
#define VEU_IO_21 21  // note: also backlight on stock CYD
#define VEU_IO_22 22
#define VEU_IO_27 27
#define VEU_IO_35 35

#define VEU_SCREEN_W 320
#define VEU_SCREEN_H 240
