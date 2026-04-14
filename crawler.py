import os
import time
import random
import re
import pandas as pd
import shutil
import winreg
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# ================= 配置区 =================
MAX_COMMENTS = 200
SCROLL_PAUSE_MIN = 1.5
SCROLL_PAUSE_MAX = 3.0
MAX_STUCK_COUNT = 2

BASE_DATA_DIR = r"D:\Login_dataset\SeleniumUserData"
GLOBAL_DRIVER_PATH = ChromeDriverManager().install()


def clear_chrome_cache(user_data_dir):
    """自动清理 Chrome 缓存文件夹"""
    cache_paths = [
        os.path.join(user_data_dir, "Default", "Cache"),
        os.path.join(user_data_dir, "Default", "Code Cache"),
        os.path.join(user_data_dir, "GrShaderCache")
    ]
    for path in cache_paths:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                print(f"已清理缓存: {path}")
            except Exception as e:
                print(f"清理缓存失败 {path}: {e}")

# 在启动 WebDriver 前调用
clear_chrome_cache(BASE_DATA_DIR)

def get_chrome_major_version():
    """自动从 Windows 注册表获取当前 Chrome 的大版本号"""
    try:
        # 打开 Chrome 的注册表路径
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version_str, _ = winreg.QueryValueEx(key, "version")
        # version_str 长这样："146.0.7680.165"，我们只截取第一段 "146" 并转成数字
        major_version = int(version_str.split('.')[0])
        print(f"自动检测到本地 Chrome 版本为: {major_version}")
        return major_version
    except Exception as e:
        print(f"无法自动获取 Chrome 版本，将不指定版本号。错误: {e}")
        return None

# 全局获取一次即可
CURRENT_CHROME_VERSION = get_chrome_major_version()

def get_stealth_options(user_data_path):
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
    options.page_load_strategy = 'eager'
    return options


def is_intercepted(driver):
    """精准判断是否被拦截 (增强版：加入短信验证和安全中心特征)"""
    try:
        url = driver.current_url
        # 新增 aq.taobao(安全中心), havana(统一登录), iv.taobao(身份验证)
        if any(kw in url for kw in
               ['login.taobao', 'login.tmall', 'pass.tmall', 'sec.taobao', 'punish', 'aq.taobao', 'havana',
                'iv.taobao']):
            return True

        # 新增：直接扫描页面上有没有二次验证的刺眼关键字
        if driver.find_elements(By.XPATH,
                                "//*[contains(text(), '获取验证码') or contains(text(), '安全验证') or contains(text(), '向手机')]"):
            return True

        iframes = driver.find_elements(By.XPATH, "//iframe[contains(@src, 'login') or contains(@src, 'sec.taobao')]")
        for iframe in iframes:
            if iframe.is_displayed(): return True

        dialogs = driver.find_elements(By.ID, "nc_1_wrapper") + \
                  driver.find_elements(By.ID, "baxia-dialog-content") + \
                  driver.find_elements(By.CLASS_NAME, "sufei-dialog")
        for dialog in dialogs:
            if dialog.is_displayed(): return True
    except Exception:
        pass
    return False


def wait_for_user_action(driver, worker_name):
    """发现拦截就卡住，等你扫码完或点掉白框自动继续"""
    time.sleep(2)
    if is_intercepted(driver):
        print(f"\n [{worker_name}] 触发拦截！请手动扫码或点掉白框...")
        while is_intercepted(driver):
            time.sleep(2)
        print(f" [{worker_name}] 拦截解除！等待页面自然加载...")
        time.sleep(4)  # 绝不强行刷新，给足跳转时间

# 筛除非法评论逻辑
def is_junk_text(text):
    if not text: return True
    text = text.strip()
    if len(text) < 4: return True
    if len(text) < 25 and re.search(r'\d{4}[-年]\d{1,2}[-月]\d{1,2}', text): return True
    if text.startswith("【") or text.startswith("["): return True
    if re.search(r'红包\d{1,2}:\d{2}', text): return True
    if re.search(r'\d+元红包', text): return True

    # === 新增：防隐私泄露、验证页面与登录页面特征词 ===
    security_keywords = [
        # 验证码/安全验证场景
        "登录验证", "手机验证码", "本人操作", "手机不可用", "其他验证方式",
        "获取短信校验码", "手机号码", "校验码", "我的淘宝", "帮助提建议",
        "安全验证", "向手机", "身份验证", "滑块", "拼图", "获取验证码",
        # 新增：账号密码登录界面特征词
        "密码登录", "短信登录", "账号登录", "忘记密码", "免费注册",
        "请输入密码", "请输入账号", "记住密码", "密码错误", "找回密码", "扫码登录"
    ]
    for k in security_keywords:
        if k in text: return True

    # === 新增：正则精准狙击各类隐私/账号信息 ===
    # 1. 匹配脱敏手机号 (如 133****1234，涵盖所有号段)
    if re.search(r'\d{3}\*{4,6}\d{2,4}', text): return True

    # 2. 新增：匹配完整的未脱敏 11 位手机号 (1开头，第二位3-9，后9位为任意数字)
    if re.search(r'1[3-9]\d{9}', text): return True

    # 3. 匹配脱敏账号/邮箱 (如 c******n, a***@b.com)
    if re.search(r'\w\*{3,6}\w', text): return True

    # 4. 新增：匹配完整的常见邮箱格式 (防止用户把邮箱当账号暴露)
    if re.search(r'[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+', text): return True
    # ========================================

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
    except Exception:
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
    except Exception:
        pass
    return ""


