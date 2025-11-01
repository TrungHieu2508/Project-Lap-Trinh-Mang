import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from PIL import Image, ImageTk
import io
import base64
import hashlib
import socket
import json
import os

HEADER_LENGTH = 15


class ServerMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GIÁM SÁT MÁY TÍNH QUA MẠNG (TCP/UDP)")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2c3e50')

        self.connected_clients = {}
        self.open_detail_windows = {}
        self.computer_counter = 1
        self.alert_label = None

        self.config = self.load_config()
        self.server_port = self.config.get("SERVER_PORT", 5000)
        self.password = self.config.get("PASSWORD", "change_this_password")

        self.server_socket = None

        self.setup_tcp_server()
        self.start_discovery_server()
        self.setup_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =================== CONFIG ===================
    def load_config(self):
        config_path = "config.json"
        default_config = {
            "SERVER_PORT": 5000,
            "PASSWORD": "change_this_password"
        }
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        else:
            with open(config_path, "w") as f:
                json.dump(default_config, f, indent=2)
            return default_config

    # =================== TCP SERVER ===================
    def setup_tcp_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.server_port))
            self.server_socket.listen(10)
            print(f"Server TCP đang lắng nghe trên port {self.server_port}...")
            threading.Thread(target=self.accept_connections, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Lỗi Server TCP", f"Không thể khởi động server: {e}")
            self.root.destroy()

    def accept_connections(self):
        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                print(f"Chấp nhận kết nối từ {client_address}")
                threading.Thread(target=self.handle_client, args=(client_socket, client_address), daemon=True).start()
        except OSError:
            print("Socket server đã đóng.")

    def handle_client(self, client_socket, client_address):
        client_id = f"{client_address[0]}:{client_address[1]}"
        computer_name = ""
        try:
            header = self.recv_all(client_socket, HEADER_LENGTH)
            if not header:
                raise ConnectionError("Client ngắt kết nối trước khi đăng ký")

            msg_type = header[0:5].decode('utf-8').strip()
            data_length = int(header[5:15].decode('utf-8'))
            if msg_type != 'REG' or data_length <= 0:
                client_socket.close()
                return

            reg_data_bytes = self.recv_all(client_socket, data_length)
            data = json.loads(reg_data_bytes.decode('utf-8'))
            username = data.get('username', 'Unknown')
            hostname = data.get('hostname', 'Unknown')

            computer_name = f"MAY {self.computer_counter}"
            self.computer_counter += 1

            self.connected_clients[client_id] = {
                'sid': client_id,
                'computer_name': computer_name,
                'username': username,
                'hostname': hostname,
                'status': 'online',
                'last_seen': time.time(),
                'image_data': None,
                'socket': client_socket
            }

            self.root.after(0, self.update_computers_display)

            # --- Nhận ảnh liên tục ---
            while True:
                header = self.recv_all(client_socket, HEADER_LENGTH)
                if not header:
                    break
                msg_type = header[0:5].decode('utf-8').strip()
                data_length = int(header[5:15].decode('utf-8'))
                if msg_type != 'IMG' or data_length <= 0:
                    break
                image_data = self.recv_all(client_socket, data_length)
                if not image_data:
                    break

                try:
                    decrypted = self.decrypt_bytes(image_data, self.password)
                    client_info = self.connected_clients.get(client_id)
                    if client_info:
                        client_info['image_data'] = decrypted
                        client_info['last_seen'] = time.time()
                        client_info['status'] = 'online'

                    # Cập nhật UI
                    if self.is_detail_window_open(client_id):
                        self.root.after(0, self.update_detail_window, client_id)
                    self.root.after(0, self.update_computers_display)
                except Exception as e:
                    print(f"Lỗi giải mã ảnh từ {client_id}: {e}")

        except Exception as e:
            print(f"Client {client_id} ({computer_name}) ngắt kết nối: {e}")
        finally:
            if client_id in self.connected_clients:
                name = self.connected_clients[client_id]['computer_name']
                del self.connected_clients[client_id]
                self.root.after(0, lambda: self.handle_client_disconnect(name))
            client_socket.close()

    def recv_all(self, sock, n):
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data

    def decrypt_bytes(self, payload: bytes, password: str) -> bytes:
        if payload.startswith(b"XORv1"):
            data = payload[5:]
            key = hashlib.sha256(password.encode()).digest()
            out = bytearray(data)
            for i in range(len(out)):
                out[i] ^= key[i % len(key)]
            return bytes(out)
        else:
            try:
                return base64.b64decode(payload)
            except:
                raise ValueError("Định dạng ảnh không xác định")

    # =================== UI ===================
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg='#34495e', height=60)
        header_frame.pack(fill='x')
        tk.Label(header_frame, text="BẢNG ĐIỀU KHIỂN GIÁM SÁT",
                 font=('Arial', 20, 'bold'), fg='white', bg='#34495e').pack(pady=10)

        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)

        self.computers_frame = tk.Frame(main_frame, bg='#34495e')
        self.computers_frame.pack(fill='both', expand=True)

        self.alert_label = tk.Label(self.root, text="", font=('Arial', 14, 'bold'),
                                    bg="#e74c3c", fg="white", pady=5)
        self.alert_label.pack(fill='x')

        self.update_computers_display()

    def update_computers_display(self):
        for widget in self.computers_frame.winfo_children():
            widget.destroy()

        if not self.connected_clients:
            tk.Label(self.computers_frame, text="Đang chờ máy tính kết nối...",
                     font=('Arial', 18), bg='#34495e', fg='white').pack(expand=True)
            return

        row, col = 0, 0
        for cid, info in self.connected_clients.items():
            frame = tk.Frame(self.computers_frame, bg='#ecf0f1', relief='raised', borderwidth=2)
            frame.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')

            tk.Label(frame, text=f"{info['computer_name']}\n({info['hostname']})",
                     font=('Arial', 12, 'bold'), bg='#ecf0f1').pack(pady=5)

            tk.Label(frame, text=info['status'].upper(), font=('Arial', 10, 'bold'),
                     fg=('green' if info['status'] == 'online' else 'red'), bg='#ecf0f1').pack(pady=2)

            if info['image_data']:
                try:
                    img = Image.open(io.BytesIO(info['image_data']))
                    img.thumbnail((200, 120), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    lbl = tk.Label(frame, image=photo, bg='black')
                    lbl.image = photo
                    lbl.pack(padx=5, pady=5)
                except:
                    tk.Label(frame, text="Lỗi ảnh", bg='black', fg='red').pack()
            else:
                tk.Label(frame, text="Chưa có hình ảnh", bg='black', fg='white',
                         height=7, width=28).pack()

            frame.bind("<Double-1>", lambda e, c=cid: self.on_client_double_click(c))
            for child in frame.winfo_children():
                child.bind("<Double-1>", lambda e, c=cid: self.on_client_double_click(c))

            col += 1
            if col >= 5:
                col = 0
                row += 1

    def handle_client_disconnect(self, name):
        """Khi client thoát: xóa khỏi giao diện và hiển thị thông báo 10s"""
        self.update_computers_display()
        msg = f"⚠️ {name} đã ngắt kết nối!"
        print(msg)
        self.alert_label.config(text=msg, bg="#e74c3c")
        # Tự ẩn thông báo sau 10 giây
        self.root.after(10000, lambda: self.alert_label.config(text="", bg=self.root["bg"]))

    # =================== DETAIL WINDOW ===================
    def on_client_double_click(self, cid):
        if cid in self.connected_clients:
            if cid in self.open_detail_windows and self.open_detail_windows[cid][0].winfo_exists():
                self.open_detail_windows[cid][0].lift()
                return
            self.create_detail_window(cid)

    def create_detail_window(self, cid):
        info = self.connected_clients[cid]
        win = tk.Toplevel(self.root)
        win.title(f"Giám sát: {info['computer_name']}")
        win.geometry("800x600")
        win.configure(bg='#2c3e50')
        tk.Label(win, text=f"ĐANG GIÁM SÁT: {info['computer_name']}",
                 font=('Arial', 16, 'bold'), bg='#2c3e50', fg='white', pady=10).pack()
        tk.Label(win, text=f"User: {info['username']} | Host: {info['hostname']}",
                 font=('Arial', 12), bg='#2c3e50', fg='#bdc3c7').pack()

        img_label = tk.Label(win, bg='black')
        img_label.pack(pady=10, expand=True, fill='both')
        self.open_detail_windows[cid] = (win, img_label)
        win.protocol("WM_DELETE_WINDOW", lambda: self.on_detail_window_close(cid))
        self.update_detail_window(cid)

    def on_detail_window_close(self, cid):
        if cid in self.open_detail_windows:
            self.open_detail_windows[cid][0].destroy()
            del self.open_detail_windows[cid]

    def is_detail_window_open(self, cid):
        return cid in self.open_detail_windows and self.open_detail_windows[cid][0].winfo_exists()

    def update_detail_window(self, cid):
        if not self.is_detail_window_open(cid):
            return
        win, label = self.open_detail_windows[cid]
        info = self.connected_clients.get(cid)
        if not info or not info['image_data']:
            return
        try:
            img = Image.open(io.BytesIO(info['image_data']))
            w, h = label.winfo_width(), label.winfo_height()
            if w > 1 and h > 1:
                img.thumbnail((w - 20, h - 20), Image.LANCZOS)
            else:
                img.thumbnail((780, 580), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            label.config(image=photo)
            label.image = photo
        except Exception as e:
            print(f"Lỗi update ảnh chi tiết: {e}")

    # =================== DISCOVERY ===================
    def start_discovery_server(self):
        def discovery_loop():
            try:
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                udp.bind(('', 9999))
                print("Server UDP Discovery đang chạy...")
                while True:
                    data, addr = udp.recvfrom(1024)
                    msg = data.decode('utf-8')
                    parts = msg.split(":")
                    if len(parts) == 2 and parts[0] == "DISCOVER_SERVER":
                        with open("session.json", "r") as f:
                            sid = json.load(f).get("session_id")
                        if parts[1] == sid:
                            ip = socket.gethostbyname(socket.getfqdn())
                            if ip.startswith("127."):
                                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                                s.connect(("8.8.8.8", 80))
                                ip = s.getsockname()[0]
                                s.close()
                            reply = f"SERVER_FOUND:{ip}:{self.server_port}"
                            udp.sendto(reply.encode(), addr)
            except Exception as e:
                print(f"Lỗi Discovery: {e}")

        threading.Thread(target=discovery_loop, daemon=True).start()

    def on_close(self):
        print("Đang đóng server...")
        if self.server_socket:
            self.server_socket.close()
        for client in self.connected_clients.values():
            if client.get("socket"):
                try:
                    client["socket"].close()
                except:
                    pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ServerMonitorGUI(root)
    root.mainloop()
