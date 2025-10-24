import base64, io, json, threading, time, hashlib, os
from flask import Flask
from flask_socketio import SocketIO
from PIL import Image, ImageTk
from tkinter import Tk, Label, Frame, Canvas, Scrollbar, BOTH, RIGHT, LEFT, Y, NW
from datetime import datetime

# ============================================================
# Flask Server khởi tạo
# ============================================================
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

frames = {}
gui_instance=None  # { client_id: {username, hostname, timestamp, image_b64, scheme} }
stopped_clients = set()


# ============================================================
# Giải mã dữ liệu nhận từ client
# ============================================================
try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False

PASSWORD = "change_this_password"

def derive_fernet_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
        backend=default_backend(),
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def decrypt_bytes(data: bytes, password: str):
    if data.startswith(b"XORv1"):
        key = hashlib.sha256(password.encode()).digest()
        enc = bytearray(data[5:])
        for i in range(len(enc)):
            enc[i] ^= key[i % len(key)]
        return bytes(enc)
    else:
        salt = data[:16]
        token = data[16:]
        key = derive_fernet_key(password, salt)
        f = Fernet(key)
        return f.decrypt(token)

# ============================================================
# Nhận dữ liệu từ client
# ============================================================
@socketio.on("register")
def on_register(data):
    print(f"📡 Client đăng ký: {data}")

@socketio.on("image_encrypted")
def on_image(data):
    global gui_instance, stopped_clients
    try:
        client_id = f"{data['meta']['username']}@{data['meta']['hostname']}"

        # ⚠️ Nếu client này đã bị dừng => bỏ qua dữ liệu
        if client_id in stopped_clients:
            return

        if gui_instance and not gui_instance.monitoring_enabled:
            return

        enc_b64 = data["enc_image_b64"]
        enc_bytes = base64.b64decode(enc_b64)
        img_bytes = decrypt_bytes(enc_bytes, PASSWORD)

        frames[client_id] = {
            "username": data['meta']['username'],
            "hostname": data['meta']['hostname'],
            "timestamp": data["timestamp"],
            "image_bytes": img_bytes,
            "scheme": data["enc_scheme"],
        }

    except Exception as e:
        print("❌ Lỗi giải mã:", e)


# ============================================================
# Flask chạy nền
# ============================================================
def run_flask():
    socketio.run(app, host="0.0.0.0", port=5000)

# ============================================================
# GUI hiển thị live feed nhiều client + nút điều khiển
# ============================================================
class MonitorGUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("🖥️ Live Monitor - Multi Client")
        self.root.geometry("1000x700")

        # ====== Cờ điều khiển ======
        self.display_paused = False
        self.monitoring_enabled = True

        # ====== Thanh nút điều khiển ======
        control_frame = Frame(self.root, pady=5)
        control_frame.pack()

        self.pause_btn = Label(control_frame, text="⏸️ Tạm dừng hiển thị", bg="#ffcc00", width=20, cursor="hand2")
        self.pause_btn.pack(side=LEFT, padx=10)
        self.pause_btn.bind("<Button-1>", self.toggle_display)

        self.stop_btn = Label(control_frame, text="🛑 Dừng giám sát", bg="#ff4444", fg="white", width=20, cursor="hand2")
        self.stop_btn.pack(side=LEFT, padx=10)
        self.stop_btn.bind("<Button-1>", self.stop_monitoring)

        # ====== Khung cuộn chứa hình ảnh ======
        self.canvas = Canvas(self.root)
        self.scrollbar = Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = Frame(self.canvas)
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor=NW)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.scrollbar.pack(side=RIGHT, fill=Y)

        self.client_labels = {}

        # ====== Chạy Flask ở luồng riêng ======
        threading.Thread(target=run_flask, daemon=True).start()
        self.update_gui()
        self.root.mainloop()

    # --------------------------
    def toggle_display(self, event=None):
        self.display_paused = not self.display_paused
        if self.display_paused:
            self.pause_btn.config(text="▶️ Tiếp tục hiển thị", bg="#00cc66")
        else:
            self.pause_btn.config(text="⏸️ Tạm dừng hiển thị", bg="#ffcc00")

    # --------------------------
    def stop_monitoring(self, event=None):
        self.monitoring_enabled = False
        frames.clear()
        for cid, items in self.client_labels.items():
            items["img"].config(image="", text="")
            items["time"].config(text="⛔ Giám sát đã dừng")
        self.stop_btn.config(text="✅ Đã dừng giám sát", bg="#777777")
        print("🛑 Giám sát đã bị dừng — không nhận thêm dữ liệu từ client.")

    def stop_single_client(self, client_id):
        stopped_clients.add(client_id)
        if client_id in self.client_labels:
            lbls = self.client_labels[client_id]
            lbls["img"].config(image="", text="")
            lbls["time"].config(text=f"⛔ {client_id} đã bị dừng")
            lbls["stop_btn"].config(text="✅ Đã dừng", bg="#777777")
        print(f"🛑 Đã dừng giám sát thiết bị: {client_id}")

    # --------------------------
    def update_gui(self):
        if not self.display_paused and self.monitoring_enabled:
            for cid, data in frames.items():
                if cid not in self.client_labels:
                    frame = Frame(self.scroll_frame, relief="groove", borderwidth=2, padx=10, pady=10)
                    frame.pack(padx=10, pady=10, fill="x")
                    title = Label(frame, text=cid, font=("Arial", 14, "bold"))
                    title.pack()
                    img_label = Label(frame)
                    img_label.pack()
                    time_label = Label(frame, font=("Arial", 10))
                    time_label.pack()
                    self.client_labels[cid] = {"frame": frame, "img": img_label, "time": time_label}
                    # 🛑 Nút dừng riêng thiết bị này
                    stop_one_btn = Label(frame, text="🛑 Dừng thiết bị này", bg="#ff6666", fg="white", width=20, cursor="hand2")
                    stop_one_btn.pack(pady=5)
                    stop_one_btn.bind("<Button-1>", lambda e, c=cid: self.stop_single_client(c))
                    self.client_labels[cid]["stop_btn"] = stop_one_btn


                try:
                    image = Image.open(io.BytesIO(data["image_bytes"]))
                    image = image.resize((800, int(800 * image.height / image.width)))
                    photo = ImageTk.PhotoImage(image)
                    self.client_labels[cid]["img"].config(image=photo)
                    self.client_labels[cid]["img"].image = photo
                    timestamp = datetime.fromtimestamp(data["timestamp"]).strftime("%H:%M:%S")
                    self.client_labels[cid]["time"].config(text=f"Cập nhật: {timestamp}")
                except Exception as e:
                    print("Lỗi hiển thị:", e)

        self.root.after(500, self.update_gui)

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("🚀 ServerApp GUI đang khởi động trên cổng 5000...")
    gui_instance = MonitorGUI()

