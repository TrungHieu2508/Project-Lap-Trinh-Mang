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

class RemoteMonitorClient:
    def __init__(self):
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=5, reconnection_delay=1000)
        self.stop_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=5)
        self.is_connected = False
        self.config = self.load_config()
        
        self.setup_socketio()
        
    def load_config(self):
        """Tải cấu hình từ file"""
        config_path = "client_config.json"
        default_config = {
            "SERVER_IP": "localhost",
            "SERVER_PORT": 5000,
            "CAPTURE_INTERVAL": 0.5,
            "MAX_WIDTH": 1280,
            "JPEG_QUALITY": 70,
            "PASSWORD": "change_this_password"
        }
        
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        else:
            with open(config_path, "w") as f:
                json.dump(default_config, f, indent=2)
            return default_config
    
    def setup_socketio(self):
        """Thiết lập SocketIO client"""
        
        @self.sio.event
        def connect():
            self.is_connected = True
            print("✅ Đã kết nối thành công tới server!")
            
            # Gửi metadata đăng ký
            metadata = {
                "username": getpass.getuser(),
                "hostname": socket.gethostname(),
                "pid": os.getpid()
            }
            self.sio.emit("register", metadata)
            
            # Bắt đầu gửi frame
            self.start_capture()
        
        @self.sio.event
        def disconnect():
            self.is_connected = False
            print("❌ Mất kết nối với server!")
            self.stop_event.set()
    
    def connect_to_server(self):
        """Kết nối đến server"""
        try:
            server_url = f"http://{self.config['SERVER_IP']}:{self.config['SERVER_PORT']}"
            print(f"🔌 Đang kết nối tới {server_url}...")
            self.sio.connect(server_url, wait_timeout=10)
        except Exception as e:
            print(f"❌ Lỗi kết nối: {e}")
            return False
        return True
    
    def start_capture(self):
        """Bắt đầu chụp và gửi màn hình"""
        def capture_loop():
            last_hash = None
            while not self.stop_event.is_set() and self.is_connected:
                try:
                    # Chụp màn hình
                    screenshot = pyautogui.screenshot()
                    w, h = screenshot.size
                    max_width = self.config["MAX_WIDTH"]
                    
                    # Resize nếu cần
                    if w > max_width:
                        new_h = int(h * (max_width / w))
                        screenshot = screenshot.resize((max_width, new_h), Image.LANCZOS)
                    
                    # Nén ảnh
                    buffer = io.BytesIO()
                    screenshot.save(buffer, format="JPEG", quality=self.config["JPEG_QUALITY"], optimize=True)
                    img_bytes = buffer.getvalue()
                    
                    # Kiểm tra frame trùng
                    current_hash = hashlib.md5(img_bytes).hexdigest()
                    if current_hash == last_hash:
                        time.sleep(self.config["CAPTURE_INTERVAL"])
                        continue
                    
                    last_hash = current_hash
                    
                    # Mã hóa và gửi
                    encrypted = self.encrypt_bytes(img_bytes, self.config["PASSWORD"])
                    payload = {
                        "meta": {
                            "username": getpass.getuser(),
                            "hostname": socket.gethostname(),
                            "pid": os.getpid()
                        },
                        "timestamp": int(time.time()),
                        "enc_image_b64": base64.b64encode(encrypted).decode(),
                        "enc_scheme": "xor_fallback"
                    }
                    
                    if self.is_connected:
                        self.sio.emit("image_encrypted", payload)
                    
                    time.sleep(self.config["CAPTURE_INTERVAL"])
                    
                except Exception as e:
                    print(f"❌ Lỗi chụp màn hình: {e}")
                    time.sleep(1)
        
        # Chạy trong thread riêng
        capture_thread = threading.Thread(target=capture_loop, daemon=True)
        capture_thread.start()
    
    def encrypt_bytes(self, data: bytes, password: str) -> bytes:
        """Mã hóa dữ liệu"""
        key = hashlib.sha256(password.encode()).digest()
        out = bytearray(data)
        for i in range(len(out)):
            out[i] ^= key[i % len(key)]
        return b"XORv1" + bytes(out)
    
    def disconnect(self):
        """Ngắt kết nối"""
        self.stop_event.set()
        self.sio.disconnect()
        print("⏹️ Đã ngắt kết nối")

def main():
    client = RemoteMonitorClient()
    
    # Kết nối đến server
    if client.connect_to_server():
        print("🚀 Client đã khởi động. Nhấn Ctrl+C để dừng.")
        try:
            # Giữ chương trình chạy
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Đang dừng client...")
            client.disconnect()
    else:
        print("❌ Không thể kết nối đến server. Kiểm tra cấu hình và thử lại.")

if __name__ == "__main__":
    main()