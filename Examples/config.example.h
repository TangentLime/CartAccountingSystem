// PLACE THIS IN ../NFCSystem/include/config.h

#pragma once

#include <Arduino.h>

// Network config
constexpr const char* WIFI_SSID = "your-ssid";
constexpr const char* WIFI_PASS = "your-password";   // "" for an open network

// Scanner endpoint (plaintext HTTP on the scanner port, 5001).
// The ESP32 talks to the scanner listener over HTTP via WiFiClient - no TLS.
// Use the server's hostname or IP; the scanner port is 5001 (dashboard is 5000/HTTPS).
constexpr const char* SERVER_URL = "http://[SERVER NAME]:5001/scan";

// Must match NFC_API_KEY in the server's .env (see serverSystem.py)
constexpr const char* API_KEY = "your-key-here";

// NOTE: SCANNER_LOCATION is NOT set here. It is injected at build time by
// PlatformIO build_flags, one per environment (see NFCSystem/platformio.ini):
//   pio run -e jp  -t upload   ->  "Jurassic Park"
//   pio run -e jit -t upload   ->  "JIT"
//   pio run -e mal -t upload   ->  "MAL"
// The value must be one of the server's Locale strings.

// Pin assignments
constexpr uint8_t SDA_PIN    = 21;
constexpr uint8_t SCL_PIN    = 22;
constexpr uint8_t BUZZER_PIN = 25;

// Behavior tuning
constexpr uint16_t SCAN_INTERVAL_MS      = 200;    // delay between PN532 polls
constexpr uint16_t DEBOUNCE_SAME_TAG_MS  = 3000;   // ignore same UID re-scanned within this window
constexpr uint16_t HTTP_TIMEOUT_MS       = 4000;
constexpr uint16_t WIFI_RETRY_INTERVAL_S = 30;
constexpr uint16_t WIFI_CONNECT_TIMEOUT_MS = 20000;
