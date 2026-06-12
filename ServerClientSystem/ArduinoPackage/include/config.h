#pragma once

// ===== Wi-Fi =====
#define WIFI_SSID       "YOUR_SSID"
#define WIFI_PASSWORD   "YOUR_PASSWORD"

// ===== Flask server =====
// e.g. "http://192.168.1.42:5000/tags"
#define SERVER_URL      "http://GNELTS00014685.local:5000/tags"

// ===== Camera tuning =====
// Lower resolution = faster AprilTag processing.
// QVGA (320x240) is a good starting point on ESP32-S3.
#define CAM_FRAMESIZE   FRAMESIZE_QVGA
#define CAM_PIXFORMAT   PIXFORMAT_GRAYSCALE   // AprilTag needs grayscale

// ===== AprilTag =====
#define APRILTAG_DECIMATE   2.0f   // Higher = faster, less accurate
#define APRILTAG_SIGMA      0.0f
#define APRILTAG_THREADS    1

// ===== Queue =====
#define TAG_QUEUE_LENGTH    10

// ===== ESP32-S3-CAM (Freenove / AI-Thinker S3) pin map =====
// This is for Freenove ESP32-S3 WROOM CAM, check and adjust
#define PWDN_GPIO_NUM   -1
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM   15
#define SIOD_GPIO_NUM   4
#define SIOC_GPIO_NUM   5
#define Y2_GPIO_NUM     11
#define Y3_GPIO_NUM     9
#define Y4_GPIO_NUM     8
#define Y5_GPIO_NUM     10
#define Y6_GPIO_NUM     12
#define Y7_GPIO_NUM     18
#define Y8_GPIO_NUM     17
#define Y9_GPIO_NUM     16
#define VSYNC_GPIO_NUM  6
#define HREF_GPIO_NUM   7
#define PCLK_GPIO_NUM   13