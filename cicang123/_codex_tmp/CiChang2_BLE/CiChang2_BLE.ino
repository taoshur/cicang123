#include <Arduino.h>
#include <Adafruit_MLX90393.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Wire.h>

// BLE 服务和特征 UUID
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

// BLE 对象
BLEServer *pServer = NULL;
BLECharacteristic *pCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

// 心跳包相关
unsigned long lastHeartbeat = 0;
const unsigned long heartbeatInterval = 5000; // 5秒发送一次心跳包

// 传感器读取节流
unsigned long lastSensorRead = 0;
const unsigned long sensorReadInterval = 200; // 200ms读取一次传感器

Adafruit_MLX90393 sensor;

// 串口2引脚定义  GPIO16(RX)和GPIO17(TX)
#define SERIAL2_RX 16
#define SERIAL2_TX 17

// 可配置参数
float threshold = 1;
const char* BT_NAME = "cichang";

// 数据缓冲区
char dataBuffer[128];
char dataBuffer2[128];

String serial2Input = "";
bool shouldSendData = false;

// 空磁场
float empty_y_min = 3.1;
float empty_y_max = 3.345;
float empty_z_min = -0.756;
float empty_z_max = -0.516;
// 正常钢丝磁场
float normal_y_min = 3.214;
float normal_y_max = 3.462;
float normal_z_min = -0.696;
float normal_z_max = -0.415;
// 断裂磁场
float fracture_y_min = 3.001;
float fracture_y_max = 3.252;
float fracture_z_min = -0.515;
float fracture_z_max = -0.388;

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      Serial.println("[BLE] 设备已连接");
    };

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      Serial.println("[BLE] 设备已断开连接");
      delay(100);
      pServer->startAdvertising();
      Serial.println("[BLE] 重新开始广播");
    }
};

class MyCharacteristicCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxData = pCharacteristic->getValue();
      if (rxData.length() > 0) {
        Serial.print("[BLE] 收到数据: ");
        Serial.println(rxData);
      }
    }
};

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial2.begin(115200, SERIAL_8N1, SERIAL2_RX, SERIAL2_TX);
  delay(500);

  Serial.println("\n========== 系统初始化开始 ==========");
  Serial.println("[SETUP] 初始化BLE...");

  BLEDevice::init(BT_NAME);
  BLEDevice::setMTU(517);

  pServer = BLEDevice::createServer();
  if (!pServer) {
    Serial.println("[ERROR] 创建BLE服务器失败");
    return;
  }
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);
  if (!pService) {
    Serial.println("[ERROR] 创建BLE服务失败");
    return;
  }

  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      BLECharacteristic::PROPERTY_READ |
                      BLECharacteristic::PROPERTY_NOTIFY |
                      BLECharacteristic::PROPERTY_WRITE
                    );
  if (!pCharacteristic) {
    Serial.println("[ERROR] 创建BLE特征失败");
    return;
  }
  pCharacteristic->setCallbacks(new MyCharacteristicCallbacks());
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  if (!pAdvertising) {
    Serial.println("[ERROR] 获取BLE广播对象失败");
    return;
  }

  BLEAdvertisementData advertisementData;
  advertisementData.setName(BT_NAME);
  advertisementData.setCompleteServices(BLEUUID(SERVICE_UUID));
  pAdvertising->setAdvertisementData(advertisementData);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMaxPreferred(0x12);

  BLEDevice::startAdvertising();
  Serial.println("[BLE] 广播已启动");
  Serial.print("[BLE] 设备名称: ");
  Serial.println(BT_NAME);
  Serial.print("[BLE] 服务UUID: ");
  Serial.println(SERVICE_UUID);

  Serial.println("[SETUP] 初始化传感器...");
  if (!sensor.begin_I2C()) {
    Serial.println("[ERROR] 未找到MLX90393传感器!");
    delay(1000);
  } else {
    Serial.println("[SENSOR] MLX90393传感器已连接");
  }

  sensor.setGain(MLX90393_GAIN_3X);
  sensor.setResolution(MLX90393_X, MLX90393_RES_17);
  sensor.setResolution(MLX90393_Y, MLX90393_RES_17);
  sensor.setResolution(MLX90393_Z, MLX90393_RES_17);
  sensor.setOversampling(MLX90393_OSR_3);
  sensor.setFilter(MLX90393_FILTER_5);

  Serial.println("[SETUP] 系统初始化完成");
  Serial2.println("Serial2初始化完成");

  delay(2000);

  Serial.println("[CALIBRATION] 开始校准传感器...");
  const int sampleDuration = 3000;
  const unsigned long startTime = millis();
  int sampleCount = 0;
  float sum_x = 0, sum_y = 0, sum_z = 0;
  float X = 0, Y = 0, Z = 0;

  while (millis() - startTime < sampleDuration) {
    if (sensor.readData(&X, &Y, &Z)) {
      sum_x += X;
      sum_y += Y;
      sum_z += Z;
      sampleCount++;
    }
    delay(200);
  }

  if (sampleCount > 0) {
    float avg_x = sum_x / sampleCount;
    float avg_y = sum_y / sampleCount;
    float avg_z = sum_z / sampleCount;
    float x_mT = avg_x / 1000.0f;
    float y_mT = avg_y / 1000.0f;
    float z_mT = avg_z / 1000.0f;

    float jiao = -(normal_y_min + 0.1 - y_mT);
    float jiao2 = -(normal_z_min + 0.1 - z_mT);

    empty_y_min += jiao;
    empty_y_max += jiao;
    empty_z_min += jiao2;
    empty_z_max += jiao2;
    normal_y_min += jiao;
    normal_y_max += jiao;
    normal_z_min += jiao2;
    normal_z_max += jiao2;
    fracture_y_min += jiao;
    fracture_y_max += jiao;
    fracture_z_min += jiao2;
    fracture_z_max += jiao2;

    snprintf(dataBuffer, sizeof(dataBuffer), "[CALIBRATION] 校准值=%.3f,%.3f", jiao, jiao2);
    Serial.println(dataBuffer);

    snprintf(dataBuffer, sizeof(dataBuffer), "[CALIBRATION] 空:min:%.3f,max:%.3f", empty_y_min, empty_y_max);
    Serial.println(dataBuffer);

    snprintf(dataBuffer, sizeof(dataBuffer), "[CALIBRATION] 正常:min:%.3f,max:%.3f", normal_y_min, normal_y_max);
    Serial.println(dataBuffer);

    snprintf(dataBuffer, sizeof(dataBuffer), "[CALIBRATION] 断裂:min:%.3f,max:%.3f", fracture_y_min, fracture_y_max);
    Serial.println(dataBuffer);
  }

  Serial.println("========== 系统初始化完成 ==========\n");
  lastHeartbeat = millis();
}

