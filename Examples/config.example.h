// PLACE THIS IN ../NFCSystem/include/config.h

#pragma once

#include <Arduino.h>

// Network config
constexpr const char* WIFI_SSID = "your-ssid";
constexpr const char* WIFI_PASS = "your-password";   // "" for an open network

// Scanner endpoint (HTTPS on the WRITE port, 5000).
// Scans are writes, so they go to the encrypted write listener via WiFiClientSecure.
// Use the hostname the cert was issued for (see SERVER_CERT below) - not an IP,
// since the self-signed cert is valid for hostnames only. (The dashboard/reads
// live separately on the plaintext HTTP read port 5001.)
constexpr const char* SERVER_URL = "https://[SERVER NAME]:5000/scan";

// Must match NFC_API_KEY in the server's .env (see serverSystem.py)
constexpr const char* API_KEY = "your-key-here";

// Server's self-signed cert (cert.pem), pinned by the firmware via setCACert().
// Paste the full PEM here. Because the cert is pinned, regenerating it on the
// server (hostname change, or the ~10-year expiry) means reflashing the scanners.
constexpr const char* SERVER_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
                  <---- paste the contents of the server's cert.pem here
-----END CERTIFICATE-----
)EOF";

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
