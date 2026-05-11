# 磁场监测系统

## 快速开始

### Windows用户
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务器
python app.py
```

### 树莓派用户
```bash
# 启动系统（服务器 + ngrok穿透）
bash magnetic_system.sh start

# 或使用菜单模式
bash magnetic_system.sh
```

## 功能特性

### 📊 核心功能
- 实时磁场数据监测（X/Y/Z三轴）
- 二阶差分突变检测算法
- WebSocket实时通信
- **支持多种连接方式**：
  - ESP32蓝牙连接
  - ESP32 USB连接（支持多设备）
  - ESP32网络连接（HTTP/WebSocket）
- 数据接收控制（开始/停止接收）
- 数据清空功能

### 📈 数据分析功能
- 实时数据图表展示（Chart.js）
- 多传感器数据切换显示

### 🧠 传感器CNN模型
- 模型加载和测试
- 数据标注功能（8种缺陷类型）：
  - 无缺陷、裂纹、腐蚀、点蚀、划痕、变形、块状、柱状
- 数据采集和模型训练
- 实时验证功能

### 🔌 服务器连接
- WebSocket远程连接
- 树莓派自动扫描和连接
- 自动重连机制

## 文件说明

### 核心文件
| 文件 | 说明 |
|------|------|
| `app.py` | Flask后端服务器（一体化整合版） |
| `1.html` | 前端界面（磁场监测单页面应用） |
| `requirements.txt` | Python依赖列表 |
| `magnetic_system.sh` | 树莓派管理脚本 |
| `server.py` | 模型推理后端服务 |

### 传感器CNN目录
```
sensor_cnn/
├── models/          # 模型文件
│   ├── best_three_sensor.pt
│   ├── best_simple.pt
│   └── single_sensor_model.pth
├── src/             # 源代码
│   ├── train.py              # 训练脚本
│   ├── inference.py          # 推理模块
│   ├── deployment.py         # 部署工具
│   ├── train_from_annotation.py  # 从标注训练
│   └── realtime_validation.py    # 实时验证
├── scripts/         # 训练脚本
└── web/            # Web部署文件
```

### 其他文件
- `CiChang2_BLE.ino` - ESP32蓝牙通信代码
- `项目优化日志.txt` - 优化记录
- `项目技术栈总结.txt` - 技术文档

## 使用方法

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动服务器
```bash
# 基础模式（仅Web界面）
python app.py

# 串口模式（连接ESP32）
python app.py --serial --port COM3

# 网络模拟器模式（测试用）
python app.py --simulator
```

### 3. 树莓派管理脚本
```bash
# 启动系统（服务器 + ngrok穿透）
bash magnetic_system.sh start

# 菜单模式（交互式）
bash magnetic_system.sh
```

### 4. 访问界面
- 本地访问：http://127.0.0.1:5000
- 网络访问：http://<设备IP>:5000
- 公网访问：通过ngrok获取的地址

### 5. 连接设备
1. **选择连接方式**：
   - ESP32蓝牙连接：使用支持Web Bluetooth的浏览器
   - ESP32 USB连接：选择串口端口和波特率
   - ESP32网络连接：输入ESP32的IP地址和端口

2. **点击连接设备按钮**

3. **点击开始接收数据**

### 6. CNN模型使用
1. 点击"加载CNN模型"按钮
2. 选择数据采集模式（平板模式/管道模式）
3. 开始数据采集和标注
4. 启动模型训练

## 系统架构

### 前端技术
- **Chart.js** - 数据图表展示
- **Socket.IO** - WebSocket实时通信
- **HTML5/CSS3** - 界面布局和样式
- **原生JavaScript** - 应用逻辑

### 后端技术
- **Flask** - Web框架
- **Flask-SocketIO** - WebSocket支持
- **PySerial** - 串口通信（可选）
- **Eventlet** - 异步网络库
- **PyTorch** - 深度学习框架
- **ONNX Runtime** - 模型推理

### 部署技术
- **ngrok** - 内网穿透
- **Shell脚本** - 自动化部署

## 常见问题

### 依赖安装失败
```bash
# 创建虚拟环境
python -m venv venv

# Windows激活
venv\Scripts\activate

# Linux/Mac激活
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 端口被占用
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :5000
kill -9 <PID>
```

### ngrok连接失败
```bash
# 检查ngrok配置
ngrok config add-authtoken <your_token>

# 手动测试
ngrok http 5000
```

### 串口连接失败
- 确保ESP32已正确连接
- 检查串口驱动是否安装
- 确认串口编号正确

### 蓝牙连接失败
- 确保浏览器支持Web Bluetooth（Chrome/Edge）
- 确保在HTTPS或localhost环境下运行
- 检查蓝牙设备是否已配对

## 系统要求
- **Python**: 3.7+
- **浏览器**: Chrome 89+ / Edge 89+ / Opera 75+ / Firefox 85+
- **硬件**: ESP32开发板
- **树莓派**: 3B+或更高（推荐）

## 更新日志

### 最新更新
- ✅ 支持ESP32多种连接方式（蓝牙/USB/网络）
- ✅ 集成传感器CNN模型训练和推理
- ✅ 支持8种缺陷类型数据标注
- ✅ 添加数据接收控制功能
- ✅ 添加WebSocket远程连接

### 历史更新
- 添加实时磁场数据监测
- 实现二阶差分突变检测算法
- 添加WebSocket实时通信
- 添加网络模拟器功能