from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import onnxruntime as ort
import numpy as np
import os

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)
session = None
class_names = [
    "no_defect",
    "crack",
    "corrosion",
    "pitting",
    "scratch",
    "deformation",
    "blocky",
    "columnar"
]

@app.route('/')
def index():
    return send_from_directory('.', '1.html')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model_loaded': session is not None})

@app.route('/predict', methods=['POST'])
def predict():
    if not session:
        return jsonify({'error': '模型未加载'}), 500
    
    try:
        # 获取传感器数据
        data = request.json
        sensor_data = data.get('sensor_data', [])
        
        # 处理传感器数据
        processed_data = []
        for i in range(min(9, len(sensor_data))):
            # 检查数据类型，如果是数字直接使用，如果是对象则获取'x'属性
            if isinstance(sensor_data[i], (int, float)):
                processed_data.append(sensor_data[i])
            else:
                processed_data.append(sensor_data[i].get('x', 0))
        
        # 填充数据到9个传感器
        while len(processed_data) < 9:
            processed_data.append(0)
        
        # 转换为模型输入格式
        input_data = np.array(processed_data, dtype=np.float32)
        input_data = input_data.reshape(1, 1, 9)
        
        # 执行推理
        inputs = {session.get_inputs()[0].name: input_data}
        outputs = session.run(None, inputs)
        
        # 处理输出
        probabilities = outputs[0][0]

        # 如果模型输出9个类别，只取前8个（与前端匹配）
        if len(probabilities) > 8:
            print(f"⚠️ 模型输出 {len(probabilities)} 个概率值，截取前8个以匹配前端类别数量")
            probabilities = probabilities[:8]

        predicted_class = np.argmax(probabilities)
        confidence = probabilities[predicted_class]
        
        # 计算实际传感器数量
        actual_sensor_count = min(9, len(sensor_data))
        
        # 根据传感器数量调整置信度
        adjusted_confidence = confidence
        if actual_sensor_count < 9:
            adjusted_confidence *= (actual_sensor_count / 9)
        
        # 构建响应
        response = {
            'class_id': int(predicted_class),
            'class_name': class_names[predicted_class],
            'confidence': float(adjusted_confidence),
            'probabilities': [float(p) for p in probabilities],
            'sensor_count': actual_sensor_count
        }
        
        return jsonify(response)
    except Exception as e:
        print(f"推理失败: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    model_port = int(os.environ.get('MODEL_PORT', '5001'))

    # 加载模型
    try:
        session = ort.InferenceSession('sensor_cnn/web/plate_model.onnx')
        print("模型加载成功！")
    except Exception as e:
        print(f"模型加载失败: {e}")

    print(f"模型服务监听端口: {model_port}")

    # 启动服务
    app.run(host='0.0.0.0', port=model_port)