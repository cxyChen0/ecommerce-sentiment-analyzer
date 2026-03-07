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
MAX_COMMENTS = 200
SCROLL_PAUSE_MIN = 0.5
SCROLL_PAUSE_MAX = 0.8
MAX_STUCK_COUNT = 2

# 固定盘符路径，养号基石
BASE_DATA_DIR = r"D:\Login_dataset\SeleniumUserData"


# =========================================

def get_stealth_options(user_data_path):
    """【黑科技】集中管理的隐身配置，干掉灰色自动化横幅"""
    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument(fr"--user-data-dir={user_data_path}")
    options.add_argument("--start-maximized")

    prefs = {"profile.managed_default_content_settings.images": 2,
             "profile.managed_default_content_settings.stylesheets": 2}
    options.add_experimental_option("prefs", prefs)
    # options.page_load_strategy = 'eager'
    return options


def is_intercepted(driver):
    """精准判断是否被拦截 (必须肉眼可见才算拦截，防假阳性)"""
    try:
        url = driver.current_url
        if any(kw in url for kw in ['login.taobao', 'login.tmall', 'pass.tmall', 'sec.taobao', 'punish']):
            return True

        iframes = driver.find_elements(By.XPATH,
                                       "//iframe[contains(@src, 'login.taobao') or contains(@src, 'login.tmall')]")
        for iframe in iframes:
            if iframe.is_displayed(): return True

        dialogs = driver.find_elements(By.ID, "nc_1_wrapper") + driver.find_elements(By.ID,
                                                                                     "baxia-dialog-content") + driver.find_elements(
            By.CLASS_NAME, "sufei-dialog")
        for dialog in dialogs:
            if dialog.is_displayed(): return True
    except:
        pass
    return False


def wait_for_user_action(driver, worker_name):
    """发现拦截就卡住，等你扫码完或点掉白框自动继续"""
    time.sleep(2)
    if is_intercepted(driver):
        print(f"\n⚠️ [{worker_name}] 触发拦截！请手动扫码或点掉白框...")
        while is_intercepted(driver):
            time.sleep(2)
        print(f"✅ [{worker_name}] 拦截解除！等待页面自然加载...")
        time.sleep(4)  # 绝不强行刷新，给足跳转时间


# === 过滤器、滚动条等辅助函数保持不变 ===
def is_junk_text(text):
    if not text: return True
    text = text.strip()
    if len(text) < 4: return True
    if len(text) < 25 and re.search(r'\d{4}[-年]\d{1,2}[-月]\d{1,2}', text): return True
    if "✅" in text or text.startswith("【") or text.startswith("["): return True
    if re.search(r'红包\d{1,2}:\d{2}', text): return True
    if re.search(r'\d+元红包', text): return True

    junk_keywords = [
        "已购", "颜色分类", "尺码", "规格", "款式", "此用户没有填写", "系统默认", "评价方未及时做出评价",
        "未及时主动评价", "系统默认好评", "自动好评", "用户评价", "查看全部", "浏览量", "销量", "追评",
        "人已买", "视频", "图片", "评论", "天猫", "积分", "已售", "满", "减", "立减", "为你展示", "真实评价",
        "如果不满意", "退货", "运费", "上门取件", "默认排序", "按热度", "按时间", "推荐", "问大家", "宝贝细节",
        "旗舰店", "专卖店", "月销", "库存", "发货", "付款", "折", "切换大图模式", "搜索", "搜本店", "88VIP好评率98%", "适用人群",
        "IP联名"
    ]
    for k in junk_keywords:
        if k in text: return True
    if "¥" in text or "￥" in text: return True
    if re.search(r'满\d+减\d+', text): return True
    return False


def scroll_internal_panel(driver, element):
    js_script = """
    var element = arguments[0]; var scrollable = null; var parent = element.parentElement;
    for (var i = 0; i < 15; i++) {
        if (!parent) break;
        var style = window.getComputedStyle(parent);
        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && parent.scrollHeight > parent.clientHeight) {
            scrollable = parent; break;
        }
        parent = parent.parentElement;
    }
    if (scrollable) { scrollable.scrollTop = scrollable.scrollHeight; return true; } 
    else { return false; }
    """
    try:
        return driver.execute_script(js_script, element)
    except:
        return False