# === 搜索函数 ===
# === 搜索函数 ===
# === 优化后的搜索函数 ===
# === 搜索函数 (直达链接 + 安全加载模式) ===
# *** 核心修正：为搜索模块定制的 options (坚决不用 eager) ***
def get_search_stealth_options(user_data_path):
    options = webdriver.ChromeOptions()
    # 基础伪装与全局一致
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument(fr"--user-data-dir={user_data_path}")
    options.add_argument("--start-maximized")

    # 禁用图片和样式表 speed up (搜索模块可以禁用)
    prefs = {"profile.managed_default_content_settings.images": 2,
             "profile.managed_default_content_settings.stylesheets": 2}
    options.add_experimental_option("prefs", prefs)

    # * CRITICAL CHANGE: 为搜索模块使用 normal 模式，耐心等待反爬脚本完整运行
    options.page_load_strategy = 'normal'  # 强制等待全页加载完

    return options


# === 搜索函数 (原生 Selenium + 滚动加载 + 排除本品 ID) ===
def get_search_links(keyword, count=3, exclude_id=None):
    options = get_stealth_options(f"{BASE_DATA_DIR}_Search")
    driver = None
    links = []

    try:
        driver = webdriver.Chrome(service=Service(GLOBAL_DRIVER_PATH), options=options)

        # 注入 CDP 代码抹除 webdriver 特征，防止搜索页直接出滑块
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

        driver.get(f"https://s.taobao.com/search?q={keyword}")
        time.sleep(random.uniform(3.0, 5.0))

        wait_for_user_action(driver, "Search模块")

        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'item.htm')]")))
        except:
            time.sleep(2)

        # =========================
        # === 核心：滚动加载与提取 ===
        # =========================
        try:
            # 模拟向下滚动，加载更多商品
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(random.uniform(2.0, 3.0))
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(random.uniform(1.0, 2.0))

            elements = driver.find_elements(By.XPATH, "//a[@href]")
            seen_ids = set()

            for elem in elements:
                try:
                    url = elem.get_attribute("href")
                    if not url: continue
                    # 过滤广告链接
                    if "click.taobao" in url or "simba" in url or "alimama" in url: continue

                    if "id=" in url and ("item.htm" in url or "detail" in url):
                        # 精准提取 ID
                        match = re.search(r'[?&]id=(\d+)', url)
                        if match:
                            item_id = match.group(1)

                            # 防重复：如果是本品 ID，跳过
                            if exclude_id and item_id == str(exclude_id):
                                print(f"已跳过本品链接: {item_id}")
                                continue

                            # 去重：确保抓到的是不同的商品
                            if item_id not in seen_ids:
                                seen_ids.add(item_id)
                                if not url.startswith("http"): url = "https:" + url
                                links.append(url)

                    if len(links) >= count: break
                except Exception:
                    continue

        except Exception as extract_e:
            print(f"提取链接时发生异常: {extract_e}")

    except Exception as e:
        print(f"搜索出错: {e}")
        return []
    finally:
        if driver: driver.quit()

    return links


def get_spider_stealth_options(user_data_path):
    """原生 Selenium 专用伪装配置"""
    options = webdriver.ChromeOptions()
    # 基础反检测参数
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # 独立的用户数据目录（必须保证每个线程文件夹不同，否则启动会报错）
    options.add_argument(fr"--user-data-dir={user_data_path}")
    options.add_argument("--start-maximized")

    # 禁用图片和CSS以提速（可选）
    prefs = {"profile.managed_default_content_settings.images": 2,
             "profile.managed_default_content_settings.stylesheets": 2}
    options.add_experimental_option("prefs", prefs)

    options.page_load_strategy = 'eager'
    return options


