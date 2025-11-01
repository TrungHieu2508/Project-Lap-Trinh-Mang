# server.py
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
import socket
import json
import os

class ServerMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GIÁM SÁT MÁY TÍNH QUA MẠNG")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2c3e50')
        
        self.connected_clients = {}
        self.computer_counter = 1
        
        self.setup_flask_server()
        self.start_discovery_server()
        self.setup_ui()
        
    def setup_flask_server(self):
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
            
            self.root.after(0, self.update_computers_display)
            print(f"Client kết nối: {username}@{hostname} -> {computer_name}")
        
        @self.socketio.on("image_encrypted")
        def handle_encrypted(payload):
            client_id = request.sid
            if client_id in self.connected_clients:
                try:
                    self.connected_clients[client_id]['last_update'] = time.strftime('%H:%M:%S')
                    enc_b64 = payload.get("enc_image_b64", "")
                    enc_bytes = base64.b64decode(enc_b64)
                    decrypted = self.decrypt_bytes(enc_bytes, "change_this_password")
                    self.connected_clients[client_id]['image_data'] = decrypted
                    self.root.after(0, lambda: self.update_computer_preview(
                        self.connected_clients[client_id]['computer_name'], decrypted))
                except Exception as e:
                    print(f"Lỗi xử lý ảnh: {e}")
        
        @self.socketio.on("disconnect")
        def on_disconnect():
            client_id = request.sid
            if client_id in self.connected_clients:
                computer_name = self.connected_clients[client_id]['computer_name']
                self.connected_clients[client_id]['status'] = 'offline'
                self.root.after(0, self.update_computers_display)
                print(f"Client ngắt kết nối: {computer_name}")
        
        def run_server():
            self.socketio.run(self.app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
    
    def start_discovery_server(self):
        def run():
            DISCOVERY_PORT = 5001
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(('', DISCOVERY_PORT))
            
            try:
                with open("session.json", "r") as f:
                    server_session_id = json.load(f).get("session_id", "")
            except:
                print("session.json không tồn tại. Discovery bị tắt.")
                return
            
            print(f"Discovery server chạy trên UDP port {DISCOVERY_PORT}")
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = data.decode('utf-8')
                    if msg.startswith("DISCOVER_SERVER ") and msg.split(" ", 1)[1] == server_session_id:
                        reply = "SERVER_HERE 5000"
                        sock.sendto(reply.encode('utf-8'), addr)
                        print(f"Phát hiện từ {addr[0]}, đã trả lời.")
                except Exception as e:
                    if "socket" not in str(e):
                        print(f"Discovery error: {e}")
        
        threading.Thread(target=run, daemon=True).start()
    
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg='#34495e', height=80)
        header_frame.pack(fill='x', padx=10, pady=10)
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="GIÁM SÁT MÁY TÍNH QUA MẠNG", 
                 font=('Arial', 20, 'bold'), bg='#34495e', fg='white').pack(pady=20)
        tk.Label(header_frame, text="Chọn máy cần giám sát — click để phòng to / mở giám sát",
                 font=('Arial', 12), bg='#34495e', fg='#bdc3c7').pack()
        
        tk.Frame(self.root, height=2, bg='#7f8c8d').pack(fill='x', padx=20, pady=5)
        
        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        left_frame = tk.Frame(main_frame, bg='#34495e', width=250)
        left_frame.pack(side='left', fill='y', padx=(0, 10))
        left_frame.pack_propagate(False)
        
        right_frame = tk.Frame(main_frame, bg='#2c3e50')
        right_frame.pack(side='left', fill='both', expand=True)
        
        self.setup_left_panel(left_frame)
        self.setup_right_panel(right_frame)
        self.setup_status_bar()
    
    def setup_left_panel(self, parent):
        tk.Label(parent, text="GIÁM SÁT", font=('Arial', 16, 'bold'), 
                 bg='#34495e', fg='white', pady=10).pack(fill='x')
        self.list_container = tk.Frame(parent, bg='#34495e')
        self.list_container.pack(fill='both', expand=True, padx=10)
        
        control_frame = tk.Frame(parent, bg='#34495e', pady=10)
        control_frame.pack(fill='x', side='bottom')
        
        tk.Button(control_frame, text="BLOCK", font=('Arial', 12, 'bold'),
                  bg='#e74c3c', fg='white', width=10, height=2,
                  command=self.block_computer).pack(side='left', padx=5)
        tk.Button(control_frame, text="ADD", font=('Arial', 12, 'bold'),
                  bg='#27ae60', fg='white', width=10, height=2,
                  command=self.add_computer).pack(side='left', padx=5)
        
        self.update_computer_list()
    
    def setup_right_panel(self, parent):
        tk.Label(parent, text="CHẾ ĐỘ XEM TRƯỚC", font=('Arial', 16, 'bold'),
                 bg='#2c3e50', fg='white', pady=10).pack(fill='x')
        self.preview_container = tk.Frame(parent, bg='#2c3e50')
        self.preview_container.pack(fill='both', expand=True)
        self.update_preview_grid()
    
    def setup_status_bar(self):
        status_frame = tk.Frame(self.root, bg='#34495e', height=30)
        status_frame.pack(fill='x', side='bottom')
        status_frame.pack_propagate(False)
        self.status_label = tk.Label(status_frame,
                              text="Server đang chạy tại: http://0.0.0.0:5000 | Đang chờ kết nối...",
                              font=('Arial', 10), bg='#34495e', fg='#bdc3c7')
        self.status_label.pack(pady=5)
    
    def update_computer_list(self):
        for widget in self.list_container.winfo_children():
            widget.destroy()
        if not self.connected_clients:
            tk.Label(self.list_container, text="Đang chờ clients kết nối...",
                     font=('Arial', 12), bg='#34495e', fg='#bdc3c7').pack(pady=20)
            return
        for i, (cid, info) in enumerate(self.connected_clients.items()):
            if info['status'] != 'online': continue
            frame = tk.Frame(self.list_container, bg='#2c3e50', relief='raised', bd=1)
            frame.pack(fill='x', pady=2, padx=5)
            tk.Label(frame, text=str(i+1), font=('Arial', 12, 'bold'),
                     bg='#3498db', fg='white', width=3).pack(side='left')
            info_f = tk.Frame(frame, bg='#2c3e50')
            info_f.pack(side='left', fill='x', expand=True, padx=10)
            tk.Label(info_f, text=info['computer_name'], font=('Arial', 12, 'bold'),
                     bg='#2c3e50', fg='white', anchor='w').pack(fill='x')
            tk.Label(info_f, text="Online", font=('Arial', 9),
                     bg='#2c3e50', fg='#27ae60', anchor='w').pack(fill='x')
            tk.Label(info_f, text=f"User: {info['username']}", font=('Arial', 9),
                     bg='#2c3e50', fg='#bdc3c7', anchor='w').pack(fill='x')
            frame.bind("<Button-1>", lambda e, c=cid: self.show_computer_details(c))
            for child in frame.winfo_children():
                child.bind("<Button-1>", lambda e, c=cid: self.show_computer_details(c))
    
    def update_preview_grid(self):
        for widget in self.preview_container.winfo_children():
            widget.destroy()
        if not self.connected_clients:
            tk.Label(self.preview_container,
                     text="Chưa có máy tính nào kết nối\n\nCác máy tính sẽ xuất hiện ở đây khi kết nối",
                     font=('Arial', 14), bg='#2c3e50', fg='#7f8c8d', justify='center').pack(expand=True)
            return
        clients = list(self.connected_clients.items())
        for i in range(2):
            row = tk.Frame(self.preview_container, bg='#2c3e50')
            row.pack(fill='x', pady=5)
            for j in range(3):
                idx = i*3 + j
                if idx >= len(clients): break
                cid, info = clients[idx]
                self.create_preview_card(row, cid, info)
    
    def create_preview_card(self, parent, client_id, info):
        card = tk.Frame(parent, bg='#34495e', relief='raised', bd=2, width=200, height=180)
        card.pack(side='left', padx=10, pady=5)
        card.pack_propagate(False)
        tk.Label(card, text=f"{info['computer_name']} PREVIEW",
                 font=('Arial', 10, 'bold'), bg='#34495e', fg='white', pady=5).pack(fill='x')
        img_frame = tk.Frame(card, bg='#2c3e50', height=100)
        img_frame.pack(fill='both', expand=True, padx=5, pady=5)
        if info['image_data']:
            try:
                img = Image.open(io.BytesIO(info['image_data']))
                img.thumbnail((180, 80), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(img_frame, image=photo, bg='#2c3e50')
                lbl.image = photo
                lbl.pack(expand=True)
            except:
                tk.Label(img_frame, text="Live Preview", font=('Arial', 12),
                         bg='#2c3e50', fg='#7f8c8d', justify='center').pack(expand=True)
        else:
            tk.Label(img_frame, text="Đang chờ\ndữ liệu...", font=('Arial', 12),
                     bg='#2c3e50', fg='#7f8c8d', justify='center').pack(expand=True)
        info_f = tk.Frame(card, bg='#34495e')
        info_f.pack(fill='x', padx=5, pady=5)
        tk.Label(info_f, text=info['computer_name'], font=('Arial', 9, 'bold'),
                 bg='#34495e', fg='white').pack(side='left')
        tk.Button(info_f, text="Phòng to", font=('Arial', 8), bg='#3498db', fg='white',
                  command=lambda: self.zoom_computer(client_id)).pack(side='right')
        card.bind("<Button-1>", lambda e: self.zoom_computer(client_id))
    
    def update_computers_display(self):
        self.update_computer_list()
        self.update_preview_grid()
        online = sum(1 for c in self.connected_clients.values() if c['status'] == 'online')
        self.status_label.config(text=f"Server đang chạy tại: http://0.0.0.0:5000 | {online} máy tính đang kết nối")
    
    def update_computer_preview(self, name, data): self.update_computers_display()
    def show_computer_details(self, cid): 
        info = self.connected_clients[cid]
        messagebox.showinfo(f"Thông tin {info['computer_name']}",
                            f"Tên: {info['computer_name']}\nTrạng thái: {info['status']}\n"
                            f"Username: {info['username']}\nHostname: {info['hostname']}\n"
                            f"Cập nhật: {info['last_update']}")
    def zoom_computer(self, cid):
        info = self.connected_clients[cid]
        win = tk.Toplevel(self.root)
        win.title(f"Giám sát: {info['computer_name']}")
        win.geometry("800x600")
        win.configure(bg='#2c3e50')
        tk.Label(win, text=f"ĐANG GIÁM SÁT: {info['computer_name']}",
                 font=('Arial', 16, 'bold'), bg='#2c3e50', fg='white', pady=10).pack()
        tk.Label(win, text=f"User: {info['username']} | Host: {info['hostname']}",
                 font=('Arial', 12), bg='#2c3e50', fg='#bdc3c7').pack()
        if info['image_data']:
            try:
                img = Image.open(io.BytesIO(info['image_data']))
                img.thumbnail((600, 400), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                tk.Label(win, image=photo, bg='black').pack(pady=10)
                tk.Label(win).image = photo
            except: pass
    def block_computer(self): messagebox.showwarning("BLOCK", "Tính năng đang phát triển...")
    def add_computer(self): messagebox.showinfo("ADD", "Tính năng đang phát triển...")
    def decrypt_bytes(self, payload: bytes, password: str) -> bytes:
        if payload.startswith(b"XORv1"):
            data = payload[5:]
            key = hashlib.sha256(password.encode()).digest()
            out = bytearray(data)
            for i in range(len(out)): out[i] ^= key[i % len(key)]
            return bytes(out)
        return payload

if __name__ == "__main__":
    root = tk.Tk()
    app = ServerMonitorGUI(root)
    root.mainloop()