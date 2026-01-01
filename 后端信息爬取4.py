import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import random
import re

# ================= 配置区 =================
TARGET_URL = "https://detail.tmall.com/item.htm?id=969963951158&mi_id=0000ALSxIO1xRJw-xqWqmvyMVOAh-I5EvFPze0-GKcJwOMY&pvid=b8c28b81-5a4b-4bd1-b6ff-3ada7926b549&scm=1007.57291.421744.0&skuId=5919899984777&spm=tbpc.item_error.201876.d20.3a007dd60tcFIG&utparam=%7B%22x_object_type%22%3A%22item%22%2C%22matchType%22%3A%22dm_interest%22%2C%22item_price%22%3A%2228%22%2C%22umpCalled%22%3Atrue%2C%22pc_scene%22%3A%2220001%22%2C%22userId%22%3A3274212352%2C%22ab_info%22%3A%2247291%23421744%23-1%23%22%2C%22tpp_buckets%22%3A%2247291%23421744%23module%22%2C%22isLogin%22%3Atrue%2C%22abid%22%3A3%2C%22pc_pvid%22%3A%22b8c28b81-5a4b-4bd1-b6ff-3ada7926b549%22%2C%22isWeekLogin%22%3Afalse%2C%22rn%22%3A19%2C%22ump_price%22%3A%2228%22%2C%22isXClose%22%3Afalse%2C%22x_object_id%22%3A969963951158%7D&xxc=home_recommend"
MAX_COMMENTS = 500  # 目标抓取数量


# =========================================

def check_login_status(driver):
    try:
        cookies = driver.get_cookies()
        for cookie in cookies:
            if cookie['name'] in ['_nk_', 'tracknick', 'lgc', '_l_g_']:
                return True
        if "退出" in driver.page_source:
            return True
    except:
        pass
    return False


def is_junk_text(text):
    """
    【过滤器】强力过滤 SKU 信息、系统文案、优惠券、销量标签
    """
    # 1. 过滤日期开头的 (例如 "2025-10-25 ...")
    if re.match(r'^\d{4}[-年]\d{1,2}[-月]\d{1,2}', text): return True

    # 2. 过滤 SKU 堆砌信息 (特征：包含大量 ✅ 或 【】)
    if "✅" in text or text.startswith("【") or text.startswith("["): return True

    # 3. 关键词黑名单 (新增：已售、满减、立减、真实评价等干扰词)
    junk_keywords = [
        "已购", "颜色分类", "尺码", "规格", "款式",
        "此用户没有填写", "系统默认", "评价方未及时做出评价",
        "用户评价", "查看全部", "浏览量", "销量", "追评",
        "人已买", "视频", "图片", "评论", "天猫", "积分",
        "已售", "满", "减", "立减", "为你展示", "真实评价",
        "如果不满意", "退货", "运费"  # 过滤部分商家售后文案，保留用户真实吐槽
    ]
    for k in junk_keywords:
        if k in text: return True

    # 4. 长度过滤 (太短通常是标签，太长可能是代码干扰)
    # 评论一般不会只有 5 个字以下（除非是“好”，“不错”这种，容易误伤标签，暂且保留限制）
    if len(text) < 4 or len(text) > 800: return True

    # 5. 正则过滤“满xxx减xxx”这种优惠券文本
    if re.search(r'满\d+减\d+', text): return True

    return False


def scroll_internal_panel(driver, element):
    """
    【核心黑科技】寻找并滚动内部容器
    """
    js_script = """
    var element = arguments[0];
    var scrollable = null;
    var parent = element.parentElement;

    // 向上遍历 10 层，寻找带有滚动条的容器
    for (var i = 0; i < 10; i++) {
        if (!parent) break;
        var style = window.getComputedStyle(parent);
        if (style.overflowY === 'auto' || style.overflowY === 'scroll' || parent.scrollHeight > parent.clientHeight) {
            scrollable = parent;
            break;
        }
        parent = parent.parentElement;
    }

    if (scrollable) {
        scrollable.scrollTop = scrollable.scrollHeight;
        return true;
    } else {
        window.scrollTo(0, document.body.scrollHeight);
        return false;
    }
    """
    try:
        return driver.execute_script(js_script, element)
    except:
        return False


