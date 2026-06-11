#include <WiFi.h>
#include <HTTPClient.h>

// Wi-Fi Configuration
const char* ssid = "Your_Network_Name";
const char* password = "Your_Network_Password";
const char* serverUrl = "http://127.0.0.1:5000/scan"; # LocalHost

// Create a thread-safe Queue handle
QueueHandle_t tagQueue;
const int QUEUE_SIZE = 10; // Holds up to 10 scanned IDs if network lags

void setup() {
  Serial.begin(115200);

  // 1. Initialize Wi-Fi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi Connected!");

  // 2. Create the Queue (allocates memory for integers)
  tagQueue = xQueueCreate(QUEUE_SIZE, sizeof(int));
  if (tagQueue == NULL) {
    Serial.println("Error creating the queue!");
  }

  // 3. Spin up the Background Network Task on Core 0
  xTaskCreatePinnedToCore(
    networkTaskWorker,   // Function that implements the task
    "NetworkTask",       // Name of the task
    8192,                // Stack size in bytes (HTTP needs plenty of stack)
    NULL,                // Task input parameter
    1,                   // Priority of the task
    NULL,                // Task handle
    0                    // Core ID (0 = Background/Wi-Fi Core)
  );

  // 4. Initialize your Camera and AprilTag configurations here...
  // (Freenove camera setup code goes here)
}

// --- CORE 1: MAIN CAMERA LOOP ---
void loop() {
  // Simulating your camera capturing a frame and processing AprilTags...
  int detectedTagId = -1; 
  bool tagFound = false;

  // pretend your camera logic runs here and sets tagFound = true;
  
  if (tagFound) {
    // Drop the ID into the queue. 
    // The '0' parameter means "don't wait if the queue is full—keep scanning!"
    if (xQueueSend(tagQueue, &detectedTagId, 0) == pdPASS) {
      Serial.printf("[Core 1] Tag %d queued successfully.\n", detectedTagId);
    } else {
      Serial.println("[Core 1] Queue full! Dropping packet to prevent lag.");
    }
  }

  // Because the network code isn't here, this loop repeats instantly.
  // Yield slightly to let the system handle internal camera interrupts
  delay(1); 
}

// --- CORE 0: ASYNCHRONOUS NETWORK WORKER ---
void networkTaskWorker(void * pvParameters) {
  int receivedTagId;

  // Infinite loop running independently on Core 0
  for(;;) {
    // portMAX_DELAY tells the chip to "sleep" this task efficiently 
    // until an item actually appears in the queue. Zero CPU waste.
    if (xQueueReceive(tagQueue, &receivedTagId, portMAX_DELAY) == pdPASS) {
      Serial.printf("[Core 0] Processing network dispatch for Tag: %d\n", receivedTagId);

      if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        http.begin(serverUrl);
        http.addHeader("Content-Type", "application/json");

        String jsonPayload = "{\"tag_id\":" + String(receivedTagId) + "}";
        
        // This line blocks Core 0, but Core 1 is still processing video frames!
        int httpResponseCode = http.POST(jsonPayload); 
        
        if (httpResponseCode == 200) {
          Serial.println("[Core 0] Server acknowledged upload.");
        } else {
          Serial.printf("[Core 0] Upload failed. HTTP Code: %d\n", httpResponseCode);
        }
        http.end();
      } else {
        Serial.println("[Core 0] Wi-Fi lost. Cannot upload packet.");
      }
    }
  }
}