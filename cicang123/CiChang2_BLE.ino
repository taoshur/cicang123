#include <Arduino.h>
#include <WiFi.h>
#include <WiFiServer.h>         // WiFi相关库（实现STA模式连接热点+TCP服务器）
#include <Wire.h>               // I2C通信库（驱动MLX90393传感器）
#include <Adafruit_MLX90393.h>  // 磁场传感器驱动库
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLECharacteristic.h>
#include <BLE2902.h>  // BLE蓝牙低功耗库

// ====================== 硬件引脚宏定义 ======================
// 硬件串口2的收发引脚（用于外接模块通信）
// #define SERIAL2_RX 16
// #define SERIAL2_TX 17

// 双路MLX90393传感器的I2C地址
#define MLX_ADDR 0x0C  // 传感器 I2C地址
// 传感器1：I2C0 (默认引脚 SDA=21, SCL=22)
#define I2C1_SDA 21
#define I2C1_SCL 22
// 传感器2：I2C1 (自定义引脚 SDA=18, SCL=19)
#define I2C2_SDA 18
#define I2C2_SCL 19

// ====================== WiFi通信参数配置 ======================
const char* wifi_ssid = "vivo X100s";     // 连接的WiFi名称（手机热点）
const char* wifi_password = "LQJ666666";  // WiFi密码
WiFiServer wifiServer(8888);              // 原有TCP服务器，端口号8888（树莓派用）
WiFiClient wifiClient;                    // TCP客户端对象（树莓派/电脑连接）

// ====================== HTTP网页服务器配置（适配网页要求） ======================
WiFiServer httpServer(80);                // HTTP服务器，标准80端口
WiFiClient httpClient;                    // HTTP客户端对象
// ============================================================================

// ====================== BLE蓝牙参数配置 ======================
#define BLE_DEVICE_NAME "Dual_MLX90393"  // BLE蓝牙设备名称（手机搜索显示）
// BLE服务UUID（固定值，手机APP识别通信服务）
#define SERVICE_UUID "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
// BLE特征值UUID（固定值，数据传输通道）
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLEServer* pServer = NULL;                  // BLE服务器对象指针
BLECharacteristic* pCharacteristic = NULL;  // BLE数据传输特征值
bool deviceConnected = false;               // BLE连接状态标志

// ====================== 全局对象/变量定义 ======================
Adafruit_MLX90393 sensor1;  // 传感器1对象
Adafruit_MLX90393 sensor2;  // 传感器2对象
char dataBuffer[120];       // 数据缓冲区：存储拼接后的磁场字符串

// ====================== 开机初始化函数（只运行1次） ======================
void setup() {
  // 1. 初始化串口（用于电脑调试，波特率115200）
  Serial.begin(115200);
  // 初始化硬件串口2，配置波特率+引脚
  // Serial2.begin(115200, SERIAL_8N1, SERIAL2_RX, SERIAL2_TX);

  // 初始化双硬件I2C总线
  Wire.begin(I2C1_SDA, I2C1_SCL);   // I2C0：传感器1
  Wire1.begin(I2C2_SDA, I2C2_SCL);  // I2C1：传感器2

  // 2. BLE蓝牙初始化
  BLEDevice::init(BLE_DEVICE_NAME);                             // 设置蓝牙名称
  pServer = BLEDevice::createServer();                          // 创建BLE服务器
  BLEService* pService = pServer->createService(SERVICE_UUID);  // 创建BLE服务
  // 创建数据特征值，支持通知+只读模式
  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  pCharacteristic->addDescriptor(new BLE2902());  // 添加BLE描述符（必加）
  pService->start();                              // 启动BLE服务
  BLEDevice::startAdvertising();                  // 开启蓝牙广播（手机可搜索）
  Serial.println("BLE蓝牙已启动: " + String(BLE_DEVICE_NAME));

  // 3. WiFi初始化：清理旧连接，防止异常
  Serial.println("清理旧WiFi连接...");
  WiFi.disconnect(true);  // 断开已有连接+清除记忆
  WiFi.mode(WIFI_OFF);    // 临时关闭WiFi
  delay(100);             // 等待稳定
  WiFi.mode(WIFI_STA);    // 设置为STA模式（连接路由器）

  // 连接指定WiFi
  Serial.print("连接 WiFi: ");
  Serial.println(wifi_ssid);
  WiFi.begin(wifi_ssid, wifi_password);

  // 等待WiFi连接成功
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  // WiFi连接成功，打印信息并启动服务器
  Serial.println("\nWiFi 连接成功!");
  Serial.print("ESP32 IP地址: ");
  Serial.println(WiFi.localIP());
  wifiServer.begin();  // 启动原有8888端口TCP服务器
  httpServer.begin();  // 启动80端口HTTP服务器
  Serial.println("HTTP网页服务器已启动，数据接口：http://" + WiFi.localIP().toString() + "/data");

  // 4. 双传感器初始化（同地址0x0C，不同硬件I2C总线）
  if (!sensor1.begin_I2C(MLX_ADDR, &Wire)) {
    Serial.println("未找到传感器 1 (0x0C)!");
    while (1) delay(100);// 传感器异常，卡死报错
  }
  if (!sensor2.begin_I2C(MLX_ADDR, &Wire1)) {
    Serial.println("未找到传感器 2 (0x0C)!");
    while (1) delay(100);
  }

  // 5. 配置双传感器参数
  configSensor(&sensor1);
  configSensor(&sensor2);

  Serial.println("系统初始化完成!");
}

