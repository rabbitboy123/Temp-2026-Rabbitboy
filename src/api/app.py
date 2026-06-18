# Lab 2 buổi chiều: Flask app với /metrics - trigger CI build and push
import os
import random
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)  # Tự thêm /metrics

ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
VERSION = os.getenv("VERSION", "v1")

@app.get("/")
def index():
    if random.random() < ERROR_RATE:
        return jsonify(error="injected", version=VERSION), 500
    return jsonify(ok=True, version=VERSION)

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/password")
def get_password():
    path = "/etc/secrets/password"
    if os.path.exists(path):
        with open(path, "r") as f:
            return jsonify(password=f.read().strip())
    return jsonify(password="not-found"), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
