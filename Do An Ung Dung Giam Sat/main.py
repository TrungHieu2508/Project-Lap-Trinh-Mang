import tkinter as tk
from tkinter import messagebox
import subprocess
import secrets
import json
import os
import sys

# ======= CẤU HÌNH MẶT ĐỊNH =======
TEACHER_USERNAME = "ITadmin"
TEACHER_PASSWORD = "ithcm123"
SESSION_FILE = "session.json"


class AppLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("GIÁM SÁT MÁY TÍNH QUA MẠNG (TCP/UCP)")
        self.root.geometry("800x700")
        self.root.configure(bg="#1e272e")
        self.session_id = None

        # Cho phép phóng to/thu nhỏ
        self.root.resizable(True, True)
        self.create_intro_screen()

    # =================== GIAO DIỆN GIỚI THIỆU ===================
    def create_intro_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        # ==== HEADER ====
        header = tk.Frame(self.root, bg="#273c75")
        header.pack(fill="x")

        tk.Label(
            header,
            text="💻 ỨNG DỤNG GIÁM SÁT PHÒNG MÁY",
            font=("Arial", 22, "bold"),
            bg="#273c75",
            fg="white",
            pady=15
        ).pack(side="left", padx=25)

        # ==== NỘI DUNG CHÍNH ====
        intro_frame = tk.Frame(self.root, bg="#1e272e")
        intro_frame.pack(fill="both", expand=True)

        # Giới thiệu trung tâm
        tk.Label(
            intro_frame,
            text="👋 Chào mừng bạn đến với hệ thống giám sát máy tính!",
            font=("Arial", 18, "bold"),
            fg="#f1c40f",
            bg="#1e272e"
        ).pack(pady=(60, 20))

        intro_text = (
            "Hệ thống giúp quản lý và giám sát các máy tính trong phòng máy một cách hiệu quả.\n\n"
            "Ứng dụng chia thành hai vai trò chính:"
        )

        tk.Label(
            intro_frame,
            text=intro_text,
            font=("Arial", 13),
            fg="white",
            bg="#1e272e",
            justify="center"
        ).pack(pady=(10, 40))

        # Khung trái hiển thị 2 vai trò
        role_frame = tk.Frame(intro_frame, bg="#1e272e")
        role_frame.pack(anchor="w", padx=80)

        # Quản trị viên
        tk.Label(
            role_frame,
            text="👨‍🏫  Quản trị viên:",
            font=("Arial", 16, "bold"),
            bg="#1e272e",
            fg="#00a8ff"
        ).pack(anchor="w", pady=(0, 5))

        tk.Label(
            role_frame,
            text="• Giám sát và quản lý toàn bộ máy tính trong phòng.",
            font=("Arial", 13),
            bg="#1e272e",
            fg="#dcdde1"
        ).pack(anchor="w", padx=25)

        tk.Label(
            role_frame,
            text="• Khởi tạo mã lớp và kết nối các máy trạm.",
            font=("Arial", 13),
            bg="#1e272e",
            fg="#dcdde1"
        ).pack(anchor="w", padx=25, pady=(0, 20))

        # Người dùng
        tk.Label(
            role_frame,
            text="👨‍🎓  Người dùng:",
            font=("Arial", 16, "bold"),
            bg="#1e272e",
            fg="#9b59b6"
        ).pack(anchor="w", pady=(10, 5))

        tk.Label(
            role_frame,
            text="• Nhập mã code được cung cấp để tham gia.",
            font=("Arial", 13),
            bg="#1e272e",
            fg="#dcdde1"
        ).pack(anchor="w", padx=25)

        tk.Label(
            role_frame,
            text="• Cho phép hệ thống hiển thị và giám sát hoạt động thiết bị.",
            font=("Arial", 13),
            bg="#1e272e",
            fg="#dcdde1"
        ).pack(anchor="w", padx=25)

        # Nút chuyển màn hình (đặt giữa)
        next_btn = tk.Button(
            intro_frame,
            text="👉 TIẾP TỤC",
            font=("Arial", 14, "bold"),
            bg="#44bd32",
            fg="white",
            width=15,
            height=2,
            relief="flat",
            command=self.create_main_screen
        )
        next_btn.pack(pady=(60, 30))
        next_btn.bind("<Enter>", lambda e: next_btn.config(bg="#27ae60"))
        next_btn.bind("<Leave>", lambda e: next_btn.config(bg="#44bd32"))

    # =================== MÀN HÌNH NHẬP MÃ CODE ===================
    def create_main_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        # ==== HEADER ====
        header = tk.Frame(self.root, bg="#273c75")
        header.pack(fill="x")

        tk.Label(
            header,
            text="👤 NGƯỜI DÙNG",
            font=("Arial", 22, "bold"),
            bg="#273c75",
            fg="#f5f6fa",
            pady=15
        ).pack(side="left", padx=25)

        admin_btn = tk.Button(
            header,
            text="👨‍🏫 Đăng nhập Quản trị viên",
            font=("Arial", 12, "bold"),
            bg="#00a8ff",
            fg="white",
            relief="flat",
            padx=10, pady=5,
            command=self.open_teacher_login
        )
        admin_btn.pack(side="right", padx=25, pady=10)
        admin_btn.bind("<Enter>", lambda e: admin_btn.config(bg="#0097e6"))
        admin_btn.bind("<Leave>", lambda e: admin_btn.config(bg="#00a8ff"))

        # ==== KHUNG NỀN ====
        main_frame = tk.Frame(self.root, bg="#1e272e")
        main_frame.pack(fill="both", expand=True)

        # ==== CARD TRUNG TÂM ====
        card = tk.Frame(
            main_frame,
            bg="#273c75",
            highlightbackground="#40739e",
            highlightthickness=2,
            bd=0
        )
        card.place(relx=0.5, rely=0.5, anchor="center", width=420, height=360)

        tk.Label(
            card,
            text="🔑 NHẬP MÃ CODE",
            font=("Arial", 18, "bold"),
            bg="#273c75",
            fg="#fbc531"
        ).pack(pady=(25, 10))

        tk.Label(
            card,
            text="Vui lòng nhập mã code được quản trị viên cung cấp",
            font=("Arial", 11),
            bg="#273c75",
            fg="#dcdde1"
        ).pack(pady=(0, 20))

        self.code_entry = tk.Entry(
            card,
            font=("Arial", 18, "bold"),
            width=12,
            justify="center",
            relief="flat",
            bg="#dcdde1",
            fg="#2f3640"
        )
        self.code_entry.pack(pady=10, ipady=8)

        connect_btn = tk.Button(
            card,
            text="🚀 KẾT NỐI",
            font=("Arial", 14, "bold"),
            bg="#44bd32",
            fg="white",
            width=15,
            height=2,
            relief="flat",
            command=self.connect_as_student
        )
        connect_btn.pack(pady=(20, 10))
        connect_btn.bind("<Enter>", lambda e: connect_btn.config(bg="#2ecc71"))
        connect_btn.bind("<Leave>", lambda e: connect_btn.config(bg="#44bd32"))

        back_btn = tk.Button(
            card,
            text="⬅️ Quay lại",
            font=("Arial", 11, "bold"),
            bg="#718093",
            fg="white",
            relief="flat",
            command=self.create_intro_screen
        )
        back_btn.pack(pady=(5, 5))
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#636e72"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#718093"))

        # =================== ĐĂNG NHẬP ADMIN ===================
    def open_teacher_login(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        header = tk.Frame(self.root, bg="#273c75")
        header.pack(fill="x")

        tk.Label(
            header,
            text="👨‍💻 CỔNG QUẢN TRỊ VIÊN",
            font=("Arial", 22, "bold"),
            bg="#273c75",
            fg="#f5f6fa",
            pady=15
        ).pack(side="left", padx=25)

        back_btn = tk.Button(
            header,
            text="⬅️ Quay lại",
            font=("Arial", 12, "bold"),
            bg="#7f8fa6",
            fg="white",
            relief="flat",
            command=self.create_main_screen
        )
        back_btn.pack(side="right", padx=25, pady=10)
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#718093"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#7f8fa6"))

        # ==== KHUNG NỀN ====
        main_frame = tk.Frame(self.root, bg="#1e272e")
        main_frame.pack(fill="both", expand=True)

        # ==== CARD ====
        card = tk.Frame(
            main_frame,
            bg="#273c75",
            highlightbackground="#487eb0",
            highlightthickness=2,
            bd=0
        )
        card.place(relx=0.5, rely=0.5, anchor="center", width=480, height=400)

        tk.Label(
            card,
            text="🔐 ĐĂNG NHẬP HỆ THỐNG",
            font=("Arial", 18, "bold"),
            bg="#273c75",
            fg="#00cec9"
        ).pack(pady=(25, 25))

        form_frame = tk.Frame(card, bg="#273c75")
        form_frame.pack()

        tk.Label(
            form_frame,
            text="👤  Tên đăng nhập:",
            bg="#273c75",
            fg="white",
            font=("Arial", 13)
        ).grid(row=0, column=0, sticky="w", pady=8, padx=5)
        self.user_entry = tk.Entry(form_frame, font=("Arial", 13), width=25, bg="#f5f6fa", relief="flat")
        self.user_entry.grid(row=0, column=1, pady=8, padx=10)

        tk.Label(
            form_frame,
            text="🔒  Mật khẩu:",
            bg="#273c75",
            fg="white",
            font=("Arial", 13)
        ).grid(row=1, column=0, sticky="w", pady=8, padx=5)
        self.pass_entry = tk.Entry(form_frame, show="*", font=("Arial", 13), width=25, bg="#f5f6fa", relief="flat")
        self.pass_entry.grid(row=1, column=1, pady=8, padx=10)

        login_btn = tk.Button(
            card,
            text="🚪 ĐĂNG NHẬP",
            font=("Arial", 14, "bold"),
            bg="#0984e3",
            fg="white",
            width=18,
            height=2,
            relief="flat",
            command=self.teacher_login
        )
        login_btn.pack(pady=(30, 15))
        login_btn.bind("<Enter>", lambda e: login_btn.config(bg="#74b9ff"))
        login_btn.bind("<Leave>", lambda e: login_btn.config(bg="#0984e3"))

        tk.Label(
            card,
            text="* Dành riêng cho admin quản lý phòng máy",
            font=("Arial", 10, "italic"),
            bg="#273c75",
            fg="#dfe6e9"
        ).pack(pady=(5, 0))

    # =================== CHỨC NĂNG ===================
    def teacher_login(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()

        if username == TEACHER_USERNAME and password == TEACHER_PASSWORD:
            self.session_id = secrets.token_hex(3).upper()
            self.save_session()
            messagebox.showinfo("Đăng nhập thành công", f"Chào {username}!\nMã code hôm nay là: {self.session_id}")
            self.launch_server()
        else:
            messagebox.showerror("Sai thông tin", "Tên đăng nhập hoặc mật khẩu không đúng.")

    def save_session(self):
        with open(SESSION_FILE, "w") as f:
            json.dump({"session_id": self.session_id}, f)

    def connect_as_student(self):
        code = self.code_entry.get().strip().upper()
        if not code:
            self.status_label.config(text="⚠️ Vui lòng nhập mã code trước.")
            return

        messagebox.showinfo("Thành công", "Đang tìm và kết nối đến máy admin...")
        self.launch_client(code)

    def launch_server(self):
        try:
            subprocess.Popen([sys.executable, "server.py"])
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở server.py\n{e}")

    def launch_client(self, session_id):
        try:
            subprocess.Popen([sys.executable, "client.py", session_id])
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở client.py\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = AppLauncher(root)
    root.mainloop()
