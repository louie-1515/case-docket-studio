import os
import socket
import subprocess
import tkinter as tk
import webbrowser

PORT = 5000
URL = f"http://127.0.0.1:{PORT}"
PROJECT = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(PROJECT, ".server.pid")
CHECK_INTERVAL = 3000  # ms

RUNNING_COLOR = "#22c55e"
STOPPED_COLOR = "#ef4444"
FONT = ("Microsoft YaHei", 10)
FONT_BOLD = ("Microsoft YaHei", 11, "bold")
FONT_SMALL = ("Microsoft YaHei", 8)


def is_running():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", PORT))
        s.close()
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def read_pid():
    try:
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def kill_by_pid(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                   capture_output=True, creationflags=0x08000000)


def kill_port(port):
    """通过 netstat 查到占用端口的 PID，强制结束。PID 文件丢失/过期时的 fallback。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True,
            creationflags=0x08000000,
        ).stdout
        killed = set()
        for line in out.splitlines():
            if f":{port}" not in line or "LISTENING" not in line:
                continue
            parts = line.strip().split()
            pid = parts[-1]
            if pid.isdigit() and pid not in killed:
                kill_by_pid(int(pid))
                killed.add(pid)
    except Exception:
        pass


class Panel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("案件智能分析台 · 控制台")
        self.root.resizable(False, False)
        w, h = 300, 200
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{ws - w - 40}+{hs - h - 80}")
        self.root.configure(bg="#f8fafc")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self._update()
        self._poll()

    def _on_close(self):
        self.root.destroy()

    def _build(self):
        f = tk.Frame(self.root, bg="#f8fafc")
        f.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        tk.Label(f, text="案件智能分析台", font=FONT_BOLD, bg="#f8fafc").pack(anchor="w")

        status = tk.Frame(f, bg="#f8fafc")
        status.pack(fill=tk.X, pady=(6, 12))
        self._dot = tk.Canvas(status, width=10, height=10, highlightthickness=0, bg="#f8fafc")
        self._dot.pack(side=tk.LEFT, padx=(0, 6))
        self._dot_circle = self._dot.create_oval(1, 1, 9, 9, fill=STOPPED_COLOR, outline="")
        self._label = tk.Label(status, text="检测中...", font=FONT, bg="#f8fafc")
        self._label.pack(side=tk.LEFT)

        row = tk.Frame(f, bg="#f8fafc")
        row.pack(fill=tk.X, pady=2)
        b = tk.Button(row, text="打开网页", font=FONT, command=lambda: webbrowser.open(URL))
        b.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)

        row2 = tk.Frame(f, bg="#f8fafc")
        row2.pack(fill=tk.X, pady=2)
        self._btn_start = tk.Button(row2, text="启动", font=FONT, fg=STOPPED_COLOR, command=self._start)
        self._btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2, padx=(0, 2))
        self._btn_stop = tk.Button(row2, text="关闭", font=FONT, fg=STOPPED_COLOR, command=self._stop)
        self._btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2, padx=(2, 0))

        tk.Label(f, text=f"浏览器访问 {URL}", font=FONT_SMALL, fg="#94a3b8", bg="#f8fafc").pack(pady=(10, 0))

    def _update(self):
        running = is_running()
        if running:
            self._dot.itemconfig(self._dot_circle, fill=RUNNING_COLOR)
            self._label.config(text="运行中", fg=RUNNING_COLOR)
            self._btn_start.config(state=tk.DISABLED, fg="#94a3b8")
            self._btn_stop.config(state=tk.NORMAL, fg=STOPPED_COLOR)
        else:
            # 端口不通时清理残留 pid 文件
            if read_pid():
                try:
                    os.remove(PID_FILE)
                except OSError:
                    pass
            self._dot.itemconfig(self._dot_circle, fill=STOPPED_COLOR)
            self._label.config(text="已关闭", fg=STOPPED_COLOR)
            self._btn_start.config(state=tk.NORMAL, fg=RUNNING_COLOR)
            self._btn_stop.config(state=tk.DISABLED, fg="#94a3b8")

    def _poll(self):
        self._update()
        self.root.after(CHECK_INTERVAL, self._poll)

    def _start(self):
        os.chdir(PROJECT)
        proc = subprocess.Popen(
            ["py", "-3", os.path.join("project", "app.py")],
            creationflags=0x08000000,
        )
        # 记下 PID 供快速关闭
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
        self.root.after(1200, self._update)

    def _stop(self):
        killed = False
        pid = read_pid()
        if pid:
            kill_by_pid(pid)
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
            killed = True
        # 如果端口仍被占用（PID 文件丢失 / Flask reloader 子进程未跟随父进程退出），
        # 通过 netstat 直接查端口占用者并杀掉
        for _ in range(3):
            if not is_running():
                break
            self.root.update()
            self.root.after(400)
        if is_running():
            kill_port(PORT)
        # 轮询等待端口释放，最多等 5 秒
        for _ in range(25):
            if not is_running():
                break
            self.root.update()
            self.root.after(200)
        self._update()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Panel().run()