def start_crawler():
    print("正在启动 Chrome 浏览器...")

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--start-maximized")

    user_data_dir = r"D:\SeleniumUserData"
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)

    # 2. 添加参数挂载该目录
    options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)

    try:
        print(f"正在打开网页: {TARGET_URL}")
        driver.get(TARGET_URL)

        # === 1. 智能登录 ===
        print("=" * 50)
        print("请扫码登录！(实时监控中...)")
        print("=" * 50)

        start_wait_time = time.time()
        is_logged_in = False

        while time.time() - start_wait_time < 60:
            try:
                modal_btns = driver.find_elements(By.XPATH, "//*[contains(text(), '知道了')]")
                for btn in modal_btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
            except:
                pass

            if check_login_status(driver):
                print("\n✅ 登录成功！")
                is_logged_in = True
                break
            print(f"\r⏳ 等待登录... {int(60 - (time.time() - start_wait_time))}s", end="")
            time.sleep(0.5)

        if not is_logged_in:
            print("\n⚠️ 登录超时，尝试强制执行...")
        else:
            time.sleep(1)

        # === 2. 导航至评论区 ===
        print("正在跳转评论区...")
        driver.execute_script("window.scrollBy(0, 300);")
        time.sleep(1)

        try:
            nav_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='用户评价']")))
            driver.execute_script("arguments[0].click();", nav_tab)
            time.sleep(2)
        except:
            print("⚠️ 未找到导航Tab")

        try:
            driver.execute_script("window.scrollBy(0, 200);")
            time.sleep(1)
            view_all_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '查看全部评价')]")))
            driver.execute_script("arguments[0].click();", view_all_btn)
            print("✅ 已展开全部评价！")
            time.sleep(2)
        except:
            print("⚠️ 没找到展开按钮")

        # === 3. 智能滚雪球抓取 ===
        print(f"开始深度抓取... 目标: {MAX_COMMENTS} 条")
        comments = []
        last_comment_count = 0
        stuck_count = 0

        for i in range(100):
            # 1. 抓取
            elements = driver.find_elements(By.XPATH, "//div[string-length(text())>3]")  # 放宽长度限制，交给过滤器处理
            for elem in elements:
                try:
                    text = elem.text.strip()
                    # 强力过滤
                    if not is_junk_text(text):
                        if not any(c['content'] == text for c in comments):
                            comments.append({"content": text, "source": "Selenium"})
                            if len(comments) >= MAX_COMMENTS: raise StopIteration
                except:
                    continue

            # 2. 判断状态
            current_count = len(comments)
            new_added = current_count - last_comment_count
            print(f"🔄 第 {i + 1} 轮 | 总数: {current_count} | 本轮新增: {new_added} 条")

            if elements:
                last_element = elements[-1]

                if new_added > 0:
                    stuck_count = 0
                    print("  -> 🔽 正在滚动内部容器...")
                    result = scroll_internal_panel(driver, last_element)
                    if not result:
                        driver.execute_script("arguments[0].scrollIntoView(false);", last_element)
                    time.sleep(random.uniform(2.0, 3.0))

                else:
                    stuck_count += 1
                    if stuck_count >= 3:
                        print(f"  -> 🛑 连续卡顿 {stuck_count} 次，判定为已到达底部，停止抓取。")
                        break

                    print(f"  -> ⚠️ 卡顿 {stuck_count} 次，尝试强力刷新...")
                    driver.execute_script("arguments[0].scrollIntoView(true);", last_element)
                    time.sleep(1)
                    scroll_internal_panel(driver, last_element)
                    driver.execute_script("window.scrollBy(0, 500);")
                    time.sleep(4)
            else:
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(2)

            last_comment_count = current_count

    except StopIteration:
        print("\n🎉 已达到目标数量！")
    except Exception as e:
        print(f"运行出错: {e}")

    finally:
        if comments:
            print(f"\n🎉 最终保存：{len(comments)} 条")
            df = pd.DataFrame(comments)
            # 关键修改：指定换行符为 Windows 标准的 \r\n，解决“不换行/拥挤”的问题
            # 并且使用 utf-8-sig 编码，防止 Excel 打开乱码
            df.to_csv("tmall_real_data.csv", index=False, encoding='utf-8-sig', lineterminator='\r\n')
            print("文件已保存: tmall_real_data.csv (已优化换行格式)")
        else:
            print("\n❌ 未抓到数据")
        print("任务结束")


if __name__ == "__main__":
    start_crawler()