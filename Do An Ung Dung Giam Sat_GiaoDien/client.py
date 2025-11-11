import pyautogui
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
import tkinter as tk
from tkinter import messagebox
from queue import Queue
import keyboard

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

        self.block_window = None
        self.allow_remote_control = False

        self.mouse_locking = False  # ✅ khóa chuột
        self.command_queue = Queue()

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

    def send_message(self, sock, msg_type, payload):
        header = f"{msg_type:<5}{len(payload):010d}".encode()
        sock.sendall(header + payload)

    def recv_all(self, sock, n):
        data = bytearray()
        while len(data) < n:
            part = sock.recv(n - len(data))
            if not part:
                return None
            data.extend(part)
        return data

    def queue_command(self, action):
        self.command_queue.put(action)

    def process_commands(self):
        while not self.command_queue.empty():
            action = self.command_queue.get()

            if not self.allow_remote_control:
                if not self.ask_permission_gui():
                    print("❌ User từ chối Admin điều khiển")
                    return
                self.allow_remote_control = True

            if action == "BLOCK":
                self.show_block_screen()
            elif action == "UNBLOCK":
                self.hide_block_screen()
            elif action == "SHUTDOWN":
                self.shutdown_computer()

        self.root.after(300, self.process_commands)

    def ask_permission_gui(self):
        return messagebox.askyesno(
            "XÁC NHẬN QUYỀN",
            "Admin muốn khóa màn hình hoặc tắt máy.\nBạn có cho phép không?"
        )

    def listen_server(self):
        try:
            while self.is_connected and self.tcp_socket:
                header = self.recv_all(self.tcp_socket, HEADER_LENGTH)
                if not header:
                    break

                msg_type = header[:5].decode().strip()
                data_length = int(header[5:15].decode())
                if data_length <= 0:
                    continue

                payload = self.recv_all(self.tcp_socket, data_length)
                if not payload:
                    break

                if msg_type == "CMD":
                    data = json.loads(payload.decode())
                    action = data.get("action", "").upper()
                    print("→ Lệnh từ server:", action)
                    self.queue_command(action)

        except Exception as e:
            print("Mất kết nối server:", e)

        self.is_connected = False

    def discover_server(self, session_id):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(3)

            sock.sendto(f"DISCOVER_SERVER:{session_id}".encode(), ("<broadcast>", 9999))

            while True:
                data, addr = sock.recvfrom(1024)
                parts = data.decode().split(":")
                if len(parts) == 3 and parts[0] == "SERVER_FOUND":
                    return parts[1], int(parts[2])

        except:
            return None, None
        finally:
            sock.close()

    def connect_to_server(self):
        ip, port = self.discover_server(self.session_id)
        if not ip:
            print("Không tìm thấy server")
            return False

        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.connect((ip, port))

            payload = json.dumps({
                "username": getpass.getuser(),
                "hostname": socket.gethostname(),
            }).encode()

            self.send_message(self.tcp_socket, "REG", payload)
            self.is_connected = True
            threading.Thread(target=self.listen_server, daemon=True).start()
            return True

        except Exception as e:
            print("Lỗi kết nối:", e)
            return False

    def start_capture(self):
        def loop():
            while not self.stop_event.is_set():
                if not self.is_connected:
                    time.sleep(1)
                    continue

                try:
                    img = pyautogui.screenshot()
                    img = img.resize((800, 450))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=60)
                    enc = self.encrypt(buf.getvalue(), self.password)

                    self.send_message(self.tcp_socket, "IMG", enc)
                    time.sleep(self.config["CAPTURE_INTERVAL"])

                except:
                    self.is_connected = False

        threading.Thread(target=loop, daemon=True).start()

    def encrypt(self, data, pwd):
        key = hashlib.sha256(pwd.encode()).digest()
        out = bytearray(data)
        for i in range(len(out)):
            out[i] ^= key[i % len(key)]
        return b"XORv1" + bytes(out)

    # ✅ KHÓA CHUỘT
    def lock_mouse_loop(self):
        screen_w, screen_h = pyautogui.size()
        center_x, center_y = screen_w // 2, screen_h // 2

        while self.mouse_locking:
            try:
                pyautogui.moveTo(center_x, center_y)
                time.sleep(0.05)
            except:
                pass

    # ✅ ẨN TASKBAR
    def hide_taskbar(self):
        os.system('powershell -command "$t=(New-Object -Com Shell.Application).Tray; $t.Hide()"')

    def show_taskbar(self):
        os.system('powershell -command "$t=(New-Object -Com Shell.Application).Tray; $t.Show()"')

    # ✅ BLOCK FULL
    def show_block_screen(self):
        if self.block_window:
            return

        self.block_window = tk.Toplevel(self.root)
        self.block_window.attributes("-fullscreen", True)
        self.block_window.configure(bg="black")
        self.block_window.focus_force()
        self.block_window.lift()
        self.block_window.attributes("-topmost", True)

        keys_to_block = [
            "alt+tab", "alt+f4", "win", "win+tab",
            "ctrl+esc", "ctrl+shift+esc", "alt+esc"
        ]
        for k in keys_to_block:
            try:
                keyboard.block_key(k)
            except:
                pass

        self.hide_taskbar()

        # ✅ Khóa chuột
        self.mouse_locking = True
        threading.Thread(target=self.lock_mouse_loop, daemon=True).start()

        tk.Label(
            self.block_window,
            text="⛔ MÁY TÍNH ĐÃ BỊ KHÓA ⛔",
            fg="red",
            bg="black",
            font=("Arial", 48, "bold")
        ).pack(expand=True)

    # ✅ MỞ KHÓA
    def hide_block_screen(self):
        if self.block_window:
            self.block_window.destroy()
            self.block_window = None

        try:
            keyboard.unhook_all()
        except:
            pass

        self.mouse_locking = False
        self.show_taskbar()

    def shutdown_computer(self):
        os.system("shutdown /s /t 10")
        messagebox.showwarning("Thông báo", "Máy sẽ tắt sau 10 giây!")

    def run(self):
        self.root = tk.Tk()
        self.root.withdraw()

        if not self.connect_to_server():
            print("Không kết nối được server.")
            return

        self.start_capture()
        self.root.after(300, self.process_commands)
        self.root.mainloop()


def main():
    if len(sys.argv) < 2:
        print("Dùng: python client.py ABC123")
        return

    sc = RemoteMonitorClient()
    sc.session_id = sys.argv[1].upper()
    sc.run()


if __name__ == "__main__":
    main()
