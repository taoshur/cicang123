# 腾讯云 CloudBase 部署说明

本项目已整理为单容器服务，可直接部署到腾讯云 CloudBase Run：

- Flask 负责提供 `1.html` 和 `sensor_cnn/web/plate_model.onnx`；
- Flask-SocketIO 负责实时磁场数据通信；
- ONNX Runtime 在同一个 Python 进程中执行模型推理；
- 浏览器前端通过后端 `/predict` 接口进行缺陷检测，不使用浏览器端本地推理；
- 云端模式不需要树莓派托管、串口、Cloudflare Tunnel、ngrok 或独立模型服务。

## CloudBase Run 配置

创建或检查 CloudBase Run 服务时，建议使用以下配置：

| 配置项 | 建议值 |
| --- | --- |
| 服务名称 | `magnetic-detection` |
| 源码目录 | 项目根目录 |
| Dockerfile | `Dockerfile` |
| 容器端口 / 服务端口 | `8080` |
| 启动命令 | 使用 Dockerfile 默认命令 |
| 健康检查路径 | `/healthz` |
| 模型就绪检查路径 | `/health` |
| 内存 | 最低 512 MB，建议 1 GB |

环境变量：

```text
PORT=8080
WEB_PORT=8080
DEPLOY_TARGET=cloudbase-run
MODEL_PATH=sensor_cnn/web/plate_model.onnx
```

## 部署命令

在项目根目录执行：

```powershell
tcb.cmd login
.\deploy-cloudbase.ps1
```

等价的直接部署命令：

```powershell
tcb.cmd cloudrun deploy -e xingya-d7guuazahac96fea3 -s magnetic-detection --source . --port 8080 --force
```

项目中保留了 `cloudbaserc.json`，可用于可选的 CloudBase Framework 部署。不过当前更推荐直接使用 CloudBase Run 部署命令，因为它能避开本地 Framework 插件缓存缺失导致的问题。

## 部署验证

CloudBase 控制台显示部署成功后，访问：

```text
https://your-service-domain/healthz
https://your-service-domain/health
https://your-service-domain/
```

预期结果：

- `/healthz` 返回 HTTP 200，表示 Web 进程已存活；
- `/health` 返回 HTTP 200 且 `model_loaded: true`，表示 ONNX 模型已加载；
- `/` 打开磁场监测前端界面。

## 常见问题

如果执行 `tcb.cmd framework deploy` 时出现：

```text
Cannot find module ... @cloudbase/framework-plugin-container
```

请改用直接部署脚本：

```powershell
.\deploy-cloudbase.ps1
```

如果部署失败并提示云托管资源未开通，请进入 CloudBase 控制台，选择环境 `xingya-d7guuazahac96fea3`，先开通 CloudBase Run / 云托管能力，再重新部署。

## 硬件数据流

CloudBase Run 无法直接访问本地硬件。传感器数据可以通过以下方式进入系统：

- 浏览器通过 Web Bluetooth 直接连接 ESP32；
- 浏览器连接 ESP32 的 HTTP 或 WebSocket 网络端点；
- 固件或其他采集程序主动向云端接口上报数据。

云端上报示例：

```text
POST https://your-service-domain/api/magnetic_data
Content-Type: application/json

{"x": 0.12, "y": 0.34, "z": 0.56, "device": "ESP32"}
```

浏览器会通过 Socket.IO 接收 CloudBase 服务广播的实时磁场数据。
