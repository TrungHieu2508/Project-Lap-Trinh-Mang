# server.py (RAM + live stream)
import base64
import time
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
from io import BytesIO
from datetime import datetime
import hashlib

# --- Encryption support ---
try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False

# --- cấu hình ---
SECRET_PASSWORD = "change_this_password"  # phải giống PASSWORD trong client

# ---------------- Helper functions ----------------
def derive_fernet_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def decrypt_bytes(payload: bytes, password: str) -> bytes:
    if CRYPTO_AVAILABLE:
        salt = payload[:16]
        token = payload[16:]
        key = derive_fernet_key(password, salt)
        f = Fernet(key)
        return f.decrypt(token)
    else:
        assert payload.startswith(b"XORv1")
        data = payload[5:]
        key = hashlib.sha256(password.encode()).digest()
        out = bytearray(data)
        for i in range(len(out)):
            out[i] ^= key[i % len(key)]
        return bytes(out)

# ---------------- Flask + SocketIO setup ----------------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Bộ nhớ RAM lưu ảnh mới nhất của từng client
latest_frames = {}   # { client_id: base64_jpeg_string }
clients_info = {}    # { sid: {username, hostname} }

# HTML template hiển thị live stream
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Live Monitor</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        body { font-family: sans-serif; background: #111; color: white; text-align: center; }
        h1 { color: #0ff; }
        .client { display: inline-block; margin: 10px; border: 2px solid #0ff; border-radius: 8px; padding: 10px; background: #222; }
        img { max-width: 400px; border-radius: 8px; }
    </style>
</head>
<body>
    <h1>🖥️ Live Clients Monitor</h1>
    <div id="container"></div>

    <script>
        const socket = io();
        const container = document.getElementById("container");

        socket.on("frame_update", (data) => {
            const { id, username, hostname, image_b64, timestamp } = data;
            let div = document.getElementById(id);
            if (!div) {
                div = document.createElement("div");
                div.className = "client";
                div.id = id;
                container.appendChild(div);
            }
            div.innerHTML = `
                <h3>${username}@${hostname}</h3>
                <img src="data:image/jpeg;base64,${image_b64}" />
                <p>${new Date(timestamp * 1000).toLocaleTimeString()}</p>
            `;
        });
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(TEMPLATE)

# ---- Khi client đăng ký thông tin ----
from flask import request

@socketio.on("register")
def handle_register(data):
    clients_info[request.sid] = data
    print(f"✅ Client đăng ký: {data}")

# ---- Khi client gửi ảnh mã hóa ----
@socketio.on("image_encrypted")
def handle_encrypted(payload):
    try:
        meta = payload.get("meta", {})
        enc_b64 = payload.get("enc_image_b64", "")
        enc_bytes = base64.b64decode(enc_b64)
        username = meta.get("username", "unknown")
        hostname = meta.get("hostname", "unknown")
        timestamp = payload.get("timestamp", int(time.time()))

        # Giải mã ảnh (tất cả xử lý trong RAM)
        decrypted = decrypt_bytes(enc_bytes, SECRET_PASSWORD)
        img_b64 = base64.b64encode(decrypted).decode()

        # Lưu vào RAM
        latest_frames[request.sid] = img_b64

        # Gửi update đến web dashboard
        socketio.emit("frame_update", {
            "id": request.sid,
            "username": username,
            "hostname": hostname,
            "timestamp": timestamp,
            "image_b64": img_b64
        })

        print(f"📸 {username}@{hostname} -> frame nhận lúc {time.strftime('%H:%M:%S')}")

    except Exception as e:
        print("❌ Lỗi xử lý ảnh mã hóa:", e)

# ---- Khi client ngắt kết nối ----
@socketio.on("disconnect")
def on_disconnect():
    if request.sid in clients_info:
        info = clients_info.pop(request.sid)
        latest_frames.pop(request.sid, None)
        print(f"❌ Client ngắt kết nối: {info}")
        socketio.emit("frame_update", {
            "id": request.sid,
            "username": info.get("username", ""),
            "hostname": info.get("hostname", ""),
            "image_b64": "",
            "timestamp": time.time()
        })

# ---------------- Run server ----------------
if __name__ == "__main__":
    print("🚀 Server khởi động tại http://localhost:5000 (RAM mode, no disk writes)")
    socketio.run(app, host="0.0.0.0", port=5000)
