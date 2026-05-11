"""
磁场监测系统 - 一体化整合版

功能：
1. Flask后端服务器（提供Web界面和WebSocket服务）
2. 串口数据接收器（连接ESP32）
3. 网络磁场模拟器（用于测试）
4. 磁场突变检测算法

使用方法：
- 启动服务器：python app.py
- 启动串口接收器：python app.py --serial --port /dev/ttyUSB0
- 启动网络模拟器：python app.py --simulator

作者：磁场监测系统
日期：2026-03-19
"""

# 先执行eventlet.monkey_patch()，再导入其他模块
try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import datetime
import json
import statistics
import logging
import argparse
import time
import threading
import concurrent.futures
import requests
from datetime import datetime
import random
import math
import socketio
import os

# 条件导入serial模块
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    logging.warning("Serial module not available, serial functionality will be disabled")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
MODEL_PORT = int(os.environ.get('MODEL_PORT', '5001'))
MAX_DATA_HISTORY = 500

data_history = {
    'x': [],
    'y': [],
    'z': []
}


def record_magnetic_data(data):
    try:
        x = float(data.get('x', 0))
        y = float(data.get('y', 0))
        z = float(data.get('z', 0))
    except (TypeError, ValueError, AttributeError):
        return

    data_history['x'].append(x)
    data_history['y'].append(y)
    data_history['z'].append(z)

    if len(data_history['x']) > MAX_DATA_HISTORY:
        data_history['x'].pop(0)
        data_history['y'].pop(0)
        data_history['z'].pop(0)

app = Flask(__name__, template_folder='.')
app.config['SECRET_KEY'] = 'magnetic-monitor-secret-key-2024'
# 针对树莓派4核心CPU优化SocketIO配置
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    ping_timeout=120,  # 增加超时时间，适应网络波动
    ping_interval=20,
    ping_interval_max=40,
    logger=False,  # 关闭SocketIO日志，减少输出
    engineio_logger=False,  # 关闭EngineIO日志，减少输出
    async_mode='eventlet',  # 使用eventlet异步模式
    always_connect=False,  # 不总是保持连接
    http_compression=True,  # 启用HTTP压缩
    websocket_compression=True,  # 启用WebSocket压缩
    max_http_buffer_size=1e8  # 增加缓冲区大小
)




@app.route('/')
def index():
    """Render the main HTML page."""
    return render_template('1.html')


@app.route('/sensor_cnn/<path:filename>')
def serve_sensor_cnn(filename):
    """Serve files from sensor_cnn directory."""
    import os
    try:
        # 获取当前文件所在目录的绝对路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"Current directory: {current_dir}")
        
        # 构建sensor_cnn目录的绝对路径
        sensor_cnn_dir = os.path.join(current_dir, 'sensor_cnn')
        print(f"Sensor CNN directory: {sensor_cnn_dir}")
        
        # 构建文件的绝对路径
        file_path = os.path.join(sensor_cnn_dir, filename)
        print(f"File path: {file_path}")
        
        # 确保文件存在
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return "File not found", 404
        
        # 确保文件在sensor_cnn目录内（安全检查）
        if not file_path.startswith(sensor_cnn_dir):
            print(f"Access denied: {file_path}")
            return "Access denied", 403
        
        # 检查文件权限
        if not os.access(file_path, os.R_OK):
            print(f"Permission denied: {file_path}")
            return "Permission denied", 403
        
        # 发送文件
        directory = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        print(f"Serving file: {file_name} from {directory}")
        return app.send_from_directory(directory, file_name)
    except Exception as e:
        print(f"Error serving file: {e}")
        return f"Error: {str(e)}", 500


@app.route('/health', methods=['GET'])
def proxy_health():
    """Proxy health check to model backend service."""
    try:
        response = requests.get(f'http://127.0.0.1:{MODEL_PORT}/health', timeout=3)
        return response.json(), response.status_code
    except Exception as e:
        return {'status': 'error', 'model_loaded': False, 'error': str(e)}, 503


