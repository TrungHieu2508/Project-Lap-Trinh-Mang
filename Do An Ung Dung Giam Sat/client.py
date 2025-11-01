# client.py
import pyautogui
import base64
import io
from PIL import Image
import time
import threading
import getpass
import socket
import os
import json
import hashlib
import sys

# Định nghĩa kích thước header cho giao thức
HEADER_LENGTH = 15

class RemoteMonitorClient:
    def __init__(self):
        self.tcp_socket = None
        self.stop_event = threading.Event()
        self.is_connected = False
        self.config = self.load_config()
        self.session_id = ""
        self.password = self.config.get("PASSWORD", "change_this_password")
        self.server_tcp_port = self.config.get("SERVER_PORT", 5000)
        
    def load_config(self):
        config_path = "client_config.json"
        default_config = {
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
    
    # ======================================================
    # PHẦN GIAO THỨC VÀ KẾT NỐI (TCP/UDP)
    # ======================================================

    def send_message(self, sock, msg_type, payload):
        """ Hàm trợ giúp để gửi dữ liệu theo giao thức """
        if not sock:
            raise ConnectionError("Socket không hợp lệ")
        
        data_length = len(payload)
        # [LOẠI: 5 byte][ĐỘ DÀI: 10 byte]
        header = f"{msg_type:<5}{data_length:010d}".encode('utf-8')
        
        sock.sendall(header)
        sock.sendall(payload)

    def discover_server(self, session_id):
        """ Phần UDP Discovery (giữ nguyên) """
        print(f"Đang tìm server cho mã lớp {session_id}...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(3.0) # Chờ 3 giây
            
            message = f"DISCOVER_SERVER:{session_id}".encode('utf-8')
            sock.sendto(message, ('<broadcast>', 9999))
            
            while True:
                data, addr = sock.recvfrom(1024)
                response = data.decode('utf-8')
                parts = response.split(":")
                if len(parts) == 3 and parts[0] == "SERVER_FOUND":
                    print(f"Tìm thấy server tại: {parts[1]}:{parts[2]}")
                    sock.close()
                    # Trả về IP (parts[1]) và Port (parts[2])
                    return parts[1], int(parts[2])
        except socket.timeout:
            print("Không tìm thấy server (timeout).")
            sock.close()
            return None, None
        except Exception as e:
            print(f"Lỗi discovery: {e}")
            sock.close()
            return None, None

    def connect_to_server(self):
        # 1. Tìm server bằng UDP
        ip, port = self.discover_server(self.session_id)
        if not ip:
            print("Không tìm thấy server. Thử lại sau 5s...")
            return False
        
        # Port từ discovery là port TCP server
        self.server_tcp_port = port 
        
        try:
            # 2. Kết nối tới server bằng TCP
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((ip, self.server_tcp_port))
            print(f"Đã kết nối TCP đến {ip}:{self.server_tcp_port}")
            
            # 3. Gửi tin nhắn đăng ký (REG)
            metadata = {
                "username": getpass.getuser(),
                "hostname": socket.gethostname(),
                "ip": socket.gethostbyname(socket.gethostname()),
                "session_id": self.session_id
            }
            payload = json.dumps(metadata).encode('utf-8')
            
            self.send_message(self.tcp_socket, "REG", payload)
            
            self.is_connected = True
            return True
        except socket.error as e:
            print(f"Lỗi kết nối TCP: {e}")
            self.is_connected = False
            if self.tcp_socket:
                self.tcp_socket.close()
            self.tcp_socket = None
            return False
        except Exception as e:
            print(f"Lỗi không xác định khi kết nối: {e}")
            return False

    def start_capture(self):
        """ Bắt đầu vòng lặp chụp và gửi ảnh """
        def capture_loop():
            while not self.stop_event.is_set():
                if not self.is_connected or not self.tcp_socket:
                    print("Mất kết nối. Đang thử kết nối lại...")
                    if self.connect_to_server():
                        print("Kết nối lại thành công!")
                    else:
                        time.sleep(5) # Chờ 5s trước khi thử lại
                        continue # Quay lại đầu vòng lặp
                
                try:
                    # --- Phần chụp, resize, mã hóa (giữ nguyên) ---
                    img = pyautogui.screenshot()
                    
                    max_width = self.config["MAX_WIDTH"]
                    if img.width > max_width:
                        w_percent = (max_width / float(img.width))
                        h_size = int((float(img.height) * float(w_percent)))
                        img = img.resize((max_width, h_size), Image.LANCZOS)

                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=self.config["JPEG_QUALITY"])
                    img_bytes = img_byte_arr.getvalue()
                    
                    encrypted = self.encrypt_bytes(img_bytes, self.password)
                    # --- Hết phần xử lý ảnh ---
                    
                    # 4. Gửi tin nhắn ảnh (IMG)
                    self.send_message(self.tcp_socket, "IMG", encrypted)
                    
                    time.sleep(self.config["CAPTURE_INTERVAL"])
                
                except (socket.error, ConnectionResetError, BrokenPipeError, ConnectionError) as e:
                    print(f"Mất kết nối server khi đang gửi. Lỗi: {e}")
                    self.is_connected = False
                    if self.tcp_socket:
                        self.tcp_socket.close()
                    self.tcp_socket = None
                    # Vòng lặp sẽ tự động chạy lại logic kết nối ở lần lặp sau
                
                except Exception as e:
                    print(f"Lỗi trong vòng lặp chụp/gửi: {e}")
                    time.sleep(1)
                        
        threading.Thread(target=capture_loop, daemon=True).start()
    
    def encrypt_bytes(self, data: bytes, password: str) -> bytes:
        """ Hàm mã hóa (giữ nguyên) """
        key = hashlib.sha256(password.encode()).digest()
        out = bytearray(data)
        for i in range(len(out)):
            out[i] ^= key[i % len(key)]
        return b"XORv1" + bytes(out) # Thêm prefix để server nhận diện
    
    def disconnect(self):
        self.stop_event.set()
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None
        self.is_connected = False
        print("Đã ngắt kết nối")

def main():
    if len(sys.argv) < 2:
        print("Cần nhập mã lớp! Ví dụ: python client.py ABC123")
        return
    
    session_id = sys.argv[1].upper()
    client = RemoteMonitorClient()
    client.session_id = session_id
    
    if client.connect_to_server():
        client.start_capture() # Bắt đầu gửi ảnh
        print("Client đang chạy. Nhấn Ctrl+C để dừng.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            client.disconnect()
            print("Đã dừng client.")
    else:
        print("Không thể kết nối đến server. Vui lòng thử lại.")

if __name__ == "__main__":
    main()