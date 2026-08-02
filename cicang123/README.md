# 磁场缺陷检测系统

这是一个可部署到腾讯云 CloudBase Run 的磁场监测与缺陷检测 Web 服务。

## 项目功能

本项目以一个 Python Web 服务为核心，提供以下能力：

- 通过 `1.html` 提供磁场监测前端界面；
- 通过 HTTP 和 Socket.IO 接收磁场传感器数据；
- 将实时磁场数据广播给已连接的浏览器；
- 使用 `sensor_cnn/web/plate_model.onnx` 进行 ONNX 模型推理；
- 提供 CloudBase Run 可用的健康检查接口。

浏览器端会把缺陷检测请求发送到后端 `/predict` 接口，由后端统一执行模型推理。当前版本不在浏览器中运行 ONNX 模型，也不保留浏览器端备用缺陷检测逻辑。

云端运行时不依赖树莓派托管、Cloudflare Tunnel、ngrok、串口、本地模型服务、浏览器端模型执行或本地训练脚本。

## 运行文件

```text
.
├── app.py                         # Flask + Socket.IO + ONNX 推理服务
├── 1.html                         # Web 磁场监测界面
├── sensor_cnn/web/plate_model.onnx # 运行时 ONNX 模型
├── requirements.txt               # Python 运行依赖
├── Dockerfile                     # CloudBase Run 容器配置
├── cloudbaserc.json               # 可选的 CloudBase Framework 配置
├── deploy-cloudbase.ps1           # 直接部署到 CloudBase Run 的脚本
├── CLOUDBASE.md                   # CloudBase 部署与排障说明
├── CiChang2_BLE.ino               # 可选 ESP32 BLE 固件参考
└── cichang_double2.0(1).ino       # 可选 ESP32 双传感器固件参考
```

## 本地运行

```powershell
pip install -r requirements.txt
$env:PORT='8080'
python app.py
```

启动后访问：

```text
http://127.0.0.1:8080/
http://127.0.0.1:8080/healthz
http://127.0.0.1:8080/health
```

## 部署到 CloudBase Run

服务默认使用 `8080` 端口，已按腾讯云 CloudBase Run 容器运行方式配置。

```powershell
.\deploy-cloudbase.ps1
```

等价命令：

```powershell
tcb.cmd cloudrun deploy -e xingya-d7guuazahac96fea3 -s magnetic-detection --source . --port 8080 --force
```

控制台设置、公开访问和常见问题请查看 `CLOUDBASE.md`。

## 接口

```text
GET  /                    Web 前端界面
GET  /healthz             进程存活检查
GET  /health              ONNX 模型就绪检查
GET  /api/status          运行状态
POST /api/magnetic_data   接收磁场数据并广播
POST /predict             执行缺陷预测
```

传感器数据上报示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8080/api/magnetic_data `
  -ContentType 'application/json' `
  -Body '{"x":0.12,"y":0.34,"z":0.56,"device":"ESP32"}'
```

缺陷预测示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8080/predict `
  -ContentType 'application/json' `
  -Body '{"sensor_data":[0.12,0.34,0.56,0.13,0.35,0.57,0.11,0.33,0.55],"confidence_threshold":0.3}'
```

## 代码清理记录

为适配 CloudBase 部署，项目已移除以下非运行时代码：

- 独立推理服务 `server.py`；
- 树莓派管理脚本 `magnetic_system.sh`；
- `app.py` 中的本地串口接收与模拟器代码；
- `sensor_cnn/src` 下的训练、评估、压缩源码；
- `sensor_cnn/scripts` 下的训练辅助脚本；
- `sensor_cnn/models` 下未使用的训练权重和报告；
- `sensor_cnn/web` 下未使用的浏览器端模型变体和检测封装；
- 重复或过期的 Markdown 文档；
- Python 字节码缓存目录。

保留 `CiChang2_BLE.ino` 和 `cichang_double2.0(1).ino`，因为前端仍支持浏览器侧蓝牙、ESP32 网络连接以及名为 `cichang` 的设备流程。