@app.route('/predict', methods=['POST'])
def proxy_predict():
    """Proxy prediction to model backend service."""
    try:
        payload = request.get_json(silent=True) or {}
        response = requests.post(f'http://127.0.0.1:{MODEL_PORT}/predict', json=payload, timeout=8)
        return response.json(), response.status_code
    except Exception as e:
        return {'error': str(e)}, 503


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    logger.info(f"Client connected: {request.sid}")
    emit('status', {
        'message': 'Connected to magnetic monitor server',
        'status': 'connected',
        'client_id': request.sid,
        'timestamp': datetime.now().isoformat()
    })


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.info(f"Client disconnected: {request.sid}")





@socketio.on('magnetic_data')
def handle_magnetic_data(data):
    """处理从客户端接收的磁场数据"""
    try:
        # 验证数据格式
        if not all(key in data for key in ['x', 'y', 'z']):
            logger.warning(f"数据格式错误: {data}")
            return
        
        # 添加时间戳和设备信息
        data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        data['device'] = data.get('device', 'Unknown')
        record_magnetic_data(data)

        # 广播数据给所有客户端
        socketio.emit('magnetic_data', data)
        
    except Exception as e:
        logger.error(f"处理磁场数据时出错: {e}")


@app.route('/api/status')
def api_status():
    """API endpoint for system status."""
    try:
        # 安全地获取客户端数量
        clients_count = 0
        if hasattr(socketio.server, 'eio') and hasattr(socketio.server.eio, 'sockets'):
            try:
                clients_count = len(socketio.server.eio.sockets)
            except (AttributeError, TypeError):
                pass
        
    except Exception as e:
        logger.error(f"获取客户端数量时出错: {e}")
        clients_count = 0
    
    return {
        'status': 'running',
        'timestamp': datetime.now().isoformat(),
        'clients': clients_count,
        'data_points': len(data_history['x'])
    }