def extract_date_from_context(element):
    date_pattern = r'(\d{4}[-年]\d{1,2}[-月]\d{1,2})'
    try:
        parent = element.find_element(By.XPATH, "..")
        match = re.search(date_pattern, parent.text)
        if match: return match.group(1)
        grandparent = element.find_element(By.XPATH, "../..")
        match = re.search(date_pattern, grandparent.text)
        if match: return match.group(1)
    except:
        pass
    return ""


# === 搜索函数 ===
def get_search_links(keyword, count=3):
    options = get_stealth_options(f"{BASE_DATA_DIR}_Search")
    driver = None
    links = []
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(f"https://s.taobao.com/search?q={keyword}")

        time.sleep(random.uniform(1.5, 2.5))

        wait_for_user_action(driver, "Search模块")

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
    options = get_stealth_options(f"{BASE_DATA_DIR}_{worker_id}")
    driver = None
    output_file = f"tmall_data_thread_{worker_id}.csv"
    product_title = "未知商品"
    comments = []
    sales_volume = 0

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 8)

        driver.get(target_url)

        time.sleep(random.uniform(1.5, 2.5))

        wait_for_user_action(driver, f"线程-{worker_id}")

        try:
            product_title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        except:
            product_title = driver.title

        try:
            sales_element = driver.find_element(By.XPATH, "//*[contains(text(), '月销') or contains(text(), '已售')]")
            sales_text = sales_element.text
            sales_match = re.search(r'(\d+)', sales_text.replace(',', ''))
            if sales_match:
                sales_volume = int(sales_match.group(1))
                if '万' in sales_text: sales_volume *= 10000
        except:
            pass

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

        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            no_comment_flags = ["默认好评", "暂无评价", "帮助不大的评价", "还没有人评价", "评价方未及时做出评价"]
            if any(flag in page_text for flag in no_comment_flags):
                quick_elements = driver.find_elements(By.XPATH, "//div[string-length(text())>4]")
                valid_count = sum(1 for el in quick_elements if not is_junk_text(el.text))
                if valid_count == 0:
                    return "Error: ❌ 抓取终止：暂无有效的文字评论。", product_title, sales_volume
        except:
            pass

        seen_hashes = set()
        last_comment_count = 0
        stuck_count = 0

        for i in range(50):
            elements = driver.find_elements(By.XPATH, "//div[string-length(text())>3]")
            for elem in elements:
                try:
                    text = elem.text
                    if len(text) < 4: continue
                    text_hash = hash(text)
                    if text_hash in seen_hashes: continue
                    if is_junk_text(text): continue

                    date_str = extract_date_from_context(elem)
                    seen_hashes.add(text_hash)
                    comments.append({"content": text.strip(), "date": date_str, "source": f"Thread-{worker_id}"})
                    if len(comments) >= MAX_COMMENTS: raise StopIteration
                except:
                    continue

            current_count = len(comments)
            new_added = current_count - last_comment_count

            if elements:
                if new_added > 0:
                    stuck_count = 0
                else:
                    stuck_count += 1
                    if stuck_count >= MAX_STUCK_COUNT: break
                if i >= 3: break

                scroll_script = """
                    var scrolled = false; var maxArea = 0; var targetEl = null;
                    var allElements = document.querySelectorAll('*');
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i]; var style = window.getComputedStyle(el);
                        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                            var area = el.clientWidth * el.clientHeight;
                            if (area > maxArea) { maxArea = area; targetEl = el; }
                        }
                    }
                    if (targetEl && maxArea > 20000) { targetEl.scrollTop = targetEl.scrollHeight; scrolled = true; }
                """
                driver.execute_script(scroll_script)
                time.sleep(0.5)
            else:
                driver.execute_script("window.scrollBy(0, 300);")
                time.sleep(0.5)
            last_comment_count = current_count

    except StopIteration:
        pass
    except Exception as e:
        return f"Error: {e}", None, 0
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        if comments:
            df = pd.DataFrame(comments).drop_duplicates(subset=['content'])
            df.to_csv(output_file, index=False, encoding='utf-8-sig', lineterminator='\r\n')
            return output_file, product_title, sales_volume
        return "Error: 未采集到有效数据", None, 0