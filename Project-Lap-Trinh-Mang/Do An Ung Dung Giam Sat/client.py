# client.py
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
import sys

class RemoteMonitorClient:
    def __init__(self):
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=5, reconnection_delay=1000)
        self.stop_event = threading.Event()
        self.is_connected = False
        self.config = self.load_config()
        self.session_id = ""
        self.setup_socketio()
        
    def load_config(self):
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
        @self.sio.event
        def connect():
            self.is_connected = True
            print("Đã kết nối thành công tới server!")
            metadata = {
                "username": getpass.getuser(),
                "hostname": socket.gethostname(),
                "pid": os.getpid()
            }
            self.sio.emit("register", metadata)
            self.start_capture()
        
        @self.sio.event
        def disconnect():
            self.is_connected = False
            print("Mất kết nối với server!")
            self.stop_event.set()
    
    def discover_server(self, session_id):
        DISCOVERY_PORT = 5001
        TIMEOUT = 5
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(TIMEOUT)
        
        message = f"DISCOVER_SERVER {session_id}".encode('utf-8')
        sock.sendto(message, ('255.255.255.255', DISCOVERY_PORT))
        print("Đang tìm server trong mạng LAN...")
        
        try:
            data, addr = sock.recvfrom(1024)
            reply = data.decode('utf-8')
            if reply.startswith("SERVER_HERE "):
                port = int(reply.split(" ")[1])
                ip = addr[0]
                print(f"Đã tìm thấy server: {ip}:{port}")
                return ip, port
        except socket.timeout:
            print("Không tìm thấy server. Kiểm tra mạng hoặc mã lớp.")
        finally:
            sock.close()
        return None, None

    def connect_to_server(self):
        ip, port = self.discover_server(self.session_id)
        if not ip:
            return False
        self.config['SERVER_IP'] = ip
        self.config['SERVER_PORT'] = port
        try:
            url = f"http://{ip}:{port}"
            print(f"Đang kết nối đến {url}...")
            self.sio.connect(url, wait_timeout=10)
            return True
        except Exception as e:
            print(f"Lỗi kết nối: {e}")
            return False
    
    def start_capture(self):
        def capture_loop():
            last_hash = None
            while not self.stop_event.is_set() and self.is_connected:
                try:
                    screenshot = pyautogui.screenshot()
                    w, h = screenshot.size
                    if w > self.config["MAX_WIDTH"]:
                        new_h = int(h * (self.config["MAX_WIDTH"] / w))
                        screenshot = screenshot.resize((self.config["MAX_WIDTH"], new_h), Image.LANCZOS)
                    buffer = io.BytesIO()
                    screenshot.save(buffer, format="JPEG", quality=self.config["JPEG_QUALITY"], optimize=True)
                    img_bytes = buffer.getvalue()
                    current_hash = hashlib.md5(img_bytes).hexdigest()
                    if current_hash == last_hash:
                        time.sleep(self.config["CAPTURE_INTERVAL"])
                        continue
                    last_hash = current_hash
                    encrypted = self.encrypt_bytes(img_bytes, self.config["PASSWORD"])
                    payload = {
                        "meta": {"username": getpass.getuser(), "hostname": socket.gethostname(), "pid": os.getpid()},
                        "timestamp": int(time.time()),
                        "enc_image_b64": base64.b64encode(encrypted).decode(),
                        "enc_scheme": "xor_fallback"
                    }
                    if self.is_connected:
                        self.sio.emit("image_encrypted", payload)
                    time.sleep(self.config["CAPTURE_INTERVAL"])
                except Exception as e:
                    print(f"Lỗi chụp màn hình: {e}")
                    time.sleep(1)
        threading.Thread(target=capture_loop, daemon=True).start()
    
    def encrypt_bytes(self, data: bytes, password: str) -> bytes:
        key = hashlib.sha256(password.encode()).digest()
        out = bytearray(data)
        for i in range(len(out)):
            out[i] ^= key[i % len(key)]
        return b"XORv1" + bytes(out)
    
    def disconnect(self):
        self.stop_event.set()
        self.sio.disconnect()
        print("Đã ngắt kết nối")

def main():
    if len(sys.argv) < 2:
        print("Cần nhập mã lớp! Ví dụ: python client.py ABC123")
        return
    session_id = sys.argv[1].upper()
    client = RemoteMonitorClient()
    client.session_id = session_id
    if client.connect_to_server():
        print("Client đang chạy. Nhấn Ctrl+C để dừng.")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            print("\nĐang dừng client...")
            client.disconnect()
    else:
        print("Không thể kết nối. Kiểm tra mạng, firewall và mã lớp.")

if __name__ == "__main__":
    main()