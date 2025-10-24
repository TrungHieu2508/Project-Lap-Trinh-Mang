import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from PIL import Image, ImageTk
import io
import base64
import hashlib
from flask import Flask, request
from flask_socketio import SocketIO
import random

class ServerMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GIÁM SÁT MÁY TÍNH QUA MẠNG")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2c3e50')
        
        # Lưu trữ clients thực tế
        self.connected_clients = {}
        self.computer_counter = 1
        
        self.setup_flask_server()
        self.setup_ui()
        
    def setup_flask_server(self):
        """Thiết lập Flask server để nhận kết nối từ clients"""
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        @self.socketio.on("register")
        def handle_register(data):
            client_id = request.sid
            username = data.get('username', 'Unknown')
            hostname = data.get('hostname', 'Unknown')
            
            computer_name = f"MAY {self.computer_counter}"
            self.computer_counter += 1
            
            self.connected_clients[client_id] = {
                'computer_name': computer_name,
                'username': username,
                'hostname': hostname,
                'status': 'online',
                'last_update': time.strftime('%H:%M:%S'),
                'image_data': None
            }
            
            # Cập nhật UI
            self.root.after(0, self.update_computers_display)
            print(f"✅ Client kết nối: {username}@{hostname} -> {computer_name}")
        
        @self.socketio.on("image_encrypted")
        def handle_encrypted(payload):
            client_id = request.sid
            if client_id in self.connected_clients:
                try:
                    computer_name = self.connected_clients[client_id]['computer_name']
                    self.connected_clients[client_id]['last_update'] = time.strftime('%H:%M:%S')
                    
                    # Giải mã ảnh (đơn giản hóa)
                    enc_b64 = payload.get("enc_image_b64", "")
                    enc_bytes = base64.b64decode(enc_b64)
                    decrypted = self.decrypt_bytes(enc_bytes, "change_this_password")
                    
                    # Lưu ảnh
                    self.connected_clients[client_id]['image_data'] = decrypted
                    
                    # Cập nhật preview
                    self.root.after(0, lambda: self.update_computer_preview(computer_name, decrypted))
                    
                except Exception as e:
                    print(f"❌ Lỗi xử lý ảnh: {e}")
        
        @self.socketio.on("disconnect")
        def on_disconnect():
            client_id = request.sid
            if client_id in self.connected_clients:
                computer_name = self.connected_clients[client_id]['computer_name']
                self.connected_clients[client_id]['status'] = 'offline'
                self.root.after(0, self.update_computers_display)
                print(f"❌ Client ngắt kết nối: {computer_name}")
        
        # Chạy server trong thread riêng
        def run_server():
            self.socketio.run(self.app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
    
    def setup_ui(self):
        """Thiết lập giao diện giống hình"""
        # Header
        header_frame = tk.Frame(self.root, bg='#34495e', height=80)
        header_frame.pack(fill='x', padx=10, pady=10)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(header_frame, 
                             text="GIÁM SÁT MÁY TÍNH QUA MẠNG", 
                             font=('Arial', 20, 'bold'), 
                             bg='#34495e', 
                             fg='white')
        title_label.pack(pady=20)
        
        subtitle_label = tk.Label(header_frame,
                                text="Chọn máy cần giám sát — click để phòng to / mở giám sát",
                                font=('Arial', 12),
                                bg='#34495e',
                                fg='#bdc3c7')
        subtitle_label.pack()
        
        # Separator
        separator = tk.Frame(self.root, height=2, bg='#7f8c8d')
        separator.pack(fill='x', padx=20, pady=5)
        
        # Main content area
        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Left panel - Computer list
        left_frame = tk.Frame(main_frame, bg='#34495e', width=250)
        left_frame.pack(side='left', fill='y', padx=(0, 10))
        left_frame.pack_propagate(False)
        
        # Right panel - Preview grid
        right_frame = tk.Frame(main_frame, bg='#2c3e50')
        right_frame.pack(side='left', fill='both', expand=True)
        
        # Setup left panel
        self.setup_left_panel(left_frame)
        
        # Setup right panel
        self.setup_right_panel(right_frame)
        
        # Status bar
        self.setup_status_bar()
    
    def setup_left_panel(self, parent):
        """Thiết lập panel bên trái - Danh sách máy tính"""
        # Title
        title_label = tk.Label(parent, 
                             text="GIÁM SÁT", 
                             font=('Arial', 16, 'bold'), 
                             bg='#34495e', 
                             fg='white',
                             pady=10)
        title_label.pack(fill='x')
        
        # Computer list
        self.list_container = tk.Frame(parent, bg='#34495e')
        self.list_container.pack(fill='both', expand=True, padx=10)
        
        # Control buttons
        control_frame = tk.Frame(parent, bg='#34495e', pady=10)
        control_frame.pack(fill='x', side='bottom')
        
        block_btn = tk.Button(control_frame, 
                            text="BLOCK", 
                            font=('Arial', 12, 'bold'),
                            bg='#e74c3c',
                            fg='white',
                            width=10,
                            height=2,
                            command=self.block_computer)
        block_btn.pack(side='left', padx=5)
        
        add_btn = tk.Button(control_frame,
                          text="ADD",
                          font=('Arial', 12, 'bold'),
                          bg='#27ae60',
                          fg='white',
                          width=10,
                          height=2,
                          command=self.add_computer)
        add_btn.pack(side='left', padx=5)
        
        # Populate computer list
        self.update_computer_list()
    
    def setup_right_panel(self, parent):
        """Thiết lập panel bên phải - Grid preview"""
        # Title
        title_label = tk.Label(parent,
                             text="CHẾ ĐỘ XEM TRƯỚC",
                             font=('Arial', 16, 'bold'),
                             bg='#2c3e50',
                             fg='white',
                             pady=10)
        title_label.pack(fill='x')
        
        # Preview grid container
        self.preview_container = tk.Frame(parent, bg='#2c3e50')
        self.preview_container.pack(fill='both', expand=True)
        
        # Populate preview grid
        self.update_preview_grid()
    
    def setup_status_bar(self):
        """Thanh trạng thái"""
        status_frame = tk.Frame(self.root, bg='#34495e', height=30)
        status_frame.pack(fill='x', side='bottom')
        status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(status_frame,
                              text="📍 Server đang chạy tại: http://0.0.0.0:5000 | Đang chờ kết nối từ clients...",
                              font=('Arial', 10),
                              bg='#34495e',
                              fg='#bdc3c7')
        self.status_label.pack(pady=5)
    
    def update_computer_list(self):
        """Cập nhật danh sách máy tính"""
        for widget in self.list_container.winfo_children():
            widget.destroy()
        
        if not self.connected_clients:
            empty_label = tk.Label(self.list_container,
                                 text="📡 Đang chờ clients kết nối...",
                                 font=('Arial', 12),
                                 bg='#34495e',
                                 fg='#bdc3c7')
            empty_label.pack(pady=20)
            return
        
        row = 0
        for client_id, info in self.connected_clients.items():
            if info['status'] == 'online':
                color = '#27ae60'  # Green
                status_text = "● Online"
            else:
                color = '#e74c3c'  # Red
                status_text = "● Offline"
            
            computer_frame = tk.Frame(self.list_container, bg='#2c3e50', relief='raised', bd=1)
            computer_frame.pack(fill='x', pady=2, padx=5)
            
            # Number label
            number_label = tk.Label(computer_frame,
                                  text=str(row + 1),
                                  font=('Arial', 12, 'bold'),
                                  bg='#3498db',
                                  fg='white',
                                  width=3,
                                  height=1)
            number_label.pack(side='left', padx=5, pady=5)
            
            # Computer info
            info_frame = tk.Frame(computer_frame, bg='#2c3e50')
            info_frame.pack(side='left', fill='x', expand=True, padx=5)
            
            name_label = tk.Label(info_frame,
                                text=info['computer_name'],
                                font=('Arial', 11, 'bold'),
                                bg='#2c3e50',
                                fg='white',
                                anchor='w')
            name_label.pack(fill='x')
            
            status_label = tk.Label(info_frame,
                                  text=status_text,
                                  font=('Arial', 9),
                                  bg='#2c3e50',
                                  fg=color,
                                  anchor='w')
            status_label.pack(fill='x')
            
            user_label = tk.Label(info_frame,
                                text=f"User: {info['username']}",
                                font=('Arial', 9),
                                bg='#2c3e50',
                                fg='#bdc3c7',
                                anchor='w')
            user_label.pack(fill='x')
            
            # Click binding
            computer_frame.bind("<Button-1>", lambda e, cid=client_id: self.show_computer_details(cid))
            for child in computer_frame.winfo_children():
                child.bind("<Button-1>", lambda e, cid=client_id: self.show_computer_details(cid))
            
            row += 1
    
    def update_preview_grid(self):
        """Cập nhật grid preview"""
        for widget in self.preview_container.winfo_children():
            widget.destroy()
        
        if not self.connected_clients:
            empty_label = tk.Label(self.preview_container,
                                 text="Chưa có máy tính nào kết nối\n\nCác máy tính sẽ xuất hiện ở đây khi kết nối",
                                 font=('Arial', 14),
                                 bg='#2c3e50',
                                 fg='#7f8c8d',
                                 justify='center')
            empty_label.pack(expand=True)
            return
        
        # Tạo grid 2x3
        clients_list = list(self.connected_clients.items())
        
        for i in range(2):  # rows
            row_frame = tk.Frame(self.preview_container, bg='#2c3e50')
            row_frame.pack(fill='x', pady=5)
            
            for j in range(3):  # columns
                if i * 3 + j < len(clients_list):
                    client_id, info = clients_list[i * 3 + j]
                    self.create_preview_card(row_frame, client_id, info, j)
    
    def create_preview_card(self, parent, client_id, info, column):
        """Tạo card preview cho máy tính"""
        card_frame = tk.Frame(parent, bg='#34495e', relief='raised', bd=2, width=200, height=180)
        card_frame.pack(side='left', padx=10, pady=5)
        card_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(card_frame,
                             text=f"{info['computer_name']} PREVIEW",
                             font=('Arial', 10, 'bold'),
                             bg='#34495e',
                             fg='white',
                             pady=5)
        title_label.pack(fill='x')
        
        # Preview image area
        preview_frame = tk.Frame(card_frame, bg='#2c3e50', height=100)
        preview_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Tạo ảnh preview
        if info['image_data']:
            try:
                # Hiển thị ảnh thực từ client
                image = Image.open(io.BytesIO(info['image_data']))
                image.thumbnail((180, 80), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                
                preview_label = tk.Label(preview_frame, image=photo, bg='#2c3e50')
                preview_label.image = photo
                preview_label.pack(expand=True)
            except:
                # Fallback nếu lỗi ảnh
                preview_label = tk.Label(preview_frame,
                                       text="🖥️\nLive Preview",
                                       font=('Arial', 12),
                                       bg='#2c3e50',
                                       fg='#7f8c8d',
                                       justify='center')
                preview_label.pack(expand=True)
        else:
            preview_label = tk.Label(preview_frame,
                                   text="🖥️\nĐang chờ\ndữ liệu...",
                                   font=('Arial', 12),
                                   bg='#2c3e50',
                                   fg='#7f8c8d',
                                   justify='center')
            preview_label.pack(expand=True)
        
        # Computer info
        info_frame = tk.Frame(card_frame, bg='#34495e')
        info_frame.pack(fill='x', padx=5, pady=5)
        
        name_label = tk.Label(info_frame,
                            text=info['computer_name'],
                            font=('Arial', 9, 'bold'),
                            bg='#34495e',
                            fg='white')
        name_label.pack(side='left')
        
        # Zoom button
        zoom_btn = tk.Button(info_frame,
                           text="Phòng to",
                           font=('Arial', 8),
                           bg='#3498db',
                           fg='white',
                           command=lambda cid=client_id: self.zoom_computer(cid))
        zoom_btn.pack(side='right')
        
        # Click binding
        card_frame.bind("<Button-1>", lambda e, cid=client_id: self.zoom_computer(cid))
        preview_label.bind("<Button-1>", lambda e, cid=client_id: self.zoom_computer(cid))
    
    def update_computers_display(self):
        """Cập nhật toàn bộ hiển thị"""
        self.update_computer_list()
        self.update_preview_grid()
        
        # Cập nhật status
        client_count = len([c for c in self.connected_clients.values() if c['status'] == 'online'])
        self.status_label.config(
            text=f"📍 Server đang chạy tại: http://0.0.0.0:5000 | {client_count} máy tính đang kết nối"
        )
    
    def update_computer_preview(self, computer_name, image_data):
        """Cập nhật preview cho máy tính cụ thể"""
        self.update_computers_display()
    
    def show_computer_details(self, client_id):
        """Hiển thị chi tiết máy tính được chọn"""
        if client_id in self.connected_clients:
            info = self.connected_clients[client_id]
            messagebox.showinfo(
                f"Thông tin {info['computer_name']}",
                f"Tên: {info['computer_name']}\n"
                f"Trạng thái: {info['status']}\n"
                f"Username: {info['username']}\n"
                f"Hostname: {info['hostname']}\n"
                f"Cập nhật lần cuối: {info['last_update']}"
            )
    
    def zoom_computer(self, client_id):
        """Phóng to màn hình máy tính"""
        if client_id in self.connected_clients:
            info = self.connected_clients[client_id]
            
            # Tạo cửa sổ phóng to
            zoom_window = tk.Toplevel(self.root)
            zoom_window.title(f"Giám sát: {info['computer_name']}")
            zoom_window.geometry("800x600")
            zoom_window.configure(bg='#2c3e50')
            
            # Title
            title_label = tk.Label(zoom_window,
                                 text=f"ĐANG GIÁM SÁT: {info['computer_name']}",
                                 font=('Arial', 16, 'bold'),
                                 bg='#2c3e50',
                                 fg='white',
                                 pady=10)
            title_label.pack()
            
            # Info
            info_label = tk.Label(zoom_window,
                                text=f"User: {info['username']} | Hostname: {info['hostname']}",
                                font=('Arial', 12),
                                bg='#2c3e50',
                                fg='#bdc3c7')
            info_label.pack()
            
            # Preview area
            preview_label = tk.Label(zoom_window,
                                   text="🖥️\nCHẾ ĐỘ GIÁM SÁT TOÀN MÀN HÌNH\n\n"
                                       f"Đang hiển thị màn hình từ: {info['computer_name']}\n"
                                       f"Username: {info['username']}\n"
                                       f"Cập nhật: {info['last_update']}",
                                   font=('Arial', 14),
                                   bg='black',
                                   fg='white',
                                   justify='center')
            preview_label.pack(fill='both', expand=True, padx=20, pady=20)
            
            # Nếu có ảnh, hiển thị ảnh lớn
            if info['image_data']:
                try:
                    image = Image.open(io.BytesIO(info['image_data']))
                    image.thumbnail((600, 400), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    
                    img_label = tk.Label(zoom_window, image=photo, bg='black')
                    img_label.image = photo
                    img_label.pack(pady=10)
                except Exception as e:
                    print(f"Lỗi hiển thị ảnh lớn: {e}")
    
    def block_computer(self):
        """Chức năng block máy tính"""
        messagebox.showwarning("BLOCK", "Tính năng đang được phát triển...")
    
    def add_computer(self):
        """Thêm máy tính mới"""
        messagebox.showinfo("ADD", "Tính năng thêm máy tính mới đang được phát triển...")
    
    def decrypt_bytes(self, payload: bytes, password: str) -> bytes:
        """Giải mã dữ liệu"""
        if payload.startswith(b"XORv1"):
            data = payload[5:]
            key = hashlib.sha256(password.encode()).digest()
            out = bytearray(data)
            for i in range(len(out)):
                out[i] ^= key[i % len(key)]
            return bytes(out)
        else:
            return payload

if __name__ == "__main__":
    root = tk.Tk()
    app = ServerMonitorGUI(root)
    root.mainloop()