import os
import time
import random
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================= 配置区 =================
MAX_COMMENTS = 200  # 目标抓取数量
SCROLL_PAUSE_MIN = 0.5  # 最小等待时间 (秒)
SCROLL_PAUSE_MAX = 0.8  # 最大等待时间 (秒)
MAX_STUCK_COUNT = 2  # 连续无数据退出阈值


# =========================================

def check_login_status(driver):
    """检测是否需要登录"""
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
    """【过滤器】强力过滤 SKU、系统文案、单纯的日期行、无效评价"""
    if not text: return True
    text = text.strip()

    if len(text) < 4: return True

    # 如果整段文字本身就是日期，它不是评论内容，过滤掉（但我们会通过上下文提取它作为元数据）
    if len(text) < 25 and re.search(r'\d{4}[-年]\d{1,2}[-月]\d{1,2}', text):
        return True

    if "✅" in text or text.startswith("【") or text.startswith("["): return True

    junk_keywords = [
        "已购", "颜色分类", "尺码", "规格", "款式",
        "此用户没有填写", "系统默认", "评价方未及时做出评价",
        "未及时主动评价", "系统默认好评", "自动好评",
        "用户评价", "查看全部", "浏览量", "销量", "追评",
        "人已买", "视频", "图片", "评论", "天猫", "积分",
        "已售", "满", "减", "立减", "为你展示", "真实评价",
        "如果不满意", "退货", "运费", "上门取件",
        "默认排序", "按热度", "按时间", "推荐", "问大家", "宝贝细节",
        "旗舰店", "专卖店", "月销", "库存", "发货", "付款", "折"
    ]
    for k in junk_keywords:
        if k in text: return True

    if "¥" in text or "￥" in text: return True
    if re.search(r'满\d+减\d+', text): return True

    return False


def scroll_internal_panel(driver, element):
    """【核心黑科技】只滚动内部容器"""
    js_script = """
    var element = arguments[0];
    var scrollable = null;
    var parent = element.parentElement;
    for (var i = 0; i < 15; i++) {
        if (!parent) break;
        var style = window.getComputedStyle(parent);
        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && parent.scrollHeight > parent.clientHeight) {
            scrollable = parent;
            break;
        }
        parent = parent.parentElement;
    }
    if (scrollable) {
        scrollable.scrollTop = scrollable.scrollHeight;
        return true;
    } else {
        return false; 
    }
    """
    try:
        return driver.execute_script(js_script, element)
    except:
        return False


# === 辅助函数：上下文日期提取 ===
def extract_date_from_context(element):
    """
    尝试从当前元素的父级或祖父级文本中提取日期
    返回格式: YYYY-MM-DD 或 YYYY年MM月DD日
    """
    date_pattern = r'(\d{4}[-年]\d{1,2}[-月]\d{1,2})'

    try:
        # 策略1: 找爸爸 (Parent)
        # 很多时候评论内容和日期在同一个大的 div 容器里
        parent = element.find_element(By.XPATH, "..")
        parent_text = parent.text
        match = re.search(date_pattern, parent_text)
        if match:
            return match.group(1)

        # 策略2: 找爷爷 (Grandparent)
        # 结构较深时使用
        grandparent = element.find_element(By.XPATH, "../..")
        grand_text = grandparent.text
        match = re.search(date_pattern, grand_text)
        if match:
            return match.group(1)

    except:
        pass

    return ""  # 没找到


# === 搜索函数 ===
def get_search_links(keyword, count=3):
    print(f"🔍 [Search] 正在搜索: {keyword}")
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    user_data_dir = r"D:\Login_dataset\SeleniumUserData_Search"
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument("--start-maximized")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    driver = None
    links = []
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(f"https://s.taobao.com/search?q={keyword}")
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'item.htm')]")))
        except:
            time.sleep(2)

        elements = driver.find_elements(By.XPATH, "//a[contains(@href, 'item.htm') and not(contains(@href, 'click'))]")
        for elem in elements:
            url = elem.get_attribute("href")
            if url and "id=" in url:
                if not url.startswith("http"): url = "https:" + url
                if url not in links: links.append(url)
            if len(links) >= count: break
    except Exception as e:
        print(f"搜索出错: {e}")
        return []
    finally:
        if driver: driver.quit()
    return links


