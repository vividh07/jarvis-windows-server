#include <DHT.h>

#define DHT_PIN 4
#define PIR_PIN 5
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);

bool presenceDetected = false;
unsigned long lastPresenceTime = 0;
const unsigned long PRESENCE_TIMEOUT = 30000; // 30 seconds

void setupSensors() {
  dht.begin();
  pinMode(PIR_PIN, INPUT);
}

float getTemperature() {
  float temp = dht.readTemperature();
  if (isnan(temp)) return -999;
  return temp;
}

float getHumidity() {
  float hum = dht.readHumidity();
  if (isnan(hum)) return -999;
  return hum;
}

bool checkPresence() {
  int pirState = digitalRead(PIR_PIN);
  
  if (pirState == HIGH) {
    presenceDetected = true;
    lastPresenceTime = millis();
  } else {
    if (millis() - lastPresenceTime > PRESENCE_TIMEOUT) {
      presenceDetected = false;
    }
  }
  
  return presenceDetected;
}

String getSensorJSON() {
  float temp = getTemperature();
  float hum = getHumidity();
  bool presence = checkPresence();
  
  String json = "{";
  json += "\"type\":\"sensor_data\",";
  json += "\"temperature\":" + String(temp) + ",";
  json += "\"humidity\":" + String(hum) + ",";
  json += "\"presence\":" + String(presence ? "true" : "false");
  json += "}";
  
  return json;
}