# === 核心爬虫 ===
# === 核心爬虫 (加入多线程错峰与拟人延迟) ===
def run_spider(target_url, worker_id=1):
    options = get_spider_stealth_options(f"{BASE_DATA_DIR}_{worker_id}")
    driver = None
    output_file = f"tmall_data_thread_{worker_id}.csv"
    product_title = "未知商品"
    comments = []
    sales_volume = 0

    try:
        # === 1. 核心防御：错峰启动机制 ===
        # 根据 worker_id 强行错开每个线程的启动时间 (例如线程1等2秒，线程2等4秒，线程3等6秒)
        # 绝不让三个浏览器在同一秒钟砸向淘宝服务器
        stagger_time = (worker_id - 1) * random.uniform(12.0, 15.0) + random.uniform(6.0, 10.0)
        print(f"[{worker_id}] 为了避开并发检测，正在进行深度错峰等待 {stagger_time:.1f} 秒...")
        time.sleep(stagger_time)

        # 初始化原生 Driver
        driver = webdriver.Chrome(service=Service(GLOBAL_DRIVER_PATH), options=options)

        # --- 关键：注入 CDP 代码抹除 webdriver 特征 ---
        # 原生 Selenium 如果不加这一段，淘宝的脚本一眼就能看出你是机器人
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        })
                    """
        })

        wait = WebDriverWait(driver, 15)  # 原生 Selenium 建议 Wait 时间长一点
        driver.get(target_url)

        # 2. 初始进入商品详情页，拉长等待时间，让环境监测脚本跑完
        time.sleep(random.uniform(3.5, 5.5))

        wait_for_user_action(driver, f"线程-{worker_id}")

        try:
            product_title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        except Exception:
            product_title = driver.title

        try:
            sales_element = driver.find_element(By.XPATH, "//*[contains(text(), '月销') or contains(text(), '已售')]")
            sales_text = sales_element.text
            sales_match = re.search(r'(\d+)', sales_text.replace(',', ''))
            if sales_match:
                sales_volume = int(sales_match.group(1))
                if '万' in sales_text: sales_volume *= 10000
        except Exception:
            pass

        try:
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(random.uniform(0.5, 1.5)) # 滑动后微停顿
            nav_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='用户评价']")))
            driver.execute_script("arguments[0].click();", nav_tab)
            # 3. 点击“用户评价”后，拉长数据加载缓冲时间
            time.sleep(random.uniform(2.0, 3.5))
        except Exception:
            pass

        try:
            view_all_btn = driver.find_element(By.XPATH, "//*[contains(text(), '查看全部评价')]")
            driver.execute_script("arguments[0].click();", view_all_btn)
            time.sleep(random.uniform(1.5, 2.5))
        except Exception:
            pass

        # === 切换为时间排序 ===
        try:
            try:
                default_sort_btn = driver.find_element(By.XPATH, "//*[text()='默认排序']")
                driver.execute_script("arguments[0].click();", default_sort_btn)
                time.sleep(random.uniform(1.0, 2.0))
            except Exception:
                pass

            time_sort_btn = driver.find_element(By.XPATH, "//*[text()='时间排序']")
            driver.execute_script("arguments[0].click();", time_sort_btn)
            # 4. 排序切换会触发后端重新请求数据，必须多等
            time.sleep(random.uniform(2.5, 4.0))
        except Exception:
            pass

        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            no_comment_flags = [
                "默认好评", "暂无评价", "帮助不大的评价", "还没有人评价",
                "评价方未及时做出评价", "暂时还没有评价"
            ]

            if any(flag in page_text for flag in no_comment_flags):
                empty_elements = driver.find_elements(By.XPATH,
                                                      "//*[contains(text(), '暂时还没有评价') or contains(text(), '暂无评价') or contains(text(), '还没有人评价')]")

                for el in empty_elements:
                    if el.is_displayed():
                        return "Error: 抓取终止：该商品暂时没有任何评价数据。", product_title, sales_volume

                quick_elements = driver.find_elements(By.XPATH, "//div[string-length(text())>4]")
                valid_count = 0
                for el in quick_elements:
                    t = el.text.strip()
                    if not is_junk_text(t) and (
                            "，" in t or "。" in t or "！" in t or "？" in t or "～" in t or len(t) > 12):
                        valid_count += 1

                if valid_count == 0:
                    return "Error: 抓取终止：页面未发现真实有效的文本评论。", product_title, sales_volume
        except Exception:
            pass

        seen_hashes = set()
        last_comment_count = 0
        stuck_count = 0

        for i in range(5):
            if is_intercepted(driver):
                print(f"[{worker_id}] 抓取中途遭遇拦截！暂停提取，请先处理...")
                wait_for_user_action(driver, f"线程-{worker_id}-循环抓取拦截")
                continue

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
                    if len(comments) >= MAX_COMMENTS:
                        raise StopIteration

                except StopIteration:
                    raise
                except Exception:
                    continue

            current_count = len(comments)
            new_added = current_count - last_comment_count

            if elements:
                if new_added > 0:
                    stuck_count = 0
                else:
                    stuck_count += 1
                    if stuck_count >= MAX_STUCK_COUNT: break

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
                # 5. 这里真正使用了你配置区的安全滑动等待时间
                time.sleep(random.uniform(SCROLL_PAUSE_MIN, SCROLL_PAUSE_MAX))
            else:
                driver.execute_script("window.scrollBy(0, 300);")
                time.sleep(random.uniform(SCROLL_PAUSE_MIN, SCROLL_PAUSE_MAX))
            last_comment_count = current_count

    except StopIteration:
        pass
    except Exception as e:
        return f"Error: {e}", None, 0
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    if comments:
        df = pd.DataFrame(comments).drop_duplicates(subset=['content'])
        df.to_csv(output_file, index=False, encoding='utf-8-sig', lineterminator='\r\n')
        return output_file, product_title, sales_volume
    return "Error: 未采集到有效数据", None, 0