# === 核心爬虫 ===
def run_spider(target_url, worker_id=1):
    print(f"🚀 [线程-{worker_id}] 启动 Chrome...")

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2
    }
    options.add_experimental_option("prefs", prefs)
    options.page_load_strategy = 'eager'

    base_dir = r"D:\Login_dataset\SeleniumUserData"
    user_data_dir = f"{base_dir}_{worker_id}"
    if not os.path.exists(user_data_dir): os.makedirs(user_data_dir)
    options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = None
    output_file = f"tmall_data_thread_{worker_id}.csv"
    product_title = "未知商品"

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 8)

        print(f"[线程-{worker_id}] 打开网页: {target_url}")
        driver.get(target_url)

        try:
            product_title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        except:
            product_title = driver.title

        # 进入评论区
        try:
            driver.execute_script("window.scrollBy(0, 400);")
            nav_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='用户评价']")))
            driver.execute_script("arguments[0].click();", nav_tab)
            time.sleep(0.5)
        except:
            pass

        try:
            view_all_btn = driver.find_element(By.XPATH, "//*[contains(text(), '查看全部评价')]")
            driver.execute_script("arguments[0].click();", view_all_btn)
            time.sleep(1)
        except:
            pass

        # === 优化 XPath 查找范围 ===
        # 尝试找到评论区的“根节点”，如果找不到就用 driver (全文查找)
        # 这样可以避免搜索到底部的推荐商品
        root_element = driver
        try:
            # 常见的评论区容器 ID 或 Class 特征
            # 这是一个启发式查找，如果找不到特定的，就回退到 driver
            candidates = driver.find_elements(By.XPATH, "//*[contains(@class, 'rate') or contains(@id, 'review')]")
            # 找一个面积比较大的容器，或者直接用 body
            # 简单策略：如果找到了明确的容器就用容器，否则全文
            # 这里为了稳定性，我们还是主要依赖 driver，但在 XPath 上加限定
            pass
        except:
            pass

        # === 极速采集循环 ===
        comments = []
        seen_hashes = set()
        last_comment_count = 0
        stuck_count = 0

        for i in range(50):
            # 优化查找范围：使用 driver.find_elements
            # 这里的 XPath "//div" 是全文查找。
            # 如果我们能定位到 root_element，可以用 root_element.find_elements(By.XPATH, ".//div...") (注意前面的点)
            # 但考虑到兼容性，这里我们保持 "//div"，但在处理时增加日期提取

            elements = driver.find_elements(By.XPATH, "//div[string-length(text())>3]")

            for elem in elements:
                try:
                    text = elem.text
                    if len(text) < 4: continue

                    text_hash = hash(text)
                    if text_hash in seen_hashes: continue

                    if is_junk_text(text): continue

                    # === 提取日期 (新增) ===
                    # 在这里，我们不仅仅提取内容，还去父元素找日期
                    date_str = extract_date_from_context(elem)

                    seen_hashes.add(text_hash)
                    clean_text = text.strip()

                    comments.append({
                        "content": clean_text,
                        "date": date_str,  # 新增日期列
                        "source": f"Thread-{worker_id}"
                    })

                    if len(comments) >= MAX_COMMENTS:
                        raise StopIteration
                except:
                    continue

            current_count = len(comments)
            new_added = current_count - last_comment_count

            if i % 2 == 0:
                print(f"[线程-{worker_id}] 轮次 {i + 1} | 已采集: {current_count} | 新增: {new_added}")

            if elements:
                last_element = elements[-1]
                if new_added > 0:
                    stuck_count = 0
                    scrolled = scroll_internal_panel(driver, last_element)
                    if not scrolled:
                        driver.execute_script("arguments[0].scrollIntoView(false);", last_element)
                    time.sleep(random.uniform(SCROLL_PAUSE_MIN, SCROLL_PAUSE_MAX))
                else:
                    stuck_count += 1
                    print(f"[线程-{worker_id}] ⚠️ 暂无新数据 ({stuck_count}/{MAX_STUCK_COUNT})")
                    if stuck_count >= MAX_STUCK_COUNT:
                        print(f"[线程-{worker_id}] 🛑 连续无更新，提前结束。")
                        break
                    driver.execute_script("arguments[0].scrollIntoView(true);", last_element)
                    time.sleep(1.5)
            else:
                driver.execute_script("window.scrollBy(0, 300);")
                time.sleep(1)

            last_comment_count = current_count

    except StopIteration:
        print(f"[线程-{worker_id}] 🎉 采集达标，停止。")
    except Exception as e:
        if "no such window" in str(e):
            print(f"[线程-{worker_id}] 浏览器已关闭")
        else:
            print(f"[线程-{worker_id}] 异常: {e}")
            return f"Error: {e}", None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

        if comments:
            df = pd.DataFrame(comments)
            df.drop_duplicates(subset=['content'], inplace=True)
            # 导出时包含 date 列
            df.to_csv(output_file, index=False, encoding='utf-8-sig', lineterminator='\r\n')
            return output_file, product_title
        else:
            return "Error: 未采集到有效数据", None