// ====================== 传感器参数配置函数 ======================
// 功能：配置传感器增益、分辨率、滤波参数，提高采集精度
void configSensor(Adafruit_MLX90393* s) {
  s->setGain(MLX90393_GAIN_3X);                   // 设置信号增益（3倍，提升灵敏度）
  s->setResolution(MLX90393_X, MLX90393_RES_17);  // X轴分辨率17位
  s->setResolution(MLX90393_Y, MLX90393_RES_17);  // Y轴分辨率17位
  s->setResolution(MLX90393_Z, MLX90393_RES_17);  // Z轴分辨率17位
  s->setOversampling(MLX90393_OSR_3);             // 过采样设置（抗干扰）
  s->setFilter(MLX90393_FILTER_5);                // 数字滤波（稳定数据）
}

// ====================== 主循环函数（无限循环运行） ======================
void loop() {
  // ====================== 优先级最高：处理HTTP请求，适配网页解析 ======================
  if (!httpClient.connected()) {
    httpClient = httpServer.available();
  }

  // 处理HTTP /data 请求，适配网页解析规则
  if (httpClient && httpClient.connected() && httpClient.available()) {
    String request = httpClient.readStringUntil('\n');
    // 匹配GET /data 请求
    if (request.indexOf("GET /data ") >= 0) {
      // 标准HTML网页响应头，100%适配网页解析
      httpClient.println("HTTP/1.1 200 OK");
      httpClient.println("Content-Type: text/html;charset=utf-8");
      httpClient.println("Access-Control-Allow-Origin: *");
      httpClient.println("Cache-Control: no-cache, no-store");
      httpClient.println("Connection: close");
      httpClient.println();
      // 用最简HTML包裹数据，符合网页规范，数据内容完全不变
      httpClient.print("<html><body>");
      httpClient.print(dataBuffer);
      httpClient.print("</body></html>");
    } else {
      httpClient.println("HTTP/1.1 404 Not Found");
      httpClient.println("Content-Type: text/html");
      httpClient.println("Connection: close");
      httpClient.println();
      httpClient.println("<html><body>404 Not Found</body></html>");
    }
    httpClient.stop();
  }
  // ============================================================================

  // 1. 原有TCP客户端监听：如果树莓派断开连接，重新监听连接请求
  if (!wifiClient.connected()) {
    wifiClient = wifiServer.available();
    delay(10);
  }

  // 2. 定义变量，存储传感器原始数据
  float X1, Y1, Z1;                              // 传感器1三轴原始数据
  float X2, Y2, Z2;                              // 传感器2三轴原始数据
  bool read1 = sensor1.readData(&X1, &Y1, &Z1);  // 读取传感器1数据
  bool read2 = sensor2.readData(&X2, &Y2, &Z2);  // 读取传感器2数据

  // 3. 传感器1和传感器2读取成功，处理并发送数据
  if (read1 && read2) {
    // 单位转换：T → mT
    float x1 = X1 / 1000.0f, y1 = Y1 / 1000.0f, z1 = Z1 / 1000.0f;
    float x2 = X2 / 1000.0f, y2 = Y2 / 1000.0f, z2 = Z2 / 1000.0f;

    // 拼接数据格式：S1:x1, y1, z1;S2:x2, y2, z2
    snprintf(dataBuffer, sizeof(dataBuffer),
             "S1:%.3f,%.3f,%.3f;S2:%.3f,%.3f,%.3f\n",
             x1, y1, z1, x2, y2, z2);

    // ====================== 四路数据同步输出（原有功能完全保留） ======================
    Serial.print(dataBuffer);  // 1. 串口输出（电脑调试）
    pCharacteristic->setValue(dataBuffer);
    pCharacteristic->notify();  // 2. BLE蓝牙发送（手机接收）
    // Serial2.print(dataBuffer);         // 3. 串口2输出（外接模块）

    // 4. 原有TCP发送（树莓派接收，8888端口）
    if (wifiClient && wifiClient.connected()) {
      wifiClient.print(dataBuffer);
    }
  } else {
    // 传感器读取失败，打印报错信息
    if (!read1) Serial.println("传感器1读取失败!");
    if (!read2) Serial.println("传感器2读取失败!");
  }

  delay(200);  // 采样间隔200ms（每秒采集5次）
}