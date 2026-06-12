#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_camera.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

// AprilTag library (raspiduino/apriltag-esp32)
extern "C" {
  #include "apriltag.h"
  #include "tag36h11.h"
  #include "common/image_u8.h"
  #include "common/zarray.h"
}

#include "config.h"

// ---------- Inter-core communication ----------
struct TagDetection {
  int     id;
  float   decision_margin;
  uint32_t timestamp_ms;
};

static QueueHandle_t tagQueue = nullptr;

// ---------- Camera init ----------
static bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size   = CAM_FRAMESIZE;
  config.pixel_format = CAM_PIXFORMAT;
  config.grab_mode    = CAMERA_GRAB_LATEST;
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count     = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  return true;
}

// ---------- Wi-Fi ----------
static void connectWiFi() {
  Serial.printf("Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.printf("\nWiFi connected. IP: %s\n", WiFi.localIP().toString().c_str());
}

// ---------- Core 0: Camera + AprilTag ----------
void cameraTask(void *param) {
  Serial.printf("[cameraTask] running on core %d\n", xPortGetCoreID());

  // Set up AprilTag detector once
  apriltag_family_t  *tf = tag36h11_create();
  apriltag_detector_t *td = apriltag_detector_create();
  apriltag_detector_add_family(td, tf);
  td->quad_decimate = APRILTAG_DECIMATE;
  td->quad_sigma    = APRILTAG_SIGMA;
  td->nthreads      = APRILTAG_THREADS;
  td->refine_edges  = 1;

  for (;;) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[cameraTask] frame grab failed");
      vTaskDelay(pdMS_TO_TICKS(50));
      continue;
    }

    // Wrap the camera buffer in an image_u8_t (no copy).
    // Works because we requested PIXFORMAT_GRAYSCALE.
    image_u8_t img = {
      .width  = (int32_t)fb->width,
      .height = (int32_t)fb->height,
      .stride = (int32_t)fb->width,
      .buf    = fb->buf
    };

    zarray_t *detections = apriltag_detector_detect(td, &img);
    int n = zarray_size(detections);

    for (int i = 0; i < n; i++) {
      apriltag_detection_t *det;
      zarray_get(detections, i, &det);

      TagDetection msg;
      msg.id              = det->id;
      msg.decision_margin = det->decision_margin;
      msg.timestamp_ms    = millis();

      // Non-blocking send; drop if queue is full so camera never stalls
      if (xQueueSend(tagQueue, &msg, 0) != pdPASS) {
        // Queue full — network task is behind. Just skip.
      }

      Serial.printf("[cam] tag id=%d margin=%.1f\n",
                    det->id, det->decision_margin);
    }

    apriltag_detections_destroy(detections);
    esp_camera_fb_return(fb);

    // Small yield to keep watchdog happy
    vTaskDelay(pdMS_TO_TICKS(1));
  }

  // Never reached, but for completeness:
  apriltag_detector_destroy(td);
  tag36h11_destroy(tf);
  vTaskDelete(NULL);
}

// ---------- Core 1: Network ----------
void networkTask(void *param) {
  Serial.printf("[networkTask] running on core %d\n", xPortGetCoreID());

  TagDetection msg;
  for (;;) {
    // Block until a detection is queued
    if (xQueueReceive(tagQueue, &msg, portMAX_DELAY) == pdPASS) {

      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[net] WiFi down, attempting reconnect...");
        WiFi.reconnect();
        vTaskDelay(pdMS_TO_TICKS(500));
        continue;
      }

      HTTPClient http;
      http.begin(SERVER_URL);
      http.addHeader("Content-Type", "application/json");
      http.setTimeout(2000);

      char body[128];
      snprintf(body, sizeof(body),
               "{\"id\":%d,\"margin\":%.2f,\"ts\":%lu}",
               msg.id, msg.decision_margin,
               (unsigned long)msg.timestamp_ms);

      int code = http.POST((uint8_t*)body, strlen(body));
      if (code > 0) {
        Serial.printf("[net] POST id=%d -> %d\n", msg.id, code);
      } else {
        Serial.printf("[net] POST failed: %s\n",
                      http.errorToString(code).c_str());
      }
      http.end();
    }
  }
}

// ---------- Setup / loop ----------
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== ESP32-S3-CAM AprilTag streamer ===");

  if (!psramFound()) {
    Serial.println("WARNING: PSRAM not detected!");
  }

  if (!initCamera()) {
    Serial.println("Halting: camera init failed");
    while (true) delay(1000);
  }

  connectWiFi();

  tagQueue = xQueueCreate(TAG_QUEUE_LENGTH, sizeof(TagDetection));
  if (!tagQueue) {
    Serial.println("Failed to create queue");
    while (true) delay(1000);
  }

  // Pin AprilTag work to core 0 — give it a big stack, it allocates a lot.
  xTaskCreatePinnedToCore(
      cameraTask,  "cameraTask",  16384, NULL, 1, NULL, 0);

  // Network on core 1 (Arduino loop also normally lives on core 1, but
  // we leave loop() empty so this is fine).
  xTaskCreatePinnedToCore(
      networkTask, "networkTask", 8192,  NULL, 1, NULL, 1);
}

void loop() {
  // Everything runs in tasks
  vTaskDelay(pdMS_TO_TICKS(1000));
}