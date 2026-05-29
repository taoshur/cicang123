"""Magnetic defect detection web app.

Single-process deployment for Tencent CloudBase Run:
- Flask serves the web UI and static model assets.
- Flask-SocketIO handles realtime magnetic data.
- ONNX Runtime runs inference in this process.

Cloud deployment does not depend on Raspberry Pi, serial ports, tunnels, or a
second model service. Hardware data should be sent to /api/magnetic_data.
"""

try:
    import eventlet

    eventlet.monkey_patch()
except ImportError:
    eventlet = None

from datetime import datetime
import logging
import os
from pathlib import Path
import threading

from flask import Flask, jsonify, render_template, request, send_from_directory
try:
    from flask_cors import CORS
except ImportError:
    CORS = None
from flask_socketio import SocketIO, emit

try:
    import numpy as np
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    np = None
    ort = None
    ONNX_AVAILABLE = False


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
APP_PORT = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "8080")
DEPLOY_TARGET = os.environ.get("DEPLOY_TARGET", "cloudbase")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", "sensor_cnn/web/plate_model.onnx"))
MAX_DATA_HISTORY = 500
CLASS_NAMES = [
    "no_defect",
    "crack",
    "corrosion",
    "pitting",
    "scratch",
    "deformation",
    "blocky",
    "columnar",
]

app = Flask(__name__, template_folder=str(BASE_DIR))
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "magnetic-monitor-secret-key")
if CORS:
    CORS(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=120,
    ping_interval=20,
    logger=False,
    engineio_logger=False,
    async_mode="eventlet" if eventlet else None,
    http_compression=True,
    max_http_buffer_size=100_000_000,
)

data_history = {"x": [], "y": [], "z": []}
model_session = None
model_error = None
model_lock = threading.Lock()


def resolved_model_path() -> Path:
    return MODEL_PATH if MODEL_PATH.is_absolute() else BASE_DIR / MODEL_PATH


def load_model_session():
    """Load the ONNX model once inside the web process."""
    global model_session, model_error

    if model_session is not None or model_error is not None:
        return model_session

    with model_lock:
        if model_session is not None or model_error is not None:
            return model_session

        if not ONNX_AVAILABLE:
            model_error = "onnxruntime or numpy is not installed"
            logger.warning(model_error)
            return None

        model_file = resolved_model_path()
        if not model_file.exists():
            model_error = f"Model file not found: {model_file}"
            logger.warning(model_error)
            return None

        try:
            model_session = ort.InferenceSession(str(model_file), providers=["CPUExecutionProvider"])
            model_error = None
            logger.info("ONNX model loaded: %s", model_file)
        except Exception as exc:
            model_error = str(exc)
            logger.exception("Failed to load ONNX model")

        return model_session


def coerce_float(value, default=0.0):
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(numeric_value):
        return default
    return numeric_value


def extract_sensor_values(sensor_data):
    values = []
    for item in sensor_data:
        if isinstance(item, dict):
            values.extend(
                [
                    coerce_float(item.get("x")),
                    coerce_float(item.get("y")),
                    coerce_float(item.get("z")),
                ]
            )
        elif isinstance(item, (list, tuple)):
            values.extend(coerce_float(value) for value in item[:3])
        else:
            values.append(coerce_float(item))

        if len(values) >= 9:
            break

    return values[:9]


def normalize_sensor_values(sensor_values):
    processed_data = sensor_values[:9]
    while len(processed_data) < 9:
        processed_data.append(0.0)

    return np.array(processed_data, dtype=np.float32).reshape(1, 1, 9)


