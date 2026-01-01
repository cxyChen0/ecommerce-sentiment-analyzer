import tkinter as tk
from tkinter import scrolledtext
import pyautogui
import time
import threading
import ctypes

# Windows API
user32 = ctypes.windll.user32
WM_INPUTLANGCHANGEREQUEST = 0x0050
HKL_ENGLISH = 0x04090409


class AutoTyperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PTA 专用打字机 (光速跳过版)")
        self.root.geometry("500x700")
        self.root.attributes("-topmost", True)

        self.label = tk.Label(root,
                              text="PTA 终极优化：\n1. 遇到 } 不输入，直接按↓跳过\n2. 强制解除所有延迟限制\n3. 自动去除行首缩进",
                              font=("Arial", 11), fg="#d32f2f")
        self.label.pack(pady=10)

        self.text_area = scrolledtext.ScrolledText(root, width=50, height=15, font=("Arial", 10))
        self.text_area.pack(pady=5)

        self.btn_start = tk.Button(root, text="光速输入 (5秒倒计时)", command=self.start_thread, bg="#FF0000",
                                   fg="white", font=("Arial", 12, "bold"))
        self.btn_start.pack(pady=15)

        self.status_label = tk.Label(root, text="就绪", fg="gray")
        self.status_label.pack()

    def start_thread(self):
        threading.Thread(target=self.run_typing, daemon=True).start()

    def get_foreground_window_info(self):
        hwnd = user32.GetForegroundWindow()
        thread_id = user32.GetWindowThreadProcessId(hwnd, 0)
        current_layout = user32.GetKeyboardLayout(thread_id)
        return hwnd, current_layout

    def change_layout(self, hwnd, layout_id):
        user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, layout_id)

    def run_typing(self):
        raw_content = self.text_area.get("1.0", tk.END).strip()
        if not raw_content:
            return

        lines = raw_content.split('\n')
        self.btn_start.config(state=tk.DISABLED)

        # 倒计时
        for i in range(5, 0, -1):
            self.status_label.config(text=f"请切换到 PTA 窗口... {i}", fg="blue")
            time.sleep(1)

        self.status_label.config(text="正在光速输入...", fg="green")

        target_hwnd = None
        original_layout = None

        # === 核心修改1：解除库的全局限速 ===
        # 默认是 0.1秒，改成 0.005秒，速度提升20倍
        pyautogui.PAUSE = 0.005

        try:
            target_hwnd, original_layout = self.get_foreground_window_info()
            if original_layout != HKL_ENGLISH:
                self.change_layout(target_hwnd, HKL_ENGLISH)
                time.sleep(0.2)

            for index, line in enumerate(lines):
                # 1. 去除行首空格 (解决缩进问题)
                stripped_line = line.lstrip()

                # === 核心修改2：智能处理 } ===
                # 如果这一行以 } 开头（例如 "}" 或 "} else {"）
                if stripped_line.startswith('}'):
                    # 不要打这个 }，而是按“下箭头”跳过 PTA 自动生成的那个 }
                    pyautogui.press('down')

                    # 去掉开头的 }，如果后面还有内容（比如 " else {"），则继续输入
                    remaining_content = stripped_line[1:]
                    if remaining_content:
                        pyautogui.write(remaining_content, interval=0)
                else:
                    # 普通行，直接输入
                    if stripped_line:
                        pyautogui.write(stripped_line, interval=0)

                # 处理换行
                if index < len(lines) - 1:
                    pyautogui.press('enter')

            self.status_label.config(text="输入完成！", fg="green")

        except pyautogui.FailSafeException:
            self.status_label.config(text="已强制停止", fg="red")

        finally:
            # 恢复默认速度，以免影响其他程序
            pyautogui.PAUSE = 0.1

            if target_hwnd and original_layout and original_layout != HKL_ENGLISH:
                self.change_layout(target_hwnd, original_layout)
            self.btn_start.config(state=tk.NORMAL)
            self.root.after(2000, lambda: self.status_label.config(text="就绪", fg="gray"))


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoTyperApp(root)
    root.mainloop()