@app.route('/api/magnetic_data', methods=['POST'])
def api_receive_magnetic_data():
    """
    API endpoint for receiving magnetic data from serial receiver.
    接收串口接收器发送的磁场数据。
    """
    try:
        data = request.get_json()
        
        if not data:
            return {'error': 'No data received'}, 400
        
        data['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        device = data.get('device', 'Serial')
        if process_magnetic_data(data, device):
            socketio.emit('magnetic_data', data)
            return {'status': 'success', 'message': 'Data received'}, 200
        else:
            return {'error': 'Failed to process data'}, 400
            
    except Exception as e:
        logger.error(f"API接收磁场数据时出错: {e}")
        return {'error': str(e)}, 500


def process_magnetic_data(data, device='Unknown'):
    """处理磁场数据"""
    try:
        # 添加设备信息
        data['device'] = device
        record_magnetic_data(data)

        return True
        
    except Exception as e:
        logger.error(f"处理磁场数据时出错: {e}")
        return False


class SerialDataReceiver:
    """串口数据接收器"""
    
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200, server_url='http://127.0.0.1:5000'):
        self.port = port
        self.baudrate = baudrate
        self.server_url = server_url
        self.serial_conn = None
        self.is_running = False
        self.receive_thread = None
        
        # 线程池，用于并行处理数据发送（利用树莓派4核心CPU）
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        
    def list_available_ports(self):
        """列出所有可用串口"""
        ports = serial.tools.list_ports.comports()
        available_ports = []
        
        logger.info("\n可用串口列表:")
        logger.info("-" * 60)
        
        for i, port in enumerate(ports, 1):
            logger.info(f"{i}. {port.device}")
            logger.info(f"   描述: {port.description}")
            logger.info(f"   硬件ID: {port.hwid}")
            logger.info("")
            available_ports.append(port.device)
            
        return available_ports
    
    def connect(self):
        """连接串口"""
        try:
            logger.info(f"\n正在连接串口 {self.port}...")
            logger.info(f"波特率: {self.baudrate}")
            
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            
            # 等待串口稳定
            time.sleep(2)
            
            if self.serial_conn.is_open:
                logger.info("✅ 串口连接成功")
                return True
            else:
                logger.error("❌ 串口连接失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 连接串口时出错: {e}")
            return False
    
    def disconnect(self):
        """断开串口连接"""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
                logger.info("✅ 串口已断开")
        except Exception as e:
            logger.error(f"❌ 断开串口时出错: {e}")
    
    def start_receiving(self):
        """开始接收数据"""
        if not self.serial_conn or not self.serial_conn.is_open:
            logger.error("❌ 串口未连接")
            return False
        
        self.is_running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        logger.info("✅ 开始接收串口数据")
        return True
    
    def stop_receiving(self):
        """停止接收数据"""
        self.is_running = False
        if self.receive_thread:
            self.receive_thread.join(timeout=5)
        logger.info("✅ 停止接收串口数据")
    
    def _receive_loop(self):
        """接收数据的主循环"""
        buffer = ""
        while self.is_running:
            try:
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='ignore')
                    buffer += data
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        self._process_data(line.strip())
                else:
                    time.sleep(0.01)  # 避免CPU占用过高
            except Exception as e:
                logger.error(f"❌ 接收数据时出错: {e}")
                time.sleep(1)
    
    def _process_data(self, line):
        """处理接收到的数据"""
        try:
            # 解析数据
            if line.startswith('xyzmT:'):
                # 格式: xyzmT:0.220,-0.010,0.077
                data_str = line.split(':', 1)[1]
                x, y, z = map(float, data_str.split(','))
                
                data = {
                    'x': x,
                    'y': y,
                    'z': z,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    'device': 'ESP32'
                }
                
                # 异步发送数据到服务器
                self.executor.submit(self._send_to_server, data)
                
            elif line.strip():
                # 其他类型的消息
                logger.info(f"串口消息: {line}")
                
        except Exception as e:
            logger.error(f"❌ 处理数据时出错: {e}")
    

    
    def _send_to_server(self, data):
        """发送数据到服务器"""
        def send_data_task():
            try:
                url = f"{self.server_url}/api/magnetic_data"
                response = requests.post(
                    url,
                    json=data,
                    headers={'Content-Type': 'application/json'},
                    timeout=5
                )
                if response.status_code == 200:
                    pass  # 成功，静默处理
                else:
                    logger.warning(f"发送数据失败: {response.status_code}")
            except Exception as e:
                logger.error(f"❌ 发送数据到服务器时出错: {e}")
        
        # 执行发送任务
        send_data_task()