void loop() {
  unsigned long currentMillis = millis();

  while (Serial2.available()) {
    char c = Serial2.read();
    serial2Input += c;
    if (serial2Input.endsWith("123")) {
      shouldSendData = true;
      serial2Input = "";
    }
  }

  if (deviceConnected != oldDeviceConnected) {
    if (deviceConnected) {
      Serial.println("[BLE] 客户端已连接");
      snprintf(dataBuffer2, sizeof(dataBuffer2), "连接成功\n");
      pCharacteristic->setValue(dataBuffer2);
      pCharacteristic->notify();
    } else {
      Serial.println("[BLE] 客户端已断开");
    }
    oldDeviceConnected = deviceConnected;
  }

  if (currentMillis - lastSensorRead >= sensorReadInterval) {
    lastSensorRead = currentMillis;

    float X, Y, Z;
    if (sensor.readData(&X, &Y, &Z)) {
      float x_mT = X / 1000.0f;
      float y_mT = Y / 1000.0f;
      float z_mT = Z / 1000.0f;

      snprintf(dataBuffer, sizeof(dataBuffer),
               "[SENSOR] X:%.2fmT,Y:%.3fmT,Z:%.3fmT",
               x_mT, y_mT, z_mT);

      snprintf(dataBuffer2, sizeof(dataBuffer2),
               "xyzmT:%.3f,%.3f,%.3f\n",
               x_mT, y_mT, z_mT);

      if (deviceConnected) {
        pCharacteristic->setValue(dataBuffer2);
        pCharacteristic->notify();
        lastHeartbeat = currentMillis;
      }
      Serial.println(dataBuffer);

      if (shouldSendData) {
        Serial2.println(dataBuffer);
        shouldSendData = false;
      }
    } else {
      Serial.println("[SENSOR] 读取传感器数据失败");
    }
  }

  if (deviceConnected && (currentMillis - lastHeartbeat >= heartbeatInterval)) {
    pCharacteristic->setValue("heartbeat\n");
    pCharacteristic->notify();
    lastHeartbeat = currentMillis;
  }

  delay(50);
}