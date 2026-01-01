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
        self.root.title("PTA 专用打字机 (补全粉碎版)")
        self.root.geometry("500x700")
        self.root.attributes("-topmost", True)

        self.label = tk.Label(root,
                              text="策略更新：\n1. 输入 '{' 后立即按 Delete 删除自动补全\n2. 恢复正常输入 '}'\n3. 保持极速去缩进模式",
                              font=("Arial", 11), fg="#d32f2f")
        self.label.pack(pady=10)

        self.text_area = scrolledtext.ScrolledText(root, width=50, height=15, font=("Arial", 10))
        self.text_area.pack(pady=5)

        self.btn_start = tk.Button(root, text="光速输入 (5秒倒计时)", command=self.start_thread, bg="#D32F2F",
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

        # 解除限速
        pyautogui.PAUSE = 0.005

        try:
            target_hwnd, original_layout = self.get_foreground_window_info()
            if original_layout != HKL_ENGLISH:
                self.change_layout(target_hwnd, HKL_ENGLISH)
                time.sleep(0.2)

            for index, line in enumerate(lines):
                # 1. 去掉行首空格 (利用 PTA 的自动缩进)
                stripped_line = line.lstrip()

                # 如果是空行，直接回车
                if not stripped_line:
                    if index < len(lines) - 1:
                        pyautogui.press('enter')
                    continue

                # === 核心逻辑修改：精细化处理 '{' ===
                # 我们不能直接 write(stripped_line)，因为要中间插入 Delete

                if '{' in stripped_line:
                    # 如果这一行包含 {，我们需要切开处理
                    segments = stripped_line.split('{')
                    for i, seg in enumerate(segments):
                        # 输入 { 前面的内容
                        if seg:
                            pyautogui.write(seg, interval=0)

                        # 如果这不是最后一段，说明刚才 split 掉了一个 {
                        # 所以我们要补一个 {，然后马上删除自动生成的 }
                        if i < len(segments) - 1:
                            pyautogui.write('{', interval=0)
                            # 此时 PTA 变成了 {|}，光标在中间
                            # 按 Delete 删除光标右边的 }
                            pyautogui.press('delete')
                else:
                    # 如果这一行没有 {，直接光速输入
                    pyautogui.write(stripped_line, interval=0)

                # 2. 换行
                if index < len(lines) - 1:
                    pyautogui.press('enter')

            self.status_label.config(text="输入完成！", fg="green")

        except pyautogui.FailSafeException:
            self.status_label.config(text="已强制停止", fg="red")

        finally:
            pyautogui.PAUSE = 0.1
            if target_hwnd and original_layout and original_layout != HKL_ENGLISH:
                self.change_layout(target_hwnd, original_layout)
            self.btn_start.config(state=tk.NORMAL)
            self.root.after(2000, lambda: self.status_label.config(text="就绪", fg="gray"))


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoTyperApp(root)
    root.mainloop()