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
import queue

HEADER_LENGTH = 15

class ServerMonitorGUI:
    def __init__(self, root):
        """Khởi tạo giao diện và cấu hình server"""
        self.root = root
        self.root.title("GIÁM SÁT MÁY TÍNH QUA MẠNG (TCP/UDP)")
        self.root.geometry("1600x800")
        self.root.configure(bg='#2c3e50')

        # Trạng thái
        self.connected_clients = {}   # dict cid -> info
        self.client_frames = {}       # chỉ chứa frame/area của các client đang hiển thị (visible)
        self.open_detail_windows = {}
        self.computer_counter = 1
        self.selected_client = None
        self.alert_label = None

        # Threading / sync
        self.lock = threading.Lock()
        self.image_queue = queue.Queue()
        # khi add/remove client -> rebuild grid once
        self.needs_full_refresh = True  # ĐẶT TRUE để lần đầu gọi update sẽ vẽ
        # Tải config
        self.config = self.load_config()
        self.server_port = self.config.get("SERVER_PORT", 5000)
        self.password = self.config.get("PASSWORD", "change_this_password")
        self.server_socket = None

        # --- PHÂN TRANG ---
        self.clients_per_page = 8
        self.current_page = 1
        self.total_pages = 1

        # Setup servers
        self.setup_tcp_server()
        self.start_discovery_server()

        # UI
        self.setup_ui()

        # Process image queue định kỳ (không chặn UI)
        self.root.after(100, self.process_image_queue)

        # Event close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =================== CONFIG ===================
    def load_config(self):
        config_path = "config.json"
        default_config = {"SERVER_PORT": 5000, "PASSWORD": "change_this_password"}
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    return json.load(f)
            else:
                with open(config_path, "w") as f:
                    json.dump(default_config, f, indent=2)
                return default_config
        except Exception:
            return default_config

    # =================== TCP SERVER ===================
    def setup_tcp_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.server_port))
            self.server_socket.listen(50)
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
                threading.Thread(
                    target=self.handle_client, args=(client_socket, client_address), daemon=True
                ).start()
        except OSError:
            print("Socket server đã đóng.")

    def handle_client(self, client_socket, client_address):
        """Xử lý kết nối và nhận dữ liệu từ client (worker thread)"""
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

            with self.lock:
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
                    'socket': client_socket,
                    'last_display': 0.0  # rate limit hiển thị
                }
                # Yêu cầu rebuild UI (vì số lượng client thay đổi)
                self.needs_full_refresh = True

            # request UI rebuild (1 lần)
            self.root.after(0, self.update_computers_display)

            while True:
                header = self.recv_all(client_socket, HEADER_LENGTH)
                if not header:
                    break

                msg_type = header[0:5].decode('utf-8').strip()
                data_length = int(header[5:15].decode('utf-8'))
                if msg_type != 'IMG' or data_length <= 0:
                    # nếu ko phải ảnh, ta break (giữ đơn giản)
                    break

                image_data = self.recv_all(client_socket, data_length)
                if not image_data:
                    break

                try:
                    decrypted = self.decrypt_bytes(image_data, self.password)

                    # debug log (bật khi cần)
                    # print(f"Nhận ảnh từ {client_id}: {len(image_data)} raw -> {len(decrypted)} sau giải mã")

                    # rate limit hiển thị mỗi client (ví dụ: 0.45s -> ~2.2 fps)
                    with self.lock:
                        client_info = self.connected_clients.get(client_id)
                        if client_info is None:
                            continue
                        now = time.time()
                        if now - client_info.get('last_display', 0) < 0.45:
                            # vẫn cập nhật last_seen nhưng skip hiển thị
                            client_info['last_seen'] = now
                            continue
                        client_info['last_display'] = now
                        # cập nhật dữ liệu ảnh
                        client_info['image_data'] = decrypted
                        client_info['last_seen'] = now
                        client_info['status'] = 'online'

                    # đẩy vào queue cho UI thread xử lý
                    self.image_queue.put((client_id, decrypted))

                except Exception as e:
                    print(f"Lỗi giải mã ảnh từ {client_id}: {e}")

        except Exception as e:
            print(f"Client {client_id} ({computer_name}) ngắt kết nối: {e}")
        finally:
            with self.lock:
                if client_id in self.connected_clients:
                    name = self.connected_clients[client_id]['computer_name']
                    del self.connected_clients[client_id]
                    # đảm bảo xóa khung hiển thị nếu tồn tại
                    if client_id in self.client_frames:
                        try:
                            frame, img_area = self.client_frames[client_id]
                            # destroy widgets an toàn
                            if hasattr(frame, 'destroy'):
                                frame.destroy()
                        except:
                            pass
                        del self.client_frames[client_id]
                    self.needs_full_refresh = True
                    self.root.after(0, lambda: self.handle_client_disconnect(name))
            try:
                client_socket.close()
            except:
                pass

    def recv_all(self, sock, n):
        data = bytearray()
        while len(data) < n:
            try:
                packet = sock.recv(n - len(data))
            except:
                return None
            if not packet:
                return None
            data.extend(packet)
        return data

    def send_message(self, sock, msg_type, payload: bytes):
        if not sock:
            raise ConnectionError("Socket không hợp lệ")
        data_length = len(payload)
        header = f"{msg_type:<5}{data_length:010d}".encode('utf-8')
        sock.sendall(header)
        sock.sendall(payload)

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
            except Exception:
                raise ValueError("Định dạng ảnh không xác định")

    # =================== UI ===================
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg='#1e272e', height=90)
        header_frame.pack(fill='x')
        tk.Label(
            header_frame, text="BẢNG ĐIỀU KHIỂN GIÁM SÁT",
            font=('Arial', 20, 'bold'), fg='white', bg='#1e272e'
        ).pack(pady=10)

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

        # vùng chứa các ô máy
        self.computers_frame = tk.Frame(main_frame, bg='#1e272e')
        self.computers_frame.pack(fill='both', expand=True)

        # Thanh phân trang
        self.pagination_frame = tk.Frame(main_frame, bg='#2c3e50')
        self.pagination_frame.pack(fill='x', pady=(5, 0))

        self.prev_button = tk.Button(
            self.pagination_frame, text="◀ Trang trước",
            font=('Arial', 12, 'bold'),
            command=self.prev_page,
            bg="#34495e", fg="white", activebackground="#2ecc71", relief="flat"
        )
        self.prev_button.pack(side='left', padx=10, pady=5)

        self.page_label = tk.Label(
            self.pagination_frame, text="Trang 1 / 1",
            font=('Arial', 12, 'bold'), bg='#2c3e50', fg='white'
        )
        self.page_label.pack(side='left', expand=True)

        self.next_button = tk.Button(
            self.pagination_frame, text="Trang sau ▶",
            font=('Arial', 12, 'bold'),
            command=self.next_page,
            bg="#34495e", fg="white", activebackground="#2ecc71", relief="flat"
        )
        self.next_button.pack(side='right', padx=10, pady=5)


        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # initial draw
        self.update_computers_display()

    def update_computers_display(self):
        """
        Xây lại grid hiển thị clients theo trang hiện tại.
        Lưu ý: self.client_frames được reset để chỉ giữ các widget visible.
        """

        with self.lock:
            if not self.needs_full_refresh:
                return
            self.needs_full_refresh = False
            all_clients = list(self.connected_clients.items())

            total = len(all_clients)
            self.total_pages = max(1, (total + self.clients_per_page - 1) // self.clients_per_page)
            # ensure current page in range
            self.current_page = max(1, min(self.current_page, self.total_pages))

            start_index = (self.current_page - 1) * self.clients_per_page
            end_index = start_index + self.clients_per_page
            clients = all_clients[start_index:end_index]

        # Clear previous frames completely and reset client_frames map
        for widget in self.computers_frame.winfo_children():
            try:
                widget.destroy()
            except:
                pass
        self.client_frames = {}

        if not clients:
            tk.Label(
                self.computers_frame,
                text="Đang chờ máy tính kết nối...",
                font=('Arial', 18),
                bg='#1e272e', fg='white'
            ).pack(expand=True, fill='both')
        else:
            max_columns = 4
            row, col = 0, 0

            for i in range(max_columns):
                self.computers_frame.grid_columnconfigure(i, weight=1, uniform="col")

            frame_width = 300
            img_height = int(frame_width * 3 / 4)
            top_info_height = 30
            total_frame_height = top_info_height + img_height + 20

            # Rebuild frames and store references
            for cid, info in clients:
                frame = tk.Frame(
                    self.computers_frame,
                    bg='#ecf0f1',
                    relief='raised',
                    borderwidth=3,
                    width=frame_width,
                    height=total_frame_height
                )
                frame.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')
                frame.grid_propagate(False)

                frame.grid_rowconfigure(0, minsize=top_info_height)
                frame.grid_rowconfigure(1, weight=1)
                frame.grid_columnconfigure(0, weight=1)

                top_info = tk.Frame(frame, bg='#ecf0f1', height=top_info_height)
                top_info.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
                top_info.grid_propagate(False)

                name_text = f"{info['computer_name']} ({info['hostname']})"
                if info.get('blocked'):
                    name_text += ""

                name_label = tk.Label(top_info, text=name_text, font=('Arial', 12, 'bold'), bg='#ecf0f1', fg='#2c3e50')
                status_color = 'orange' if info.get('blocked') else ('green' if info['status']=='online' else 'red')
                status_text = '● BLOCKED' if info.get('blocked') else f"● {info['status'].upper()}"
                status_label = tk.Label(top_info, text=status_text, font=('Arial',10,'bold'), fg=status_color, bg='#ecf0f1')

                name_label.grid(row=0, column=0, sticky='w')
                status_label.grid(row=0, column=1, sticky='e')

                top_info.grid_columnconfigure(0, weight=1)
                top_info.grid_columnconfigure(1, weight=0)

                # Hàm dynamic font cho từng label
                def make_resize_label(label, status_label):
                    def resize_name_font(event):
                        status_width = status_label.winfo_reqwidth()
                        available_width = max(event.width - status_width - 10, 50)
                        base_size = 12
                        new_size = max(min(int(base_size * available_width / 200), base_size), 6)
                        label.config(font=('Arial', new_size, 'bold'))
                    return resize_name_font

                top_info.bind('<Configure>', make_resize_label(name_label, status_label))

                img_area = tk.Frame(frame, bg='black')
                img_area.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
                img_area.pack_propagate(False)

                # initial placeholder (có thể sẽ được thay bằng ảnh nếu có)
                if info.get('image_data'):
                    # tạo label sẽ được update bên dưới thông qua update_client_image
                    pass
                else:
                    tk.Label(img_area, text="Chưa có hình ảnh", bg='black', fg='white', font=('Arial', 10)).pack(expand=True)

                # bind click
                frame.bind("<Button-1>", lambda e, c=cid: self.on_client_click(c))
                # bind cho children: dùng after một chút để chắc children đã tồn tại
                def bind_children(f, c):
                    for child in f.winfo_children():
                        try:
                            child.bind("<Button-1>", lambda e, cc=c: self.on_client_click(cc))
                        except:
                            pass
                self.root.after(10, lambda f=frame, c=cid: bind_children(f, c))

                if cid == self.selected_client:
                    frame.config(relief='solid', borderwidth=5)

                # save frame ref cho client hiện đang visible
                self.client_frames[cid] = (frame, img_area)

                col +=1
                if col >= max_columns:
                    col = 0
                    row += 1

        # Cập nhật nhãn trang và trạng thái nút điều hướng
        self.page_label.config(text=f"Trang {self.current_page} / {self.total_pages}")
        self.prev_button.config(state='normal' if self.current_page > 1 else 'disabled')
        self.next_button.config(state='normal' if self.current_page < self.total_pages else 'disabled')

        # Sau khi build UI, cập nhật ảnh cho các client visible (nếu đã có image_data)
        # Lưu danh sách visible cids để gọi update_client_image
        visible_cids = list(self.client_frames.keys())
        for cid in visible_cids:
            # gọi trực tiếp (UI thread)
            self.update_client_image(cid)

    def process_image_queue(self):
        """Xử lý các ảnh vào queue và chỉ cập nhật những client có ảnh (UI thread)"""
        updated_cids = set()
        while True:
            try:
                cid, img_data = self.image_queue.get_nowait()
            except queue.Empty:
                break
            # cập nhật bộ dữ liệu (đã cập nhật trong handle_client, nhưng an toàn update thêm)
            with self.lock:
                if cid in self.connected_clients:
                    self.connected_clients[cid]['image_data'] = img_data
                    self.connected_clients[cid]['last_seen'] = time.time()
                    self.connected_clients[cid]['status'] = 'online'
                    updated_cids.add(cid)

        # cập nhật UI cho mỗi client đã nhận ảnh (chỉ phần image)
        for cid in updated_cids:
            self.update_client_image(cid)
            # nếu cửa sổ chi tiết đang mở cho client này, cập nhật luôn
            if self.is_detail_window_open(cid):
                self.update_detail_window(cid)

        # schedule tiếp tục
        self.root.after(100, self.process_image_queue)

    def update_client_image(self, cid):
        """Chỉ cập nhật image area cho 1 client (UI thread)"""
        # chỉ xử lý nếu client đang visible (có entry trong client_frames)
        if cid not in self.client_frames:
            return
        with self.lock:
            info = self.connected_clients.get(cid)
            if not info:
                return
            image_data = info.get('image_data')

        frame, img_area = self.client_frames[cid]
        # clear previous widgets (và release image reference)
        for w in img_area.winfo_children():
            # try xóa ref image nếu có
            if isinstance(w, tk.Label) and hasattr(w, 'image'):
                try:
                    del w.image
                except:
                    pass
            try:
                w.destroy()
            except:
                pass

        if image_data:
            try:
                img = Image.open(io.BytesIO(image_data))
                # resize theo vùng của frame (tỉ lệ 4:3)
                frame_width = 350
                img_height = int(frame_width * 3 / 4)
                img_resized = ImageOps.contain(img, (frame_width, img_height))
                photo = ImageTk.PhotoImage(img_resized)
                lbl = tk.Label(img_area, image=photo, bg='black')
                lbl.image = photo
                lbl.pack(expand=True, fill='both')
            except Exception as e:
                tk.Label(img_area, text="Lỗi ảnh", bg='black', fg='red').pack(expand=True)
                print(f"Lỗi hiển thị ảnh {cid}: {e}")
        else:
            tk.Label(img_area, text="Chưa có hình ảnh", bg='black', fg='white', font=('Arial', 12)).pack(expand=True)

    # =================== ACTIONS ===================
    def block_action(self):
        if not self.selected_client:
            messagebox.showinfo("Chọn máy", "Vui lòng chọn một máy để BLOCK/UNBLOCK (click vào ô máy).")
            return

        cid = self.selected_client
        with self.lock:
            client_info = self.connected_clients.get(cid)
        if not client_info:
            messagebox.showinfo("Lỗi", "Không tìm thấy máy đã chọn.")
            return

        sock = client_info.get('socket')
        if not sock:
            messagebox.showinfo("Lỗi", "Socket của máy không khả dụng.")
            return

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
            with self.lock:
                client_info['blocked'] = not currently_blocked

            verb = 'mở khóa' if currently_blocked else 'khóa'
            self.alert_label.config(
                text=f"⚠️ Đã {verb} {client_info['computer_name']}",
                bg="#e67e22"
            )
            self.root.after(5000, lambda: self.alert_label.config(text="", bg=self.root["bg"]))
            # update top info status label by full refresh (cheap)
            with self.lock:
                self.needs_full_refresh = True
            self.root.after(0, self.update_computers_display)
        except Exception as e:
            messagebox.showerror("Lỗi gửi lệnh", f"Không thể gửi lệnh {action}: {e}")

    def shutdown_action(self):
        if not self.selected_client:
            messagebox.showinfo("Chọn máy", "Vui lòng chọn một máy để SHUTDOWN (click vào ô máy).")
            return

        cid = self.selected_client
        with self.lock:
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
        # đánh dấu rebuild và thông báo
        with self.lock:
            self.needs_full_refresh = True
        self.update_computers_display()
        msg = f"⚠️ {name} đã ngắt kết nối!"
        print(msg)
        self.alert_label.config(text=msg, bg="#e74c3c")
        self.root.after(10000, lambda: self.alert_label.config(text="", bg=self.root["bg"]))

    def on_client_click(self, cid):
        with self.lock:
            if cid not in self.connected_clients:
                return
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
        info = self.connected_clients.get(cid)
        if not info:
            return
        win = tk.Toplevel(self.root)
        win.title(f"👁️ Giám sát: {info['computer_name']}")
        win.geometry("900x650")
        win.configure(bg="#1e272e")

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

        img_frame = tk.Frame(win, bg="black", relief="ridge", bd=3)
        img_frame.pack(expand=True, fill="both", padx=20, pady=20)

        img_label = tk.Label(img_frame, bg="black")
        img_label.pack(expand=True, fill="both")

        control_frame = tk.Frame(win, bg="#1e272e")
        control_frame.pack(pady=(0, 20))

        close_icon = "↩️"
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

        self.open_detail_windows[cid] = (win, img_label)
        win.protocol("WM_DELETE_WINDOW", lambda: self.on_detail_window_close(cid))

        # Hiển thị ảnh ban đầu (nếu có)
        self.update_detail_window(cid)

    def on_detail_window_close(self, cid):
        if cid in self.open_detail_windows:
            try:
                self.open_detail_windows[cid][0].destroy()
            except:
                pass
            del self.open_detail_windows[cid]

    def is_detail_window_open(self, cid):
        return cid in self.open_detail_windows and self.open_detail_windows[cid][0].winfo_exists()

    def update_detail_window(self, cid):
        if not self.is_detail_window_open(cid):
            return
        win, label = self.open_detail_windows[cid]
        with self.lock:
            info = self.connected_clients.get(cid)
            if not info or not info.get('image_data'):
                return
            image_data = info['image_data']

        try:
            img = Image.open(io.BytesIO(image_data))
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
                        try:
                            with open("session.json", "r") as f:
                                sid = json.load(f).get("session_id")
                        except:
                            sid = None
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
            try:
                self.server_socket.close()
            except:
                pass
        with self.lock:
            for client in list(self.connected_clients.values()):
                try:
                    if client.get("socket"):
                        client["socket"].close()
                except:
                    pass
            self.connected_clients.clear()
        self.root.destroy()

    # ========== PHÂN TRANG ==========
    def next_page(self):
        """Chuyển sang trang kế tiếp"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.needs_full_refresh = True
            self.update_computers_display()

    def prev_page(self):
        """Quay lại trang trước"""
        if self.current_page > 1:
            self.current_page -= 1
            self.needs_full_refresh = True
            self.update_computers_display()


if __name__ == "__main__":
    root = tk.Tk()
    app = ServerMonitorGUI(root)
    root.mainloop()