class NetworkMagneticSimulator:
    """网络磁场模拟器"""
    def __init__(self):
        self.base_x = 0.5
        self.base_y = 0.3
        self.base_z = 0.7
        self.time_step = 0
        
        # 创建SocketIO客户端
        self.sio = socketio.Client()
        
        # 注册事件处理器
        @self.sio.event
        def connect():
            print('✅ 已连接到服务器')
            
        @self.sio.event
        def disconnect():
            print('❌ 与服务器断开连接')
            
        @self.sio.event
        def status(data):
            print(f'📡 服务器状态: {data}')
    
    def generate_magnetic_data(self):
        """生成磁场数据"""
        self.time_step += 0.1
        
        # 基础波动
        x = self.base_x + 0.05 * math.sin(self.time_step) + random.uniform(-0.02, 0.02)
        y = self.base_y + 0.03 * math.cos(self.time_step) + random.uniform(-0.02, 0.02)
        z = self.base_z + 0.04 * math.sin(self.time_step * 0.5) + random.uniform(-0.02, 0.02)
        
        return x, y, z
    
    def connect_to_server(self, server_url='http://192.168.137.91:5000'):
        """连接到服务器"""
        try:
            print(f'正在连接到服务器: {server_url}')
            # 清理可能存在的旧连接
            if self.sio.connected:
                try:
                    self.sio.disconnect()
                except:
                    pass
            
            # 连接到服务器
            self.sio.connect(server_url, transports=['websocket', 'polling'])
            return True
        except Exception as e:
            print(f'❌ 连接失败: {e}')
            return False
    
    def send_magnetic_data(self, x, y, z):
        """发送磁场数据"""
        try:
            if not self.sio.connected:
                print('⚠️ 未连接到服务器，无法发送数据')
                return False
            
            data = {
                'x': x,
                'y': y,
                'z': z,
                'timestamp': time.strftime('%H:%M:%S'),
                'device': 'NetworkSimulator'
            }
            self.sio.emit('magnetic_data', data)
            return True
        except Exception as e:
            print(f'❌ 发送数据失败: {e}')
            return False
    
    def simulate_monitoring(self, duration=60, interval=0.5):
        """模拟磁场监测"""
        print(f'开始模拟磁场监测，时长: {duration}秒')
        print('=' * 60)
        
        start_time = time.time()
        count = 0
        error_count = 0
        
        while time.time() - start_time < duration:
            # 检查连接状态
            if not self.sio.connected:
                print('⚠️ 连接已断开，尝试重新连接...')
                if not self.connect_to_server():
                    time.sleep(2)
                    continue
            
            # 生成并发送数据
            x, y, z = self.generate_magnetic_data()
            if self.send_magnetic_data(x, y, z):
                count += 1
                if count % 10 == 0:
                    print(f'已发送 {count} 条数据')
            else:
                error_count += 1
            
            # 等待下一次发送
            time.sleep(interval)
        
        print('=' * 60)
        print(f'模拟完成')
        print(f'发送成功: {count} 条')
        print(f'发送失败: {error_count} 条')
        
        # 断开连接
        if self.sio.connected:
            self.sio.disconnect()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='磁场监测系统')
    parser.add_argument('--serial', action='store_true', help='启动串口接收器')
    parser.add_argument('--simulator', action='store_true', help='启动网络模拟器')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='串口设备路径')
    parser.add_argument('--baudrate', type=int, default=115200, help='波特率')
    parser.add_argument('--server', default='http://127.0.0.1:5000', help='服务器地址')
    parser.add_argument('--duration', type=int, default=60, help='模拟器运行时长（秒）')
    parser.add_argument('--list-ports', action='store_true', help='列出可用串口')
    
    args = parser.parse_args()
    
    # 列出可用串口
    if args.list_ports:
        if not SERIAL_AVAILABLE:
            print('❌ 串口模块不可用，无法列出串口')
            return
        receiver = SerialDataReceiver()
        receiver.list_available_ports()
        return
    
    # 启动串口接收器
    if args.serial:
        if not SERIAL_AVAILABLE:
            print('❌ 串口模块不可用，无法启动串口接收器')
            return
        receiver = SerialDataReceiver(
            port=args.port,
            baudrate=args.baudrate,
            server_url=args.server
        )
        
        # 连接串口
        if not receiver.connect():
            return
        
        # 开始接收数据
        if receiver.start_receiving():
            try:
                print('按 Ctrl+C 停止...')
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print('\n正在停止...')
                receiver.stop_receiving()
                receiver.disconnect()
        
        return
    
    # 启动网络模拟器
    if args.simulator:
        simulator = NetworkMagneticSimulator()
        
        # 连接服务器
        if simulator.connect_to_server(args.server):
            # 开始模拟
            simulator.simulate_monitoring(duration=args.duration)
        
        return
    
    # 启动Flask服务器
    print('🚀 启动磁场监测系统服务器...')
    print('=' * 60)
    
    # 尝试获取IP地址
    try:
        import socket
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        print(f'🌐 本地地址: http://{ip_address}:5000')
        print(f'🏠 本地访问: http://localhost:5000')
    except:
        print('🌐 服务器地址: http://localhost:5000')
    
    print('=' * 60)
    print('按 Ctrl+C 停止服务器')
    print('=' * 60)
    
    # 启动服务器
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print('\n正在停止服务器...')


if __name__ == '__main__':
    main()
