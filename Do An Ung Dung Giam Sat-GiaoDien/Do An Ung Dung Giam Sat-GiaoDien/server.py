import tkinter as tk
from tkinter import messagebox
import threading
import time
from PIL import Image, ImageTk, ImageOps
import io
import base64
import hashlib
import socket
import json
import os

HEADER_LENGTH = 15


class ServerMonitorGUI:
    def __init__(self, root):
        """Khởi tạo giao diện và cấu hình server"""
        self.root = root
        self.root.title("GIÁM SÁT MÁY TÍNH QUA MẠNG (TCP/UDP)")
        self.root.geometry("1600x800")
        self.root.configure(bg='#2c3e50')

        # Biến trạng thái
        self.connected_clients = {}
        self.open_detail_windows = {}
        self.computer_counter = 1
        self.selected_client = None
        self.alert_label = None

        # Tải cấu hình
        self.config = self.load_config()
        self.server_port = self.config.get("SERVER_PORT", 5000)
        self.password = self.config.get("PASSWORD", "change_this_password")
        self.server_socket = None

        # Thiết lập server
        self.setup_tcp_server()
        self.start_discovery_server()

        # Giao diện
        self.setup_ui()

        # Sự kiện khi đóng cửa sổ
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =================== CONFIG ===================
    def load_config(self):
        """Tải cấu hình từ tệp JSON hoặc tạo mới nếu không có"""
        config_path = "config.json"
        default_config = {"SERVER_PORT": 5000, "PASSWORD": "change_this_password"}

        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        else:
            with open(config_path, "w") as f:
                json.dump(default_config, f, indent=2)
            return default_config

    # =================== TCP SERVER ===================
    def setup_tcp_server(self):
        """Thiết lập server TCP để lắng nghe kết nối từ client"""
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
        """Chấp nhận các kết nối từ client"""
        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                print(f"Chấp nhận kết nối từ {client_address}")
                threading.Thread(
                    target=self.handle_client, args=(client_socket, client_address), daemon=True
                ).start()
        except OSError:
            print("Socket server đã đóng.")

    def handle_client(self, client_socket, client_address):
        """Xử lý kết nối và nhận dữ liệu từ client"""
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
                'blocked': False,
                'status': 'online',
                'last_seen': time.time(),
                'image_data': None,
                'socket': client_socket
            }

            self.root.after(0, self.update_computers_display)

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
        """Nhận toàn bộ dữ liệu từ client"""
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data

    def send_message(self, sock, msg_type, payload: bytes):
        """Gửi dữ liệu tới client theo header chung (5 byte type, 10 byte length)"""
        if not sock:
            raise ConnectionError("Socket không hợp lệ")
        data_length = len(payload)
        header = f"{msg_type:<5}{data_length:010d}".encode('utf-8')
        sock.sendall(header)
        sock.sendall(payload)

    def decrypt_bytes(self, payload: bytes, password: str) -> bytes:
        """Giải mã dữ liệu hình ảnh từ client"""
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
        """Thiết lập giao diện người dùng"""
        header_frame = tk.Frame(self.root, bg='#1e272e', height=90)
        header_frame.pack(fill='x')
        tk.Label(
            header_frame, text="BẢNG ĐIỀU KHIỂN GIÁM SÁT",
            font=('Arial', 20, 'bold'), fg='white', bg='#1e272e'
        ).pack(pady=10)

        # ==== Nút điều khiển ====
        bottom_frame = tk.Frame(self.root, bg='#1e272e')
        bottom_frame.pack(fill='x', padx=20, pady=10)

        block_button = tk.Button(
            bottom_frame, text="🛑 BLOCK", command=self.block_action,
            bg="red", fg="white", font=('Arial', 14, 'bold')
        )
        block_button.grid(row=0, column=0, padx=20)

        shutdown_button = tk.Button(
            bottom_frame, text="⚡ SHUTDOWN", command=self.shutdown_action,
            bg="orange", fg="white", font=('Arial', 14, 'bold')
        )
        shutdown_button.grid(row=0, column=1, padx=20)

        self.alert_label = tk.Label(
            bottom_frame, text="", font=('Arial', 14, 'bold'),
            bg="#1e272e", fg="white", pady=5
        )
        self.alert_label.grid(row=0, column=2, columnspan=2, pady=5, sticky="ew")

        admin_label = tk.Label(
            bottom_frame, text="ADMIN", font=('Arial', 14, 'bold'),
            fg="white", bg="#1e272e"
        )
        admin_label.grid(row=0, column=4, padx=10, sticky="e")

        try:
            with open("session.json", "r") as f:
                session_data = json.load(f)
                class_code = session_data.get("session_id", "N/A")
        except Exception:
            class_code = "N/A"

        class_label = tk.Label(
            bottom_frame, text=f"CODE: {class_code}",
            font=('Arial', 14, 'bold'), fg="#4dffa3", bg="#1e272e"
        )
        class_label.grid(row=0, column=5, padx=20, sticky="e")

        bottom_frame.grid_columnconfigure(2, weight=1)

        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)

        self.computers_frame = tk.Frame(main_frame, bg='#1e272e')
        self.computers_frame.pack(fill='both', expand=True)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.update_computers_display()

    def update_computers_display(self):
        """Cập nhật danh sách máy tính kết nối"""
        for widget in self.computers_frame.winfo_children():
            widget.destroy()

        if not self.connected_clients:
            tk.Label(
                self.computers_frame, text="Đang chờ máy tính kết nối...",
                font=('Arial', 18), bg='#1e272e', fg='white'
            ).pack(expand=True)
            return

        row, col = 0, 0
        for cid, info in self.connected_clients.items():
            frame = tk.Frame(
                self.computers_frame, bg='#ecf0f1',
                relief='raised', borderwidth=3, width=700, height=500
            )
            frame.grid(row=row, column=col, padx=20, pady=20, sticky='nsew')
            frame.grid_propagate(False)

            top_info = tk.Frame(frame, bg='#ecf0f1')
            top_info.pack(fill='x', pady=(10, 0), padx=10)

            # Show name and indicate if the machine is blocked
            name_text = f"{info['computer_name']} ({info['hostname']})"
            if info.get('blocked'):
                name_text += " [KHÓA]"

            name_label = tk.Label(
                top_info,
                text=name_text,
                font=('Arial', 14, 'bold'), bg='#ecf0f1', fg='#2c3e50'
            )
            name_label.pack(side='left', anchor='w')

            # If blocked, show a BLOCKED status; otherwise show online/offline
            if info.get('blocked'):
                status_color = 'orange'
                status_text = '● BLOCKED'
            else:
                status_color = 'green' if info['status'] == 'online' else 'red'
                status_text = f"● {info['status'].upper()}"

            status_label = tk.Label(
                top_info, text=status_text,
                font=('Arial', 12, 'bold'), fg=status_color, bg='#ecf0f1'
            )
            status_label.pack(side='right', anchor='e')

            img_area = tk.Frame(frame, bg='black', width=450, height=300)
            img_area.pack(pady=20)
            img_area.pack_propagate(False)

            if info['image_data']:
                try:
                    display_w, display_h = 450, 250
                    img = Image.open(io.BytesIO(info['image_data']))
                    img = img.resize((display_w, display_h), Image.LANCZOS)

                    photo = ImageTk.PhotoImage(img)
                    lbl = tk.Label(img_area, image=photo, bg='black')
                    lbl.image = photo
                    lbl.pack(expand=True, fill='both')
                except:
                    tk.Label(img_area, text="Lỗi ảnh", bg='black', fg='red').pack()
            else:
                tk.Label(
                    img_area, text="Chưa có hình ảnh",
                    bg='black', fg='white', font=('Arial', 12)
                ).pack(expand=True)

            frame.bind("<Button-1>", lambda e, c=cid: self.on_client_click(c))
            for child in frame.winfo_children():
                child.bind("<Button-1>", lambda e, c=cid: self.on_client_click(c))

            # Visually mark selected client
            if cid == self.selected_client:
                try:
                    frame.config(relief='solid', borderwidth=5)
                except Exception:
                    pass

            col += 1
            if col >= 3:
                col = 0
                row += 1

    # =================== ACTIONS ===================
    def block_action(self):
        """Gửi lệnh BLOCK hoặc UNBLOCK tới client đã chọn"""
        if not self.selected_client:
            messagebox.showinfo("Chọn máy", "Vui lòng chọn một máy để BLOCK/UNBLOCK (click vào ô máy).")
            return

        cid = self.selected_client
        client_info = self.connected_clients.get(cid)
        if not client_info:
            messagebox.showinfo("Lỗi", "Không tìm thấy máy đã chọn.")
            return

        sock = client_info.get('socket')
        if not sock:
            messagebox.showinfo("Lỗi", "Socket của máy không khả dụng.")
            return

        # Toggle blocked state
        currently_blocked = bool(client_info.get('blocked'))
        action = 'UNBLOCK' if currently_blocked else 'BLOCK'

        confirm_text = (
            f"Bạn có chắc muốn mở khóa {client_info['computer_name']}?" if currently_blocked
            else f"Bạn có chắc muốn khóa {client_info['computer_name']} (chặn người dùng)?"
        )

        if not messagebox.askyesno("Xác nhận", confirm_text):
            return

        try:
            payload = json.dumps({'action': action}).encode('utf-8')
            self.send_message(sock, 'CMD', payload)

            # Update server-side state
            client_info['blocked'] = not currently_blocked

            # Update UI and show alert
            verb = 'mở khóa' if currently_blocked else 'khóa'
            self.alert_label.config(
                text=f"⚠️ Đã {verb} {client_info['computer_name']}",
                bg="#e67e22"
            )
            self.root.after(5000, lambda: self.alert_label.config(text="", bg=self.root["bg"]))
            self.root.after(0, self.update_computers_display)
        except Exception as e:
            messagebox.showerror("Lỗi gửi lệnh", f"Không thể gửi lệnh {action}: {e}")

    def shutdown_action(self):
        """Gửi lệnh tắt máy tới client đang chọn"""
        if not self.selected_client:
            messagebox.showinfo("Chọn máy", "Vui lòng chọn một máy để SHUTDOWN (click vào ô máy).")
            return

        cid = self.selected_client
        client_info = self.connected_clients.get(cid)
        if not client_info:
            messagebox.showinfo("Lỗi", "Không tìm thấy máy đã chọn.")
            return

        if messagebox.askyesno("Xác nhận", 
            f"Bạn có chắc muốn tắt máy {client_info['computer_name']} ({client_info['hostname']}) không?"):
            
            sock = client_info.get('socket')
            if not sock:
                messagebox.showinfo("Lỗi", "Socket của máy không khả dụng.")
                return

            try:
                payload = json.dumps({'action': 'SHUTDOWN'}).encode('utf-8')
                self.send_message(sock, 'CMD', payload)
                self.alert_label.config(
                    text=f"⚠️ Đã gửi lệnh SHUTDOWN tới {client_info['computer_name']}", 
                    bg="#e74c3c"
                )
                self.root.after(5000, lambda: self.alert_label.config(text="", bg=self.root["bg"]))
            except Exception as e:
                messagebox.showerror("Lỗi gửi lệnh", f"Không thể gửi lệnh SHUTDOWN: {e}")

    def handle_client_disconnect(self, name):
        self.update_computers_display()
        msg = f"⚠️ {name} đã ngắt kết nối!"
        print(msg)
        self.alert_label.config(text=msg, bg="#e74c3c")
        self.root.after(10000, lambda: self.alert_label.config(text="", bg=self.root["bg"]))

    def on_client_click(self, cid):
        """Mở cửa sổ chi tiết khi click 1 lần vào máy tính"""
        if cid in self.connected_clients:
            # Set currently selected client for actions like BLOCK/SHUTDOWN
            self.selected_client = cid
            info = self.connected_clients[cid]
            try:
                self.alert_label.config(text=f"Đã chọn: {info['computer_name']} ({info['hostname']})", bg="#3498db")
                self.root.after(5000, lambda: self.alert_label.config(text="", bg=self.root["bg"]))
            except Exception:
                pass

            if cid in self.open_detail_windows and self.open_detail_windows[cid][0].winfo_exists():
                self.open_detail_windows[cid][0].lift()
                return
            self.create_detail_window(cid)

    def create_detail_window(self, cid):
        """Tạo cửa sổ chi tiết cho máy tính (phiên bản cải tiến có icon & giao diện đẹp)"""
        info = self.connected_clients[cid]
        win = tk.Toplevel(self.root)
        win.title(f"👁️ Giám sát: {info['computer_name']}")
        win.geometry("900x650")
        win.configure(bg="#1e272e")

        # --- Header ---
        header_frame = tk.Frame(win, bg="#2f3640")
        header_frame.pack(fill="x", pady=(10, 0), padx=10)

        title_label = tk.Label(
            header_frame,
            text=f"🖥️ ĐANG GIÁM SÁT: {info['computer_name']}",
            font=("Segoe UI", 18, "bold"),
            bg="#2f3640",
            fg="#00a8ff",
            pady=10
        )
        title_label.pack()

        sub_label = tk.Label(
            header_frame,
            text=f"👤 User: {info['username']}                        💻 Host: {info['hostname']}",
            font=("Segoe UI", 12),
            bg="#2f3640",
            fg="#dcdde1",
            pady=5
        )
        sub_label.pack()

        # --- Ảnh giám sát ---
        img_frame = tk.Frame(win, bg="black", relief="ridge", bd=3)
        img_frame.pack(expand=True, fill="both", padx=20, pady=20)

        img_label = tk.Label(img_frame, bg="black")
        img_label.pack(expand=True, fill="both")

        # --- Nút thoát ---
        control_frame = tk.Frame(win, bg="#1e272e")
        control_frame.pack(pady=(0, 20))

        close_icon = "↩️"  # mũi tên thoát
        close_btn = tk.Button(
            control_frame,
            text=f"{close_icon}  THOÁT",
            font=("Segoe UI", 12, "bold"),
            command=lambda: self.on_detail_window_close(cid),
            bg="#c23616",
            fg="white",
            activebackground="#e84118",
            activeforeground="white",
            relief="flat",
            padx=15,
            pady=5,
            cursor="hand2"
        )
        close_btn.pack()

        # --- Ghi nhận cửa sổ ---
        self.open_detail_windows[cid] = (win, img_label)
        win.protocol("WM_DELETE_WINDOW", lambda: self.on_detail_window_close(cid))

        # --- Hiển thị ảnh đầu tiên ---
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
        """Khởi tạo server UDP phát hiện"""
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

    # =================== EXIT ===================
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
