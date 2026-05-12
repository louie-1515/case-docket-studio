import subprocess
import webbrowser
import sys
import os
import tkinter as tk
from tkinter import ttk

APP_DIR = os.path.dirname(os.path.abspath(__file__))


class AppLauncher:
    def __init__(self):
        self.proc = None

        self.root = tk.Tk()
        self.root.title("案件智能分析台")
        self.root.geometry("320x140")
        self.root.resizable(False, False)

        ttk.Label(self.root, text="案件智能分析台 正在运行", font=("微软雅黑", 12, "bold")).pack(pady=(15, 5))
        ttk.Label(self.root, text="浏览器已打开 http://localhost:5000", foreground="#666").pack()
        ttk.Button(self.root, text="停止服务", command=self.stop).pack(pady=15)

        self.root.protocol("WM_DELETE_WINDOW", self.stop)
        self.root.eval('tk::PlaceWindow . center')

    def start(self):
        self.proc = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=APP_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.root.after(2000, self._open_browser)
        self.root.mainloop()

    def _open_browser(self):
        webbrowser.open("http://localhost:5000")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.root.destroy()


if __name__ == "__main__":
    AppLauncher().start()
