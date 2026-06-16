/*
 * Cart Tracker - NFC Scanner Station
 * 
 * Hardware: ESP32-WROOM-32 + PN532 (I2C) + KY-006 buzzer
 * 
 * Wiring:
 *   PN532 VCC -> ESP32 3V3
 *   PN532 GND -> ESP32 GND
 *   PN532 SDA -> ESP32 GPIO 21
 *   PN532 SCL -> ESP32 GPIO 22
 *   KY-006 S  -> ESP32 GPIO 25
 *   KY-006 -  -> ESP32 GND
 *   KY-006 middle pin -> 3V3 (if labeled VCC) or leave NC
 * 
 * PN532 DIP switches: 1=OFF, 2=ON  (I2C mode)
 */

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_PN532.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

#include "config.h"

// PN532 over I2C - no SS or IRQ pins
Adafruit_PN532 nfc(-1, -1);

// Debounce state for repeated scans of the same tag
String   lastUid     = "";
uint32_t lastUidTime = 0;

// ============================================================
// Buzzer feedback patterns
// ============================================================
void beepTone(int freqHz, int durationMs) {
  tone(BUZZER_PIN, freqHz, durationMs);
  delay(durationMs + 20);
  noTone(BUZZER_PIN);
}

void beepScanned() {
  // Quick chirp - card detected
  beepTone(1500, 50);
}

void beepSuccess() {
  // Two-tone rising - server accepted the scan
  beepTone(2000, 80);
  delay(60);
  beepTone(2800, 100);
}

void beepUnknown() {
  // Two low buzzes - tag UID not recognized by server
  beepTone(400, 250);
  delay(150);
  beepTone(400, 250);
}

void beepNetworkError() {
  // Three short low beeps - couldn't reach server
  for (int i = 0; i < 3; i++) {
    beepTone(300, 120);
    delay(80);
  }
}

void beepBootHappy() {
  beepTone(1000, 60);
  beepTone(1500, 60);
  beepTone(2200, 100);
}

void beepBootFailLoop() {
  // Two-tone siren forever - signals hardware problem
  while (true) {
    beepTone(800, 200);
    delay(200);
    beepTone(400, 200);
    delay(800);
  }
}

// ============================================================
// WiFi
// ============================================================
void connectWiFi() {
  Serial.printf("Connecting to WiFi '%s'", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  if (strlen(WIFI_PASS) == 0)
  {
    WiFi.begin(WIFI_SSID);
    Serial.print(" Warning: Open Network");
  } else 
  {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
  }

  
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n  Connected. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n  Failed - will retry in main loop");
  }
}

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  static uint32_t lastAttempt = 0;
  if (millis() - lastAttempt < WIFI_RETRY_INTERVAL_S * 1000UL) return;

  lastAttempt = millis();
  Serial.println("WiFi disconnected - reconnecting...");
  WiFi.disconnect();
  WiFi.reconnect();
}

// ============================================================
// Send scan to server
// Returns HTTP status code, or -1 on local failure
// ============================================================
int sendScanToServer(const String& uid) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("  No WiFi - cannot send");
    return -1;
  }

WiFiClientSecure client;
client.setCACert(SERVER_CERT);
  
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(client, SERVER_URL)) {
    Serial.println("  http.begin() failed");
    return -1;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);

  JsonDocument doc;
  doc["uid"]      = uid;
  doc["location"] = SCANNER_LOCATION;
  String payload;
  serializeJson(doc, payload);

  Serial.printf("  POST %s\n  Payload: %s\n", SERVER_URL, payload.c_str());

  int code = http.POST(payload);
  String response = http.getString();
  http.end();

  Serial.printf("  Server: %d  %s\n", code, response.c_str());
  return code;
}

// ============================================================
// Helpers
// ============================================================
String uidToHexString(const uint8_t* uid, uint8_t len) {
  String s;
  s.reserve(len * 2);
  for (uint8_t i = 0; i < len; i++) {
    if (uid[i] < 0x10) s += "0";
    s += String(uid[i], HEX);
  }
  s.toUpperCase();
  return s;
}

// ============================================================
// Setup
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n========================================");
  Serial.println(" Cart Tracker - NFC Scanner Station");
  Serial.printf ( " Location: %s\n", SCANNER_LOCATION);
  Serial.println("========================================");

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // PN532 over I2C
  Wire.begin(SDA_PIN, SCL_PIN);
  nfc.begin();

  uint32_t version = nfc.getFirmwareVersion();
  if (!version) {
    Serial.println("ERROR: PN532 not found.");
    Serial.println("  Check wiring (SDA=21, SCL=22, VCC=3V3, GND=GND)");
    Serial.println("  Check DIP switches: 1=OFF, 2=ON for I2C mode");
    beepBootFailLoop();  // never returns
  }
  Serial.printf("PN532 firmware: 0x%08X\n", version);
  nfc.SAMConfig();

  connectWiFi();

  beepBootHappy();
  Serial.println("Ready. Scan a tag.\n");
}

// ============================================================
// Main loop
// ============================================================
void loop() {
  ensureWiFi();

  uint8_t uid[7];
  uint8_t uidLen;

  // Short timeout keeps loop responsive
  bool found = nfc.readPassiveTargetID(
    PN532_MIFARE_ISO14443A, uid, &uidLen, 100
  );

  if (!found) {
    delay(SCAN_INTERVAL_MS);
    return;
  }

  String uidStr = uidToHexString(uid, uidLen);
  uint32_t now = millis();

  // Debounce: ignore same tag rescanned within window
  if (uidStr == lastUid && (now - lastUidTime) < DEBOUNCE_SAME_TAG_MS) {
    delay(SCAN_INTERVAL_MS);
    return;
  }
  lastUid     = uidStr;
  lastUidTime = now;

  Serial.printf("Tag detected: UID=%s\n", uidStr.c_str());
  beepScanned();  // immediate feedback that the read worked

  int code = sendScanToServer(uidStr);

  if (code == 200) {
    beepSuccess();
    Serial.println("  -> Recorded\n");
  } else if (code == 400 || code == 404) {
    beepUnknown();
    Serial.println("  -> Unknown tag\n");
  } else if (code == 401 || code == 403) {
    beepNetworkError();
    Serial.println("  -> Auth rejected (check API_KEY)\n");
  } else {
    beepNetworkError();
    Serial.println("  -> Network/server error\n");
  }

  delay(SCAN_INTERVAL_MS);
}