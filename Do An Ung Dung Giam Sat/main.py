# main.py
import tkinter as tk
from tkinter import messagebox
import subprocess
import secrets
import json
import os
import sys

# ======= CẤU HÌNH MẶC ĐỊNH =======
TEACHER_USERNAME = "ITadmin"
TEACHER_PASSWORD = "ithcm123"
SESSION_FILE = "session.json"


class AppLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("Ứng dụng Giám sát Phòng máy")
        self.root.geometry("500x350")
        self.root.configure(bg="#ecf0f1")
        self.session_id = None

        self.create_main_screen()

    # ========== GIAO DIỆN CHÍNH ==========
    def create_main_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        # Header
        header_frame = tk.Frame(self.root, bg="#2c3e50")
        header_frame.pack(fill="x")
        tk.Label(header_frame, text="Ứng dụng Giám sát Phòng máy",
                 font=("Arial", 16, "bold"), bg="#2c3e50", fg="white", pady=10).pack(side="left", padx=15)

        teacher_btn = tk.Button(header_frame, text="Đăng nhập Giáo viên",
                                font=("Arial", 10, "bold"),
                                bg="#e67e22", fg="white", command=self.open_teacher_login)
        teacher_btn.pack(side="right", padx=15, pady=10)

        # Nội dung chính
        frame = tk.Frame(self.root, bg="#ecf0f1")
        frame.pack(expand=True)

        tk.Label(frame, text="Học sinh nhập mã lớp cô giáo cung cấp:",
                 font=("Arial", 12), bg="#ecf0f1").pack(pady=10)

        self.code_entry = tk.Entry(frame, font=("Arial", 14), width=20, justify="center")
        self.code_entry.pack(pady=10)

        tk.Button(frame, text="KẾT NỐI", font=("Arial", 12, "bold"),
                  bg="#27ae60", fg="white", width=15, height=1,
                  command=self.connect_as_student).pack(pady=10)

        self.status_label = tk.Label(frame, text="", font=("Arial", 10), bg="#ecf0f1", fg="#7f8c8d")
        self.status_label.pack(pady=5)

    # ========== ĐĂNG NHẬP GIÁO VIÊN ==========
    def open_teacher_login(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="Đăng nhập dành cho giáo viên",
                 font=("Arial", 14, "bold"), bg="#ecf0f1").pack(pady=20)

        tk.Label(self.root, text="Tên đăng nhập:", bg="#ecf0f1", font=("Arial", 11)).pack()
        self.user_entry = tk.Entry(self.root, font=("Arial", 12))
        self.user_entry.pack(pady=5)

        tk.Label(self.root, text="Mật khẩu:", bg="#ecf0f1", font=("Arial", 11)).pack()
        self.pass_entry = tk.Entry(self.root, show="*", font=("Arial", 12))
        self.pass_entry.pack(pady=5)

        tk.Button(self.root, text="ĐĂNG NHẬP", font=("Arial", 12, "bold"),
                  bg="#2980b9", fg="white", width=15,
                  command=self.teacher_login).pack(pady=15)

        tk.Button(self.root, text="Quay lại", command=self.create_main_screen,
                  bg="#bdc3c7", fg="black").pack()

    def teacher_login(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()

        if username == TEACHER_USERNAME and password == TEACHER_PASSWORD:
            self.session_id = secrets.token_hex(3).upper()
            self.save_session()
            messagebox.showinfo("Đăng nhập thành công",
                                f"Chào cô giáo!\nMã lớp hôm nay là: {self.session_id}")
            self.launch_server()
        else:
            messagebox.showerror("Sai thông tin", "Tên đăng nhập hoặc mật khẩu không đúng.")

    def save_session(self):
        with open(SESSION_FILE, "w") as f:
            json.dump({"session_id": self.session_id}, f)

    # ========== HỌC SINH ==========
    def connect_as_student(self):
        code = self.code_entry.get().strip().upper()
        if not code:
            self.status_label.config(text="Vui lòng nhập mã lớp trước.")
            return

        messagebox.showinfo("Thành công", "Đang tìm và kết nối đến máy giáo viên...")
        self.launch_client(code)

    # ========== MỞ FILE SERVER / CLIENT ==========
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