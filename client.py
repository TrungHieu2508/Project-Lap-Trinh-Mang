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

SERVER_IP = CONFIG.get("SERVER_IP", "")
SERVER_PORT = CONFIG["SERVER_PORT"]
CAPTURE_INTERVAL = CONFIG["CAPTURE_INTERVAL"]
MAX_WIDTH = CONFIG["MAX_WIDTH"]
JPEG_QUALITY = CONFIG["JPEG_QUALITY"]
PASSWORD = CONFIG["PASSWORD"]

# ----------------------------------------------------------------
# Hàm tự động tìm server trong mạng LAN
# ----------------------------------------------------------------
def auto_discover_server(port=SERVER_PORT, timeout=0.5):
    """
    Quét các IP trong mạng LAN (192.168.x.x) để tìm server có cổng đang mở.
    Trả về IP đầu tiên tìm thấy.
    """
    import ipaddress
    import concurrent.futures

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        subnet = ".".join(local_ip.split(".")[:3]) + ".0/24"
    except Exception:
        subnet = "192.168.1.0/24"

    print(f"🔍 Đang quét mạng LAN {subnet} để tìm server...")

    def check_ip(ip):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((str(ip), port))
            s.close()
            return str(ip)
        except:
            return None

    found_ip = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_ip, ip) for ip in ipaddress.IPv4Network(subnet)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                found_ip = res
                print(f"✅ Tìm thấy server tại {found_ip}:{port}")
                break

    return found_ip

# Nếu IP trống, tự động quét LAN
if not SERVER_IP:
    SERVER_IP = auto_discover_server(SERVER_PORT)
    if not SERVER_IP:
        raise RuntimeError("❌ Không tìm thấy server trong mạng LAN!")
    else:
        CONFIG["SERVER_IP"] = SERVER_IP
        with open(CONFIG_PATH, "w") as f:
            json.dump(CONFIG, f, indent=2)
        print(f"💾 Đã lưu IP server vào config.json: {SERVER_IP}")

# ----------------------------------------------------------------
# Encryption helpers
# ----------------------------------------------------------------
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

# ----------------------------------------------------------------
# SocketIO + Metadata setup
# ----------------------------------------------------------------
sio = socketio.Client(reconnection=False)
frame_queue = queue.Queue(maxsize=5)
stop_event = threading.Event()

METADATA = {
    "username": getpass.getuser(),
    "hostname": socket.gethostname(),
    "pid": os.getpid()
}

# ----------------------------------------------------------------
# Cơ chế kết nối + reconnect thủ công
# ----------------------------------------------------------------
def connect_to_server():
    while True:
        try:
            print(f"🔌 Đang kết nối tới server {SERVER_IP}:{SERVER_PORT} ...")
            sio.connect(f"http://{SERVER_IP}:{SERVER_PORT}", wait=True)
            print("✅ Đã kết nối thành công tới server!")
            return
        except Exception as e:
            print(f"⚠️ Không thể kết nối: {e} -> thử lại sau 5s")
            time.sleep(5)

@sio.event
def connect():
    print("-> Socket connected, gửi metadata.")
    sio.emit("register", METADATA)

@sio.event
def disconnect():
    print("-> Socket disconnected! Reconnecting...")
    connect_to_server()

# ----------------------------------------------------------------
# Capture ảnh màn hình và gửi qua SocketIO
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

            current_hash = hashlib.md5(img_bytes).hexdigest()
            if current_hash == last_hash:
                time.sleep(CAPTURE_INTERVAL)
                continue

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

# ----------------------------------------------------------------
# Gửi frame đã mã hoá tới server
# ----------------------------------------------------------------
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

@sio.on("stop_client")
def on_stop_client(data):
    cid = f"{USERNAME}@{HOSTNAME}"
    if data.get("client_id") == cid:
        print("🛑 Server yêu cầu ngắt kết nối — dừng gửi ảnh.")
        sio.disconnect()

@sio.event
def disconnect():
    print("❌ Đã ngắt kết nối khỏi server.")
    
@sio.on("stop_all_clients")
def stop_all(data):
    print("🛑 Server yêu cầu dừng toàn bộ giám sát.")
    sio.disconnect()


# ----------------------------------------------------------------
# Main run
# ----------------------------------------------------------------
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
