# Véu Placa · ESP32 CYD (placa amarela)

Companion nativo do **Véu OS** para a placa **ESP32-2432S028R** (SKU **61115**, “Cheap Yellow Display”).

## O que a placa é

| Peça | Spec |
|------|------|
| MCU | ESP32-WROOM-32 dual-core 240 MHz · WiFi + Bluetooth |
| Flash / RAM | 4 MB · 520 KB SRAM |
| Display | TFT 2.8" **ILI9341** · **240×320** RGB |
| Touch | Resistivo **XPT2046** |
| Extras | LED RGB, LDR, microSD, USB 5 V |

Não roda o desktop React: ela é um **nervo físico** do SO — painel táctil sincronizado com o kernel.

## Potencial usado

- **TFT + touch** → telas home / missão / inbox / captura / fôlego / ajustes  
- **WiFi** → `GET /device/esp32/state` + `POST /device/esp32/event`  
- **RGB** → kernel on (verde) / erro (vermelho)  
- **LDR** → brilho automático do backlight  
- **AP `veu-placa`** → provisiona SSID, URL e token sem cabo  

## Flash (PlatformIO)

```bash
cd device/esp32-cyd
pio run -e cyd -t upload
pio device monitor -b 115200
```

Arduino IDE também funciona: abra `src/main.cpp` como sketch, instale TFT_eSPI + XPT2046_Touchscreen + ArduinoJson e use os `build_flags` do `platformio.ini` no `User_Setup.h`.

## Emparelhar com o Véu

1. No SO: app **Placa** → **gerar token**  
2. Na placa (sem WiFi): conecte no AP `veu-placa` / senha `veuvela1`  
3. Abra `http://192.168.4.1`  
4. URL: `https://veu.ch8ai.com.br` + cole o token  
5. Reinicia → sync a cada ~15 s  

## API do kernel

| Método | Path | Auth |
|--------|------|------|
| GET | `/device/esp32/board` | sessão |
| POST | `/device/esp32/enroll` | sessão |
| GET | `/device/esp32/state` | Bearer token da placa |
| POST | `/device/esp32/event` | Bearer token |

Eventos: `capture`, `breath` (`guided|semi|free|auto`), `ping`.

## Pinout (referência)

Ver `include/veu_pins.h` — TFT HSPI (12/13/14/15/2/21), touch VSPI (36/32/39/25/33), RGB (4/16/17), SD (19/23/18/5), LDR 34.