def count_sensor_groups(values):
    non_empty_value_count = len(values)
    if non_empty_value_count == 0:
        return 0
    return max(1, min(3, (non_empty_value_count + 2) // 3))


def get_actual_sensor_count(payload, values):
    raw_count = payload.get("actual_sensor_count", payload.get("sensor_count"))
    if raw_count is not None:
        try:
            return max(0, min(3, int(raw_count)))
        except (TypeError, ValueError):
            pass
    return count_sensor_groups(values)


def normalize_model_output(raw_output):
    values = np.asarray(raw_output, dtype=np.float64).reshape(-1)
    if len(values) > len(CLASS_NAMES):
        values = values[: len(CLASS_NAMES)]
    if len(values) < len(CLASS_NAMES):
        values = np.pad(values, (0, len(CLASS_NAMES) - len(values)), constant_values=0)

    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    total = float(np.sum(values))
    looks_like_probabilities = (
        np.all(values >= 0)
        and np.all(values <= 1)
        and total > 0
        and np.isclose(total, 1.0, atol=1e-3)
    )
    if looks_like_probabilities:
        return values.astype(np.float64)

    shifted = values - np.max(values)
    exp_values = np.exp(shifted)
    exp_total = float(np.sum(exp_values))
    if exp_total <= 0:
        return np.full(len(CLASS_NAMES), 1.0 / len(CLASS_NAMES), dtype=np.float64)
    return exp_values / exp_total


def predict_with_model(payload):
    session = load_model_session()
    if session is None:
        return {"error": model_error or "model is not loaded"}, 503

    sensor_data = payload.get("sensor_data", [])
    if not isinstance(sensor_data, list):
        return {"error": "sensor_data must be a list"}, 400

    try:
        confidence_threshold = float(payload.get("confidence_threshold", 0.3))
    except (TypeError, ValueError):
        confidence_threshold = 0.3
    confidence_threshold = max(0.0, min(1.0, confidence_threshold))

    sensor_values = extract_sensor_values(sensor_data)
    if not sensor_values:
        return {"error": "sensor_data must contain at least one numeric value"}, 400

    input_data = normalize_sensor_values(sensor_values)
    outputs = session.run(None, {session.get_inputs()[0].name: input_data})
    probabilities = normalize_model_output(outputs[0][0])

    predicted_class = int(np.argmax(probabilities))
    confidence = float(probabilities[predicted_class])
    actual_sensor_count = get_actual_sensor_count(payload, sensor_values)
    if actual_sensor_count < 3:
        confidence *= actual_sensor_count / 3
    has_defect = predicted_class != 0 and confidence >= confidence_threshold

    return {
        "class_id": predicted_class,
        "class_name": CLASS_NAMES[predicted_class],
        "confidence": confidence,
        "confidence_threshold": confidence_threshold,
        "has_defect": has_defect,
        "probabilities": [float(p) for p in probabilities],
        "sensor_count": actual_sensor_count,
        "sensor_value_count": len(sensor_values),
    }, 200


def record_magnetic_data(data):
    try:
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        z = float(data.get("z", 0))
    except (TypeError, ValueError, AttributeError):
        return False

    data_history["x"].append(x)
    data_history["y"].append(y)
    data_history["z"].append(z)

    if len(data_history["x"]) > MAX_DATA_HISTORY:
        data_history["x"].pop(0)
        data_history["y"].pop(0)
        data_history["z"].pop(0)

    return True


def prepare_magnetic_data(data, default_device="Unknown"):
    if not isinstance(data, dict):
        return None
    if not all(key in data for key in ["x", "y", "z"]):
        return None

    prepared = dict(data)
    prepared["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    prepared["device"] = prepared.get("device") or default_device
    return prepared


@app.route("/")
def index():
    return render_template("1.html")


@app.route("/sensor_cnn/<path:filename>")
def serve_sensor_cnn(filename):
    sensor_cnn_dir = (BASE_DIR / "sensor_cnn").resolve()
    requested_path = (sensor_cnn_dir / filename).resolve()
    try:
        requested_path.relative_to(sensor_cnn_dir)
    except ValueError:
        return "Access denied", 403
    if not requested_path.exists():
        return "File not found", 404
    return send_from_directory(requested_path.parent, requested_path.name)


@app.route("/health", methods=["GET"])
def health():
    session = load_model_session()
    return jsonify(
        {
            "status": "ok" if session else "degraded",
            "model_loaded": session is not None,
            "model_path": str(resolved_model_path()),
            "error": model_error,
            "port": APP_PORT,
            "deployment": DEPLOY_TARGET,
        }
    ), 200 if session else 503


@app.route("/healthz", methods=["GET"])
def healthz():
    """Liveness probe for CloudBase Run.

    This endpoint only checks that the web process is alive. Use /health when
    you also want to verify that the ONNX model can be loaded.
    """
    return jsonify(
        {
            "status": "ok",
            "port": APP_PORT,
            "deployment": DEPLOY_TARGET,
        }
    )


@app.route("/predict", methods=["POST"])
def predict():
    try:
        payload = request.get_json(silent=True) or {}
        result, status_code = predict_with_model(payload)
        return jsonify(result), status_code
    except Exception as exc:
        logger.exception("Prediction failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/status", methods=["GET"])
def api_status():
    clients_count = 0
    try:
        clients_count = len(socketio.server.eio.sockets)
    except Exception:
        pass

    return jsonify(
        {
            "status": "running",
            "timestamp": datetime.now().isoformat(),
            "clients": clients_count,
            "data_points": len(data_history["x"]),
            "model_loaded": model_session is not None,
        }
    )


@app.route("/api/magnetic_data", methods=["POST"])
def api_receive_magnetic_data():
    data = prepare_magnetic_data(request.get_json(silent=True), default_device="HTTP")
    if not data:
        return jsonify({"error": "Expected JSON with x, y, and z"}), 400

    if not record_magnetic_data(data):
        return jsonify({"error": "Failed to process data"}), 400

    socketio.emit("magnetic_data", data)
    return jsonify({"status": "success", "message": "Data received"})


@socketio.on("connect")
def handle_connect():
    logger.info("Client connected: %s", request.sid)
    emit(
        "status",
        {
            "message": "Connected to magnetic monitor server",
            "status": "connected",
            "client_id": request.sid,
            "timestamp": datetime.now().isoformat(),
        },
    )


@socketio.on("disconnect")
def handle_disconnect():
    logger.info("Client disconnected: %s", request.sid)


@socketio.on("magnetic_data")
def handle_magnetic_data(data):
    prepared = prepare_magnetic_data(data, default_device="SocketIO")
    if not prepared:
        logger.warning("Invalid magnetic data: %s", data)
        return

    if record_magnetic_data(prepared):
        socketio.emit("magnetic_data", prepared)


def main():
    load_model_session()
    logger.info("Starting server on 0.0.0.0:%s", APP_PORT)
    socketio.run(app, host="0.0.0.0", port=APP_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
