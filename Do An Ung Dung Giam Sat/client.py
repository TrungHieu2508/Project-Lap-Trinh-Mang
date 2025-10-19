import socketio
import pyautogui
import base64
import io
from PIL import Image
import time
import threading
import queue
import getpass
import socket
import os
import json
import hashlib

# ----------------------------------------------------------------
# Load CONFIG từ file config.json
# ----------------------------------------------------------------
CONFIG_PATH = "config.json"
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError("❌ Không tìm thấy config.json!")

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

SERVER_IP = CONFIG["SERVER_IP"]
SERVER_PORT = CONFIG["SERVER_PORT"]
CAPTURE_INTERVAL = CONFIG["CAPTURE_INTERVAL"]
MAX_WIDTH = CONFIG["MAX_WIDTH"]
JPEG_QUALITY = CONFIG["JPEG_QUALITY"]
PASSWORD = CONFIG["PASSWORD"]

# --- Encryption helpers (Giữ nguyên phần này của bạn) ---
try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False

def derive_fernet_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_bytes(data: bytes, password: str) -> bytes:
    if CRYPTO_AVAILABLE:
        salt = os.urandom(16)
        key = derive_fernet_key(password, salt)
        f = Fernet(key)
        token = f.encrypt(data)
        return salt + token
    else:
        key = hashlib.sha256(password.encode()).digest()
        out = bytearray(data)
        for i in range(len(out)):
            out[i] ^= key[i % len(key)]
        return b"XORv1" + bytes(out)

# ---------------- Socket + Metadata ----------------
sio = socketio.Client(reconnection=False)  # Tự reconnect mình làm thủ công
frame_queue = queue.Queue(maxsize=5)
stop_event = threading.Event()

METADATA = {
    "username": getpass.getuser(),
    "hostname": socket.gethostname(),
    "pid": os.getpid()
}

# ----------------------------------------------------------------
# THÊM CƠ CHẾ RECONNECT TÙY CHỈNH
# ----------------------------------------------------------------
def connect_to_server():
    while True:
        try:
            print(f"🔌 Connecting to server {SERVER_IP}:{SERVER_PORT} ...")
            sio.connect(f"http://{SERVER_IP}:{SERVER_PORT}", wait=True)
            print("✅ Connected to server!")
            return
        except Exception as e:
            print(f"⚠️ Could not connect: {e} -> retry in 5s")
            time.sleep(5)

@sio.event
def connect():
    print("-> socket connected, sending metadata.")
    sio.emit("register", METADATA)

@sio.event
def disconnect():
    print("-> socket disconnected! Reconnecting...")
    connect_to_server()

# ----------------------------------------------------------------
# Capture + CPU Optimization (chỉ gửi khi ảnh thay đổi)
# ----------------------------------------------------------------
last_hash = None

def capture_loop():
    global last_hash
    while not stop_event.is_set():
        try:
            screenshot = pyautogui.screenshot()
            w, h = screenshot.size
            if w > MAX_WIDTH:
                new_h = int(h * (MAX_WIDTH / w))
                screenshot = screenshot.resize((MAX_WIDTH, new_h), Image.LANCZOS)

            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            img_bytes = buffer.getvalue()

            # Only push to queue if different from last frame
            current_hash = hashlib.md5(img_bytes).hexdigest()
            if current_hash == last_hash:
                time.sleep(CAPTURE_INTERVAL)
                continue  # Skip sending identical frame

            last_hash = current_hash

            try:
                frame_queue.put_nowait(img_bytes)
            except queue.Full:
                _ = frame_queue.get_nowait()
                frame_queue.put_nowait(img_bytes)

            time.sleep(CAPTURE_INTERVAL)

        except Exception as e:
            print("Capture error:", e)
            time.sleep(1)

def sender_loop():
    while not stop_event.is_set():
        try:
            img_bytes = frame_queue.get(timeout=1)
        except queue.Empty:
            continue

        try:
            encrypted = encrypt_bytes(img_bytes, PASSWORD)
            payload = {
                "meta": METADATA,
                "timestamp": int(time.time()),
                "enc_image_b64": base64.b64encode(encrypted).decode(),
                "enc_scheme": "fernet" if CRYPTO_AVAILABLE else "xor_fallback"
            }
            sio.emit("image_encrypted", payload)
        except Exception as e:
            print("Send error:", e)
        finally:
            frame_queue.task_done()

if __name__ == "__main__":
    connect_to_server()

    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=sender_loop, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        sio.disconnect()
