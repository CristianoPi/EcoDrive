#include <WiFi101.h>
#include <WiFiClient.h>
#include <MQUnifiedsensor.h>
#include <Wire.h>
#include <MPU9250_asukiaaa.h>

// MQ-135 defines
#define MQ135PIN A1
#define R0_PRECISION 100
#define RatioMQ135CleanAir 3.6

// WiFi credentials
const char* ssid = "Galaxy s21 fe ";
const char* password = "cristianO";

// ThingsBoard endpoint
const char* thingsboardServer = "demo.thingsboard.io";
const char* thingsboardPath   = "/api/v1/vw0z24ecehijr8ad5ji1/telemetry";

// MQ-135 sensor
MQUnifiedsensor MQ135("MKR1000", 5, 10, MQ135PIN, "MQ-135");

// MPU9250 (asukiaaa library)
MPU9250_asukiaaa mpu;

// Wire-based GPS variables
float latitudine;
float longitudine;

WiFiClient client;

void setup() {
  if (Serial) {
    Serial.begin(9600);
  }

  // Initialize I2C
  Wire.begin();

  // Check for WiFi shield
  if (WiFi.status() == WL_NO_SHIELD) {
    Serial.println("WiFi shield not present! Check your MKR1000 and library.");
    while (true) {}
  }

  // Connect to WiFi
  WiFi.begin(ssid, password);
  int wifi_attempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifi_attempts < 20) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
    wifi_attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Connected to WiFi");
  } else {
    Serial.println("Failed to connect to WiFi");
    while (true) {}
  }

  // Initialize MQ-135
  MQ135.setRegressionMethod(1);
  MQ135.init();
  Serial.print("Calibrating MQ-135, please wait...");
  float calcR0 = 0;
  for (int i = 1; i <= R0_PRECISION; i++) {
    MQ135.update();
    calcR0 += MQ135.calibrate(RatioMQ135CleanAir);
    Serial.print(".");
  }
  MQ135.setR0(calcR0 / R0_PRECISION);
  Serial.println(" done!");

  if (isinf(calcR0)) {
    Serial.println("Warning: Connection issue (open circuit). Check wiring.");
    while (true) {}
  }
  if (calcR0 == 0) {
    Serial.println("Warning: Connection issue (short to ground). Check wiring.");
    while (true) {}
  }

  // Initialize MPU9250
  mpu.setWire(&Wire);
  mpu.beginAccel();
  mpu.beginGyro();
  mpu.beginMag();

  // Quick check for MPU bytes
  delay(200);
  mpu.accelUpdate();
  if (mpu.accelX() == 0 && mpu.accelY() == 0 && mpu.accelZ() == 0) {
    Serial.println("Warning: MPU9250 readings are zero. Check sensor connections.");
  } else {
    Serial.println("MPU9250_asukiaaa initialized successfully.");
  }

  Serial.println("Setup complete.");
}

void loop() {
  // Read from MQ-135
  MQ135.update();
  MQ135.setA(110.47);
  MQ135.setB(-2.862);
  float CO2 = MQ135.readSensor();

  // Read from MPU9250
  mpu.accelUpdate();
  float accelX = mpu.accelX();
  float accelY = mpu.accelY();
  float accelZ = mpu.accelZ();

  // Read latitudine/longitudine from I2C slave (address 7)
  Wire.requestFrom(7, 8);
  if (Wire.available() == 8) {
    Wire.readBytes((char*)&latitudine, sizeof(latitudine));
    Wire.readBytes((char*)&longitudine, sizeof(longitudine));
  } else {
    Serial.println("Warning: Failed to read GPS data from I2C.");
  }

  // Output data locally
  Serial.print("CO2: ");
  Serial.print(CO2, 2);
  Serial.print(" ppm | AccelX: ");
  Serial.print(accelX, 3);
  Serial.print(" | AccelY: ");
  Serial.print(accelY, 3);
  Serial.print(" | AccelZ: ");
  Serial.print(accelZ, 3);
  Serial.print(" | Lat: ");
  Serial.print(latitudine, 6);
  Serial.print(" | Long: ");
  Serial.println(longitudine, 6);

  // Send data to ThingsBoard
  sendDataToThingsBoard(CO2, accelX, accelY, accelZ, String(latitudine, 6), String(longitudine, 6));

  // Collect data every second
  delay(1000);
}

void sendDataToThingsBoard(float CO2, float ax, float ay, float az, String lat, String lon) {
  if (lat == "0.000000" && lon == "0.000000") {
    Serial.println("Warning: GPS coordinates are zero. Data will not be sent to ThingsBoard.");
    return;
  }

  if (client.connect(thingsboardServer, 80)) {
    String jsonPayload = "{\"CO2\":" + String(CO2, 2) + 
                         ",\"accelX\":" + String(ax, 3) + 
                         ",\"accelY\":" + String(ay, 3) + 
                         ",\"accelZ\":" + String(az, 3) + 
                         ",\"latitude\":" + lat + 
                         ",\"longitude\":" + lon + "}";

    client.println("POST " + String(thingsboardPath) + " HTTP/1.1");
    client.println("Host: " + String(thingsboardServer));
    client.println("Content-Type: application/json");
    client.println("Content-Length: " + String(jsonPayload.length()));
    client.println();
    client.println(jsonPayload);

    long timeout = millis() + 5000; // wait for 5 seconds max
    while (client.available() == 0) {
      if (timeout - millis() <= 0) {
        Serial.println(">>> Client Timeout !");
        client.stop();
        return;
      }
    }

    while (client.available()) {
      String response = client.readStringUntil('\r');
      // Serial.print("Response: ");
      // Serial.println(response);
    }
    client.stop();
  } else {
    // Serial.println("Failed to connect to ThingsBoard server");
  }
}