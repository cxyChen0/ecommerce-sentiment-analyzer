import subprocess
import time
import os
import random
import socket
import pandas as pd
import re
import shutil
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# ================= 配置区 =================
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9222
MAX_COMMENTS = 200
# =========================================

# 创建临时目录 (保证纯净启动)
TEMP_USER_DATA = tempfile.mkdtemp()


def is_port_open(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0


def start_browser_process():
    """启动浏览器 (纯净模式)"""
    if is_port_open("127.0.0.1", DEBUG_PORT):
        print("⚠️ 检测到端口 9222 已被占用，请手动关闭旧窗口后重试。")
        return False

    print(f"🚀 正在启动纯净版 Chrome...")
    # 核心：不带 --disable-blink-features=AutomationControlled 以免触发警告条
    # 使用 --no-first-run 跳过欢迎页
    cmd = f'"{CHROME_PATH}" --remote-debugging-port={DEBUG_PORT} --user-data-dir="{TEMP_USER_DATA}" --no-first-run --no-default-browser-check'

    subprocess.Popen(cmd, shell=True)

    print("⏳ 等待浏览器启动...", end="")
    for i in range(20):
        if is_port_open("127.0.0.1", DEBUG_PORT):
            print(" 成功！")
            return True
        time.sleep(1)
        print(".", end="")
    return False


def apply_stealth(driver):
    """
    【增强隐身术】全方位移除机器人特征
    """
    print("🥷 正在施展隐身术...")
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            // 1. 移除 webdriver 属性
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 2. 伪造 plugins (美团可能会检测这个)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // 3. 伪造 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });

            // 4. 欺骗一些常见检测点
            window.chrome = { runtime: {} };
        """
    })


def enable_mobile_mode_via_cdp(driver):
    print("📲 激活手机模式 (iPhone 12 Pro)...")
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 390, "height": 844, "deviceScaleFactor": 3,
            "mobile": True, "screenWidth": 390, "screenHeight": 844,
        })
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {
            "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        })
    except:
        pass


def is_junk_text(text):
    if len(text) < 4: return True
    junk = ["评价", "全部", "有图", "好评", "差评", "最新", "推荐", "按热度", "商家回复", "满意", "味道好", "包装",
            "分量", "重新加载"]
    if text in junk: return True
    if "✅" in text or text.startswith("【"): return True
    return False


def try_fix_network_error(driver):
    """尝试点击'重新加载'按钮"""
    try:
        # 查找包含“重新加载”文字的按钮或div
        btns = driver.find_elements(By.XPATH, "//*[contains(text(), '重新加载')]")
        if btns:
            print("🔨 发现'重新加载'按钮，正在点击...")
            for btn in btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
            return True
    except:
        pass
    return False


def main():
    # 强制清理旧进程，保证环境纯净
    print("🧹 清理环境...")
    try:
        os.system("taskkill /f /im chrome.exe >nul 2>&1")
        time.sleep(1)
    except:
        pass

    if not start_browser_process():
        print("❌ 浏览器启动失败。")
        return

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{DEBUG_PORT}")

    print("🔗 连接 Selenium...")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    # 先隐身，再伪装，最后打开网页
    apply_stealth(driver)
    enable_mobile_mode_via_cdp(driver)

    print("🌐 打开美团首页...")
    driver.get("https://h5.waimai.meituan.com/waimai/mindex/home")

    # === 交互式等待区 ===
    print("\n" + "=" * 60)
    print("🛑 【人工操作阶段】")
    print("请在浏览器中操作：")
    print("1. 登录账号 (如果白屏，按 F5 刷新)。")
    print("2. 遇到“网络不给力”？请在这里输入 r 并回车，我帮你点重试。")
    print("3. 进入店铺 -> 点击【评价】标签，确保评价列表显示出来。")
    print("-" * 60)

    while True:
        user_input = input("👉 准备好后直接按【回车】开始，或者输入 r 修复网络错误: ").strip().lower()
        if user_input == 'r':
            print("🔄 尝试修复网络错误...")
            if try_fix_network_error(driver):
                print("✅ 已点击，请观察浏览器是否恢复。")
            else:
                print("⚠️ 未找到“重新加载”按钮，请手动刷新页面 (F5)。")
        else:
            print("🚀 收到指令，开始自动抓取！")
            break
    print("=" * 60 + "\n")

    # === 自动抓取 ===
    print(f"🤖 正在抓取... 目标: {MAX_COMMENTS} 条")
    comments = []

    try:
        for i in range(100):
            # 每次滑动前，检查一下是不是又网络错误了
            try_fix_network_error(driver)

            print(f"🔄 第 {i + 1} 轮滑动 | 已收集: {len(comments)} 条")

            elements = driver.find_elements(By.XPATH, "//div[string-length(text())>4]")

            new_count = 0
            for elem in elements:
                try:
                    text = elem.text.strip()
                    if not is_junk_text(text):
                        if text not in [c['content'] for c in comments]:
                            print(f"  + 捕获: {text[:15].replace(chr(10), ' ')}...")
                            comments.append({"content": text})
                            new_count += 1
                            if len(comments) >= MAX_COMMENTS: raise StopIteration
                except:
                    continue

            if new_count == 0:
                print("  ⚠️ 没新数据，尝试滚到底部...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            else:
                driver.execute_script("window.scrollBy(0, 800);")

            time.sleep(random.uniform(2, 4))

    except StopIteration:
        print("\n🎉 达标停止！")
    except Exception as e:
        print(f"❌ 出错: {e}")

    finally:
        if comments:
            df = pd.DataFrame(comments)
            df.to_csv("meituan_comments.csv", index=False, encoding='utf-8-sig')
            print(f"🎉 保存成功: meituan_comments.csv")

        # 清理临时文件夹
        try:
            shutil.rmtree(TEMP_USER_DATA, ignore_errors=True)
        except:
            pass

        print("脚本结束。")


if __name__ == "__main__":
    main()