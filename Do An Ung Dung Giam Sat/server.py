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

# Định nghĩa kích thước header cho giao thức
HEADER_LENGTH = 15


class ServerMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GIÁM SÁT MÁY TÍNH QUA MẠNG (TCP/UDP)")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2c3e50')

        self.connected_clients = {}
        self.open_detail_windows = {}  # Lưu {cid: (window, image_label)}
        self.computer_counter = 1

        self.config = self.load_config()
        self.server_port = self.config.get("SERVER_PORT", 5000)
        self.password = self.config.get("PASSWORD", "change_this_password")

        self.server_socket = None

        self.setup_tcp_server()
        self.start_discovery_server()  # UDP Discovery
        self.setup_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ======================================================
    # CONFIG
    # ======================================================
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

    # ======================================================
    # TCP SERVER
    # ======================================================
    def setup_tcp_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.server_port))
            self.server_socket.listen(10)
            print(f"Server TCP đang lắng nghe trên port {self.server_port}...")

            self.accept_thread = threading.Thread(target=self.accept_connections, daemon=True)
            self.accept_thread.start()
        except Exception as e:
            messagebox.showerror("Lỗi Server TCP", f"Không thể khởi động server: {e}")
            self.root.destroy()

    def accept_connections(self):
        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                print(f"Chấp nhận kết nối từ {client_address}")

                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address), daemon=True)
                client_thread.start()
        except OSError:
            print("Socket server đã đóng.")
        except Exception as e:
            print(f"Lỗi accept_connections: {e}")

    def handle_client(self, client_socket, client_address):
        client_id = f"{client_address[0]}:{client_address[1]}"
        computer_name = ""
        try:
            # --- Nhận tin nhắn đăng ký ---
            header = self.recv_all(client_socket, HEADER_LENGTH)
            if not header:
                raise ConnectionError("Client ngắt kết nối trước khi đăng ký")

            msg_type = header[0:5].decode('utf-8').strip()
            data_length = int(header[5:15].decode('utf-8'))

            if msg_type != 'REG' or data_length <= 0:
                print(f"Tin nhắn đầu tiên không phải REG từ {client_id}")
                client_socket.close()
                return

            reg_data_bytes = self.recv_all(client_socket, data_length)
            data = json.loads(reg_data_bytes.decode('utf-8'))

            username = data.get('username', 'Unknown')
            hostname = data.get('hostname', 'Unknown')

            computer_name = f"MAY {self.computer_counter}"
            self.computer_counter += 1

            new_client_info = {
                'sid': client_id,
                'computer_name': computer_name,
                'username': username,
                'hostname': hostname,
                'status': 'online',
                'last_seen': time.time(),
                'image_data': None,
                'socket': client_socket
            }

            self.connected_clients[client_id] = new_client_info
            self.root.after(0, self.update_computers_display)

            # --- Vòng lặp nhận ảnh ---
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
                    self.connected_clients[client_id]['image_data'] = decrypted
                    self.connected_clients[client_id]['last_seen'] = time.time()
                    self.connected_clients[client_id]['status'] = 'online'

                    # Cập nhật UI
                    if self.is_detail_window_open(client_id):
                        self.root.after(0, self.update_detail_window, client_id)
                    self.root.after(0, self.update_computers_display_status, client_id, 'online')
                    # ✅ Cập nhật luôn thumbnail trên giao diện chính
                    self.root.after(0, self.update_computers_display)

                except Exception as e:
                    print(f"Lỗi giải mã ảnh từ {client_id}: {e}")

        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, ConnectionError) as e:
            print(f"Client {client_id} ({computer_name}) ngắt kết nối: {e}")
        except Exception as e:
            print(f"Lỗi khi xử lý client {client_id}: {e}")
        finally:
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['status'] = 'offline'
                self.root.after(0, self.update_computers_display_status, client_id, 'offline')
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

    # ======================================================
    # UI
    # ======================================================
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg='#34495e', height=60)
        header_frame.pack(fill='x')
        tk.Label(header_frame, text="BẢNG ĐIỀU KHIỂN GIÁM SÁT",
                 font=('Arial', 20, 'bold'), fg='white', bg='#34495e').pack(pady=10)

        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)

        self.computers_frame = tk.Frame(main_frame, bg='#34495e')
        self.computers_frame.pack(fill='both', expand=True)

        self.update_computers_display()

    def update_computers_display(self):
        for widget in self.computers_frame.winfo_children():
            widget.destroy()

        if not self.connected_clients:
            tk.Label(self.computers_frame, text="Đang chờ máy tính kết nối...",
                     font=('Arial', 18), bg='#34495e', fg='white').pack(expand=True)
            return

        row, col = 0, 0
        max_cols = 5

        for cid, info in self.connected_clients.items():
            computer_frame = tk.Frame(self.computers_frame, bg='#ecf0f1', relief='raised', borderwidth=2)
            computer_frame.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')

            name = f"{info['computer_name']}\n({info['hostname']})"
            tk.Label(computer_frame, text=name, font=('Arial', 12, 'bold'), bg='#ecf0f1').pack(pady=5)

            status_color = 'green' if info['status'] == 'online' else 'red'
            status_label = tk.Label(computer_frame, text=info['status'].upper(),
                                    font=('Arial', 10, 'bold'), fg=status_color, bg='#ecf0f1')
            status_label.pack(pady=2)

            if info['image_data']:
                try:
                    img = Image.open(io.BytesIO(info['image_data']))
                    img.thumbnail((200, 120), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    img_label = tk.Label(computer_frame, image=photo, bg='black')
                    img_label.image = photo
                    img_label.pack(padx=5, pady=5)
                except:
                    tk.Label(computer_frame, text="Lỗi ảnh", bg='black', fg='red').pack(padx=5, pady=5)
            else:
                tk.Label(computer_frame, text="Chưa có hình ảnh",
                         height=7, width=28, bg='black', fg='white').pack(padx=5, pady=5)

            computer_frame.bind("<Double-1>", lambda e, c=cid: self.on_client_double_click(c))
            for child in computer_frame.winfo_children():
                child.bind("<Double-1>", lambda e, c=cid: self.on_client_double_click(c))

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def update_computers_display_status(self, cid, status):
        info = self.connected_clients.get(cid)
        if not info:
            return

        info['status'] = status
        if status == 'online':
            info['last_seen'] = time.time()

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

        image_label = tk.Label(win, bg='black')
        image_label.pack(pady=10, expand=True, fill='both')

        self.open_detail_windows[cid] = (win, image_label)
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

        win, image_label = self.open_detail_windows[cid]
        info = self.connected_clients.get(cid)

        if info and info['image_data']:
            try:
                img = Image.open(io.BytesIO(info['image_data']))

                win_width = image_label.winfo_width()
                win_height = image_label.winfo_height()
                if win_width > 1 and win_height > 1:
                    img.thumbnail((win_width - 20, win_height - 20), Image.LANCZOS)
                else:
                    img.thumbnail((780, 580), Image.LANCZOS)

                photo = ImageTk.PhotoImage(img)
                image_label.config(image=photo)
                image_label.image = photo
            except Exception as e:
                print(f"Lỗi update ảnh chi tiết: {e}")

    # ======================================================
    # UDP DISCOVERY
    # ======================================================
    def start_discovery_server(self):
        def discovery_loop():
            try:
                udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                udp_socket.bind(('', 9999))
                print("Server UDP (Discovery) đang lắng nghe trên port 9999")

                while True:
                    data, addr = udp_socket.recvfrom(1024)
                    message = data.decode('utf-8')
                    parts = message.split(":")
                    if len(parts) == 2 and parts[0] == "DISCOVER_SERVER":
                        session_id = parts[1]

                        try:
                            with open("session.json", "r") as f:
                                server_session = json.load(f).get("session_id")

                            if session_id == server_session:
                                # ✅ Lấy IP LAN chính xác
                                ip = socket.gethostbyname(socket.getfqdn())
                                if ip.startswith("127."):
                                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                                    try:
                                        s.connect(("8.8.8.8", 80))
                                        ip = s.getsockname()[0]
                                    except:
                                        pass
                                    s.close()

                                response = f"SERVER_FOUND:{ip}:{self.server_port}"
                                udp_socket.sendto(response.encode('utf-8'), addr)
                                print(f"Đã phản hồi discovery cho {addr} với IP {ip}")
                        except FileNotFoundError:
                            print("Không tìm thấy file session.json")
                        except Exception as e:
                            print(f"Lỗi đọc session.json: {e}")
            except Exception as e:
                print(f"Lỗi server UDP: {e}")

        threading.Thread(target=discovery_loop, daemon=True).start()

    def on_close(self):
        print("Đang đóng server...")
        if self.server_socket:
            self.server_socket.close()
        for client_info in self.connected_clients.values():
            if client_info.get('socket'):
                try:
                    client_info['socket'].close()
                except:
                    pass
        self.root.destroy()


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = ServerMonitorGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"Lỗi khởi động GUI: {e}")
