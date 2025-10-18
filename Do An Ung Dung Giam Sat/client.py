# client.py (nâng cấp)
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

# --- Encryption helpers: cố gắng dùng cryptography (Fernet). Nếu không có -> fallback XOR (không an toàn, chỉ tạm thời).
try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False

def derive_fernet_key(password: str, salt: bytes) -> bytes:
    """
    Derive a 32-byte key for Fernet from password+salt using PBKDF2.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key

def encrypt_bytes(data: bytes, password: str) -> bytes:
    """
    Return encrypted bytes. If cryptography available -> Fernet (AES-based).
    Otherwise fallback to simple XOR with SHA256(password) (NOT SECURE).
    The return format when using Fernet: salt(16 bytes) + token
    When using XOR: b'XORv1' + token
    """
    if CRYPTO_AVAILABLE:
        salt = os.urandom(16)
        key = derive_fernet_key(password, salt)
        f = Fernet(key)
        token = f.encrypt(data)
        return salt + token
    else:
        # WARNING: XOR fallback is NOT secure. Install 'cryptography' package for real encryption.
        key = hashlib.sha256(password.encode()).digest()
        out = bytearray(data)
        for i in range(len(out)):
            out[i] ^= key[i % len(key)]
        return b"XORv1" + bytes(out)

def decrypt_bytes(payload: bytes, password: str) -> bytes:
    """
    (For reference) Decrypt payload. Not used in client but shown for completeness.
    """
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

# ---------------- Configuration ----------------
SERVER_IP = "192.168.17.113"   # ⚠️ sửa thành IP server của bạn nếu cần
SERVER_PORT = 5000
CAPTURE_INTERVAL = 1.0     # giây giữa 2 lần capture (có thể giảm để gửi nhanh hơn)
MAX_WIDTH = 800            # giảm độ phân giải: thay đổi theo nhu cầu (px)
JPEG_QUALITY = 60          # chất lượng JPEG 0-100 (giảm dung lượng)
SEND_IN_BACKGROUND = True  # dùng luồng gửi riêng (True recommended)
PASSWORD = "change_this_password"  # shared secret để mã hóa (server phải biết để giải mã)
# ------------------------------------------------

sio = socketio.Client(reconnection=True)
frame_queue = queue.Queue(maxsize=5)
stop_event = threading.Event()

# metadata (username + hostname)
METADATA = {
    "username": getpass.getuser(),
    "hostname": socket.gethostname(),
    "pid": os.getpid()
}

def connect_to_server():
    try:
        sio.connect(f"http://{SERVER_IP}:{SERVER_PORT}", wait=True)
        print("✅ Connected to server!")
    except Exception as e:
        print("❌ Could not connect to server:", e)
        raise

@sio.event
def connect():
    print("-> socket connected, sending registration metadata.")
    # gửi đăng ký (metadata) 1 lần để server biết thông tin client
    sio.emit("register", METADATA)

@sio.event
def disconnect():
    print("-> socket disconnected.")

def capture_loop():
    """
    Luồng này chỉ chụp màn hình, giảm kích thước và đẩy vào queue.
    """
    while not stop_event.is_set():
        try:
            screenshot = pyautogui.screenshot()
            # Resize preserving aspect ratio
            w, h = screenshot.size
            if w > MAX_WIDTH:
                new_w = MAX_WIDTH
                new_h = int(h * (MAX_WIDTH / w))
                screenshot = screenshot.resize((new_w, new_h), Image.LANCZOS)

            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            img_bytes = buffer.getvalue()

            # Put into queue (drop oldest if full to avoid piling)
            try:
                frame_queue.put_nowait(img_bytes)
            except queue.Full:
                try:
                    _ = frame_queue.get_nowait()  # drop oldest
                    frame_queue.put_nowait(img_bytes)
                except queue.Empty:
                    pass

            time.sleep(CAPTURE_INTERVAL)
        except Exception as e:
            print("Capture error:", e)
            time.sleep(1)

def sender_loop():
    """
    Luồng này lấy frame từ queue, mã hóa và gửi lên server.
    Gửi theo 2 event để tương thích: 'image' (chuỗi dataurl - backward compatible)
    và 'image_encrypted' (payload dict chứa ảnh mã hóa dưới dạng base64).
    """
    while not stop_event.is_set():
        try:
            img_bytes = frame_queue.get(timeout=1)
        except queue.Empty:
            continue

        try:
            # Mã hóa
            encrypted = encrypt_bytes(img_bytes, PASSWORD)
            encrypted_b64 = base64.b64encode(encrypted).decode()

            timestamp = int(time.time())
            # gửi backward-compatible: data url string (không mã hóa) -> để server/UI cũ vẫn hoạt động
            # LƯU Ý: nếu bạn muốn chỉ gửi mã hóa (an toàn hơn), bỏ phần emit 'image' dưới và chỉ dùng image_encrypted
            try:
                # giữ một phiên bản nhẹ (resize + quality) đã có ở trên; chuyển thành dataurl (chuẩn)
                small_b64 = base64.b64encode(img_bytes).decode()
                sio.emit('image', f"data:image/jpeg;base64,{small_b64}")
            except Exception:
                pass

            # gửi kèm metadata và ảnh mã hóa
            payload = {
                "meta": METADATA,
                "timestamp": timestamp,
                "enc_image_b64": encrypted_b64,
                "enc_scheme": "fernet" if CRYPTO_AVAILABLE else "xor_fallback"
            }
            sio.emit("image_encrypted", payload)
            print(f"📤 Sent frame at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))} - meta: {METADATA['username']}@{METADATA['hostname']}")
        except Exception as e:
            print("Send error:", e)
        finally:
            frame_queue.task_done()

def start_threads():
    t1 = threading.Thread(target=capture_loop, daemon=True)
    t1.start()
    if SEND_IN_BACKGROUND:
        t2 = threading.Thread(target=sender_loop, daemon=True)
        t2.start()
    else:
        # nếu không tách luồng thì chạy sender trực tiếp trong main (không khuyến nghị)
        sender_loop()

if __name__ == "__main__":
    print("Client starting...")
    print(f"Metadata: {METADATA}")
    print(f"Crypto available: {CRYPTO_AVAILABLE} (install 'cryptography' for strong encryption)")
    try:
        connect_to_server()
    except Exception:
        print("Không kết nối được server — thoát.")
        raise

    start_threads()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        stop_event.set()
        time.sleep(0.5)
        sio.disconnect()
