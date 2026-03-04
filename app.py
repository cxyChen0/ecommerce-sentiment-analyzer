import os
import time
import re
import datetime
import streamlit as st
import pandas as pd
import concurrent.futures
from dotenv import load_dotenv
import db_manager
from urllib.parse import urlparse, parse_qs
import jieba
import platform
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import json

# 引入后端函数
from crawler import run_spider, get_search_links
# 引入新的流式函数
from analysis import (
    analyze_single_product_stream,
    analyze_market_trends_stream,
    analyze_competitor_comparison_stream
)

load_dotenv()
db_manager.init_stats_db()
default_key_from_env = os.getenv("ALIYUN_API_KEY")

st.set_page_config(page_title="基于AI的电商平台客户购买体验分析系统", page_icon="🛒", layout="wide")
db_manager.init_db()

# === CSS 样式注入：隐藏不需要的界面元素 ===
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display: none;}
    .block-container { padding-top: 2rem; }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ==========================================
# === 用户认证与额度管理系统 ===
# ==========================================
today_str = datetime.date.today().strftime("%Y-%m-%d")


# 初始化默认用户数据库（加入额度统计字段）
def get_new_user_template(password, role):
    return {
        'password': password,
        'role': role,
        'last_date': today_str,
        'spider_count': 0,
        'ai_count': 0,
        'dl_count': 0
    }

# 初始化状态
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'main'  # 默认显示分析主界面
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'auth_page' not in st.session_state: st.session_state.auth_page = 'login'
if 'users_db' not in st.session_state:
    st.session_state.users_db = {
        'admin': get_new_user_template('admin123', '管理员')
    }
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'current_user_id' not in st.session_state: st.session_state.current_user_id = None
if 'current_role' not in st.session_state: st.session_state.current_role = None
if 'product_id' not in st.session_state: st.session_state.product_id = ""

def switch_page(page_name):
    st.session_state.auth_page = page_name
    st.rerun()


# --- 登录界面拦截 ---
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.session_state.auth_page == 'login':
            st.title("🔐 系统登录")
            login_user = st.text_input("用户名", value="admin")
            login_pwd = st.text_input("密码", value="admin123", type="password")

            if st.button("登录", type="primary", use_container_width=True):
                # 接收三个返回值：成功标志, user_id, 角色
                success, user_id, role = db_manager.verify_login(login_user, login_pwd)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.current_user = login_user
                    st.session_state.current_user_id = user_id  # 【新增存储 ID】
                    st.session_state.current_role = role
                    st.success("登录成功！")
                    st.rerun()
                else:
                    st.error("用户名或密码错误！")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("注册账号", use_container_width=True): switch_page('register')
            with c2:
                if st.button("修改密码", use_container_width=True): switch_page('reset_pwd')

        elif st.session_state.auth_page == 'register':
            st.title("📝 注册账号")
            reg_user = st.text_input("用户名")
            reg_pwd = st.text_input("密码", type="password")
            reg_pwd2 = st.text_input("确认密码", type="password")
            reg_role = st.selectbox("选择角色", ["商家", "客户"])

            if st.button("提交注册", type="primary", use_container_width=True):
                if not reg_user or not reg_pwd:
                    st.warning("请填写完整信息！")
                elif reg_pwd != reg_pwd2:
                    st.error("两次输入密码不一致！")
                else:
                    # 【修改点】写入数据库
                    success, msg = db_manager.register_user(reg_user, reg_pwd, reg_role)
                    if success:
                        st.success("注册成功，请返回登录！")
                    else:
                        st.error(msg)

            if st.button("返回登录", use_container_width=True): switch_page('login')

        elif st.session_state.auth_page == 'reset_pwd':
            st.title("🔄 修改密码")
            reset_user = st.text_input("用户名")
            reset_pwd = st.text_input("新密码", type="password")
            reset_pwd2 = st.text_input("确认新密码", type="password")

            if st.button("确认修改", type="primary", use_container_width=True):
                if reset_pwd != reset_pwd2:
                    st.error("两次输入密码不一致！")
                else:
                    # 【修改点】更新数据库
                    success, msg = db_manager.update_password(reset_user, reset_pwd)
                    if success:
                        st.success("密码修改成功，请返回登录！")
                    else:
                        st.error(msg)

            if st.button("返回登录", use_container_width=True): switch_page('login')

    st.stop()
# ==========================================

# --- 登录后的额度刷新逻辑 ---
user_data = db_manager.get_user_data_and_check_reset(st.session_state.current_user_id)

role = user_data['role']
spider_cnt = user_data['spider_count']
ai_cnt = user_data['ai_count']
dl_cnt = user_data['dl_count']

# === 侧边栏 ===
with st.sidebar:
    st.info(f"👤 当前用户: {st.session_state.current_user} | 角色: {role}")

    # 额度展示面板
    if role == '客户':
        st.markdown(f"**今日额度 (3次/日):**\n- 🕷️ 爬虫: {spider_cnt}/3\n- 🧠 AI: {ai_cnt}/3\n- 📥 下载: {dl_cnt}/3")
    elif role == '商家':
        st.markdown(f"**今日免费额度 (10次/日):**\n- 🕷️ 爬虫: {spider_cnt}/10\n- 🧠 AI: {ai_cnt}/10")

    if st.button("🚪 退出登录"):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown("---")

    # ==========================================
    # === 【历史记录入口按钮】 ===
    if role in ['商家', '管理员']:
        st.header("📈 历史数据")
        # 根据当前页面，动态改变按钮文字
        btn_label = "🏠 返回分析大厅" if st.session_state.current_page == 'history' else "📊 查看历史记录"

        if st.button(btn_label, use_container_width=True, type="primary"):
            # 切换状态并刷新页面
            st.session_state.current_page = 'history' if st.session_state.current_page == 'main' else 'main'
            st.rerun()

    st.markdown("---")
    st.header("⚙️ 智能配置")

    # --- 2. API Key 隔离逻辑 ---
    user_api_key = default_key_from_env
    if role == '客户':
        st.success("✅ 正在使用系统默认 API Key")
    elif role == '商家':
        if ai_cnt >= 10:
            st.warning("⚠️ 今日免费额度已用尽，需配置自有 Key")
            user_api_key = st.text_input("API Key", value="", type="password", placeholder="请输入您的 API Key")
        else:
            st.success("✅ 正在使用系统自带的免费 API Key")
            st.caption("提示：也可提前配置您自己的 API Key 解除限制")
            custom_key = st.text_input("自定义 API Key (选填)", value="", type="password")
            if custom_key: user_api_key = custom_key
    elif role == '管理员':
        st.success("✅ 管理员无限畅享")
        user_api_key = default_key_from_env or st.text_input("系统 API Key 兜底", type="password")

    st.markdown("---")

    # --- 3. 模型选择 ---
    st.header("🧠 AI 模型选择")
    selected_model = st.selectbox(
        "选择分析模型",
        (
            "deepseek-v3.2-exp",
            "deepseek-r1-0528",
            "qwen3-vl-32b-thinking",
            "qwen-max",
            "doubao-seed-1-6-flash-250828",
            "doubao-seed-2-0-mini-260215",
        ),
        index=0
    )

    st.markdown("---")
    if st.button("🗑️ 清空当前页面记录"):
        keys_to_keep = ['logged_in', 'auth_page', 'users_db', 'current_user', 'current_role']
        for k in list(st.session_state.keys()):
            if k not in keys_to_keep:
                del st.session_state[k]
        st.rerun()

# ==========================================
# === 独立页面：历史记录看板 ===
# ==========================================
if st.session_state.current_page == 'history':
    st.title("📈 商家历史数据看板")

    import db_manager

    history_products = db_manager.get_merchant_products(st.session_state.current_user_id)

    if not history_products:
        st.info("📭 暂无历史记录。请先在分析大厅抓取单品数据，AI 分析后会自动保存。")
    else:
        selected_item = st.selectbox(
            "📌 选择要查阅的商品",
            history_products,
            # format_func 决定了下拉框里展示什么字：显示"标题 (ID: xxx)"
            format_func=lambda x: f"{x[1]} (ID: {x[0]})"
        )

        if selected_item:
            product_id = selected_item[0]
            trend_df = db_manager.get_product_trend(st.session_state.current_user_id, product_id)

            if not trend_df.empty:
                st.markdown("---")
                trend_df.set_index('日期', inplace=True)

                trend_df_sorted = trend_df.sort_index()  # 确保日期按时间正序排列
                if len(trend_df_sorted) >= 2:  # 至少要有两条数据才能算增长率
                    curr_sales = trend_df_sorted['销量'].iloc[-1]
                    prev_sales = trend_df_sorted['销量'].iloc[-2]

                    if prev_sales > 0:
                        growth_rate = ((curr_sales - prev_sales) / prev_sales) * 100
                        st.subheader("📊 销量核心指标监控")
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            st.metric(label="最新记录销量", value=f"{curr_sales} 单", delta=f"{growth_rate:.2f}%")

                        # 触发预警逻辑
                        if growth_rate < 10.0:
                            st.warning(
                                f"⚠️ **销量增长预警！** 最近一期销量较上期增长仅为 {growth_rate:.2f}%，低于 10% 阈值！",
                                icon="🚨")
                        else:
                            st.success(f"📈 销量增长健康！近期增长率为 {growth_rate:.2f}%。", icon="✅")
                        st.markdown("---")

                # 1. 宽幅折线图展示区
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("📅 历史销量走势")
                    st.line_chart(trend_df[['销量']], use_container_width=True)
                with col2:
                    st.subheader("⭐ 预估好评率走势 (%)")
                    st.line_chart(trend_df[['预估好评率']], color="#FF4B4B", use_container_width=True)

                # 2. 原始数据表格展示区
                st.markdown("### 📝 详细数据明细")
                # 把日期索引重置回来，方便表格展示
                display_df = trend_df.reset_index()
                st.dataframe(display_df, use_container_width=True)

                # 3. 下载历史数据按钮
                st.download_button(
                    label="📥 下载该商品历史记录 (.csv)",
                    data=display_df.to_csv(index=False).encode('utf-8-sig'),
                    file_name=f"{selected_item}_history.csv",
                    mime='text/csv'
                )

    # 执行到这里直接停止，不再向下渲染“分析大厅”的代码
    st.stop()

st.title("🛒 基于AI的电商平台客户购买体验分析系统")

# 初始化状态
for key in ['last_query', 'product_info', 'report_single_model', 'report_market_model', 'report_comp_model']:
    if key not in st.session_state: st.session_state[key] = ""
if 'df_result' not in st.session_state: st.session_state.df_result = None
if 'analysis_type' not in st.session_state: st.session_state.analysis_type = None
if 'comp_comments' not in st.session_state: st.session_state.comp_comments = []
for key in ['report_single', 'report_market', 'report_comp']:
    if key not in st.session_state: st.session_state[key] = None
if 'processing_comp' not in st.session_state: st.session_state.processing_comp = False

# ================= 权限校验函数 =================
def can_use_spider():
    if role == '管理员': return True
    if role == '客户' and spider_cnt >= 3: return False
    if role == '商家' and spider_cnt >= 10 and not user_api_key: return False
    return True


def can_use_ai():
    if role == '管理员': return True
    if role == '客户' and ai_cnt >= 3: return False
    if role == '商家' and ai_cnt >= 10 and not user_api_key: return False
    return True


def can_download():
    if role == '管理员' or role == '商家': return True
    if role == '客户' and dl_cnt >= 3: return False
    return True


def inc_spider():
    db_manager.increment_quota(st.session_state.current_user_id, 'spider_count')
def inc_ai():
    db_manager.increment_quota(st.session_state.current_user_id, 'ai_count')
def inc_dl():
    db_manager.increment_quota(st.session_state.current_user_id, 'dl_count')

# ===============================================

st.markdown("### 🔍 智能搜索")
col_input, col_btn = st.columns([5, 1], vertical_alignment="bottom")

with col_input:
    user_input = st.text_input("输入框", placeholder="👉 粘贴天猫/淘宝链接 或 输入关键词...",
                               label_visibility="collapsed")

with col_btn:
    start_analysis = st.button("🚀 立即分析", type="primary", use_container_width=True, disabled=not can_use_spider())


def is_url(text):
    return re.search(r'(http|https|tmall\.com|taobao\.com)', text)

# 从链接中提取真实商品 ID
def extract_product_id(url):
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if 'id' in params:
            return params['id'][0] # 返回真实 ID
    except:
        pass
    return "未知ID"


import json  # 确保顶部引入了 json


def generate_wordcloud_image(word_freq_dict):
    """直接接收 AI 提取的词频字典画图，抛弃原始的 jieba 分词"""

    sys_type = platform.system()
    if sys_type == "Windows":
        font_path = "C:/Windows/Fonts/simhei.ttf"  # 黑体
    elif sys_type == "Darwin":
        font_path = "/System/Library/Fonts/PingFang.ttc"
    else:
        font_path = None

    # 核心改变：不再使用 generate(text)，而是使用 generate_from_frequencies(dict)
    wc = WordCloud(
        font_path=font_path,
        width=800, height=400,
        background_color='white',
        colormap='magma',
        max_words=80
    ).generate_from_frequencies(word_freq_dict)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    plt.margins(0, 0)

    return fig

trigger_search = start_analysis or (user_input and user_input != st.session_state.last_query)

if trigger_search:
    if not can_use_spider():
        st.error("❌ 您今日的抓取额度已耗尽，或需要提供自己的 API Key！")
    else:
        st.session_state.last_query = user_input
        st.session_state.df_result = None
        st.session_state.comp_comments = []
        for k in ['report_single', 'report_market', 'report_comp']: st.session_state[k] = None
        st.session_state.processing_comp = False

        inc_spider()  # 扣除抓取次数

        # 1. 适配爬虫的新返回值 (增加 sales_volume)
        if is_url(user_input):
            # 基于 ID 判断的拦截逻辑
            extracted_id = extract_product_id(user_input)
            if extracted_id == "未知ID":
                st.error(
                    "❌ 格式错误：未在链接中检测到商品 ID。您上传的可能是搜索聚合页或无效链接，请点击进入具体商品详情页后再复制！")
                st.stop()  # 瞬间终止程序
            st.session_state.analysis_type = 'single'
            st.session_state.product_id = extract_product_id(user_input)
            with st.spinner('🕷️ 正在爬取商品数据与销量...'):
                res, title, sales_volume = run_spider(user_input, worker_id=1)

            if "Error" in res:
                st.error(res)
            else:
                st.session_state.product_info = title
                st.session_state.current_sales = sales_volume  # 暂存销量

                # ===============================================
                # === 【全局源头清洗】：读取后立刻干掉无日期的数据 ===
                # ===============================================
                raw_df = pd.read_csv(res, encoding='utf-8-sig')
                if 'date' in raw_df.columns:
                    # 强转小写并去空格，精准识别 nan 和 none
                    raw_df['date_clean'] = raw_df['date'].astype(str).str.strip().str.lower()
                    # 剔除这些空数据
                    clean_df = raw_df[~raw_df['date_clean'].isin(['nan', 'none', '', 'nat', 'null'])]
                    # 删掉辅助列，保持纯净
                    clean_df = clean_df.drop(columns=['date_clean'])
                else:
                    clean_df = raw_df

                if clean_df.empty:
                    st.error("❌ 抓取终止：清洗后未发现包含有效日期的真实评论！")
                    st.stop()

                st.session_state.df_result = clean_df
                # ===============================================

                st.success(f"抓取成功！有效评论数: {len(clean_df)} | 当前销量: {sales_volume}")
        else:
            st.session_state.analysis_type = 'market'
            with st.spinner('🕵️‍♂️ 正在搜索市场热销竞品...'):
                links = get_search_links(user_input, count=3)

            if links:
                all_cmts = []
                st.session_state.product_info = f"全网调研：{user_input}"
                with st.spinner('🚀 多线程采集竞品数据中...'):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [executor.submit(run_spider, link, i + 1) for i, link in enumerate(links)]
                        for f in concurrent.futures.as_completed(futures):
                            res, title = f.result()
                            if res and "Error" not in res:
                                try:
                                    t_df = pd.read_csv(res, encoding='utf-8-sig')
                                    if 'content' in t_df.columns: all_cmts.extend(t_df['content'].tolist())
                                except:
                                    pass
                if all_cmts:
                    st.session_state.df_result = pd.DataFrame({'content': all_cmts})
                    st.success(f"调研完成，共采集 {len(all_cmts)} 条市场评论")
            else:
                st.error("未找到相关商品")

# === 展示与分析区 ===
if st.session_state.df_result is not None:
    df = st.session_state.df_result
    st.markdown("---")

    is_single = (st.session_state.analysis_type == 'single')
    if is_single:
        st.subheader(f"📦 本品数据：{st.session_state.product_info}")
    else:
        st.subheader(f"📊 市场调研数据：{st.session_state.product_info}")

    with st.expander("📝 查看原始数据 & 下载", expanded=False):
        st.dataframe(df, use_container_width=True)
        st.download_button(
            label="📥 下载当前分析数据 (.csv)",
            data=df.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"data_{int(time.time())}.csv",
            mime='text/csv',
            disabled=not can_download(),
            on_click=inc_dl  # 下载后触发次数累加
        )

    rpt_key = 'report_single' if is_single else 'report_market'
    mod_key = 'report_single_model' if is_single else 'report_market_model'
    saved_rpt = st.session_state[rpt_key]
    saved_mod = st.session_state[mod_key]

    st.markdown("### 🧠 深度分析报告")

    if saved_rpt:
        st.info(f"当前展示的是 **{saved_mod}** 生成的报告")

        # 1. 抹除用于画词云的 JSON 代码块
        clean_report = re.sub(r'```json\s*\{.*?"wordcloud".*?\}\s*```', '', saved_rpt, flags=re.DOTALL)

        # ===============================================
        # === 【终极版：兼容所有模型的 AI 思考折叠器】 ===
        # ===============================================
        think_content = ""

        # 策略 1：寻找标准的 <think> 标签 (DeepSeek 等原生支持)
        think_match = re.search(r'<think>(.*?)</think>', clean_report, flags=re.DOTALL | re.IGNORECASE)

        if think_match:
            think_content = think_match.group(1).strip()
            # 从正文中剔除
            clean_report = re.sub(r'<think>.*?</think>\n*', '', clean_report, flags=re.DOTALL | re.IGNORECASE)
        else:
            # 策略 2：兼容豆包等模型的自定义前缀文本
            # 匹配逻辑：从 "🧠" 开始，一直抓取，直到遇到正式报告的标题（通常是换行后的 # 或 **）
            alt_match = re.search(r'(🧠.*?)(?=\n#|\n---)', clean_report, flags=re.DOTALL)
            if alt_match:
                think_content = alt_match.group(1).strip()
                # 从正文中精确剔除这段思考文本
                clean_report = clean_report.replace(alt_match.group(0), "").strip()

        # 如果成功抓到了思考内容，就把它装进折叠面板
        if think_content:
            with st.expander("🤔 查看 AI 深度思考逻辑", expanded=False):
                st.caption("以下是 AI 总结报告前的数据梳理与推演过程：")
                st.markdown(think_content)
        # ===============================================

        # 2. 展示极其干净的报告干货
        st.markdown(clean_report.strip())

        # ===============================================
        # 从 session 的报告中解析 AI 词云字典并画图
        # ===============================================
        if is_single and st.session_state.df_result is not None:
            st.markdown("---")
            st.markdown("### ☁️ AI 提纯核心情感词云")
            st.caption("基于 AI 深度理解提取的产品特征与情感关键词，告别无意义口语词。")
            with st.spinner("正在绘制词云图..."):
                try:
                    # 使用正则提取出报告里的 JSON 字典
                    match_json = re.search(r'```json\s*(\{.*?"wordcloud".*?\})\s*```', saved_rpt, re.DOTALL)
                    if match_json:
                        json_data = json.loads(match_json.group(1))
                        word_freq_dict = json_data.get("wordcloud", {})

                        if word_freq_dict:
                            fig = generate_wordcloud_image(word_freq_dict)
                            st.pyplot(fig)
                        else:
                            st.warning("⚠️ 词云数据为空。")
                    else:
                        st.info("📌 提示：本次 AI 报告未按格式返回词云数据，请尝试点击重新生成。")
                except Exception as e:
                    st.error(f"词云渲染解析失败: {e}")
        # ===============================================

        st.markdown("---")
        btn_text = f"🔄 切换到 {selected_model} 并重新生成" if selected_model != saved_mod else "🔄 重新生成"
        if st.button(btn_text, disabled=not can_use_ai() or st.session_state.processing_comp):
            st.session_state[rpt_key] = None
            st.rerun()

    else:
        gen_btn_text = "✨ 生成单品体验报告" if is_single else "✨ 生成市场趋势调研报告"
        if st.button(f"{gen_btn_text} ({selected_model})", type="primary", disabled=not can_use_ai()):
            if not user_api_key:
                st.error("缺少 API Key，无法调用 AI！")
            else:
                inc_ai()
                comments = df['content'].tolist()
                st.session_state[mod_key] = selected_model

                if is_single:
                    stream_gen = analyze_single_product_stream(comments, user_api_key, model=selected_model)
                    full_report = st.write_stream(stream_gen)
                    st.session_state[rpt_key] = full_report

                    # === 正则提取好评率并存入数据库 ===
                    try:
                        match = re.search(r'预估好评率.*?(\d+(?:\.\d+)?)%', full_report)
                        positive_rate = float(match.group(1)) if match else 0.0
                        sales = st.session_state.get('current_sales', 0)

                        db_manager.save_daily_stats(
                            user_id=st.session_state.current_user_id,
                            product_id=st.session_state.product_id,
                            product_name=st.session_state.product_info,
                            sales_volume=sales,
                            positive_rate=positive_rate
                        )
                        st.toast(f"✅ 数据已存档！好评率: {positive_rate}% | 销量: {sales}")
                        # 画图动作会交由上方的 saved_rpt 逻辑处理，保证刷新后也不消失
                    except Exception as e:
                        st.error(f"数据存档失败: {e}")
                else:
                    stream_gen = analyze_market_trends_stream(comments, user_api_key, model=selected_model)
                    st.session_state[rpt_key] = st.write_stream(stream_gen)

                st.rerun()

    # 只有商家或管理员，在单品分析模式下，且数据库中有数据时展示
    if is_single and st.session_state.current_role in ['商家', '管理员']:
        trend_df = db_manager.get_product_trend(st.session_state.current_user_id, st.session_state.product_id)

        if not trend_df.empty and len(trend_df) > 0:
            st.markdown("---")
            st.subheader("📈 商品历史数据趋势监控")
            trend_df.set_index('日期', inplace=True)

            trend_df_sorted = trend_df.sort_index()
            if len(trend_df_sorted) >= 2:
                curr_sales = trend_df_sorted['销量'].iloc[-1]
                prev_sales = trend_df_sorted['销量'].iloc[-2]

                if prev_sales > 0:
                    growth_rate = ((curr_sales - prev_sales) / prev_sales) * 100
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        st.metric(label="最新抓取销量", value=f"{curr_sales} 单", delta=f"{growth_rate:.2f}%")

                    if growth_rate < 10.0:
                        st.warning(f"⚠️ **销量增长预警！** 当前销量较上次记录增长率为 {growth_rate:.2f}%，低于 10% 阈值！",
                                   icon="🚨")
                    else:
                        st.success(f"📈 销量增长健康！当前增长率为 {growth_rate:.2f}%。", icon="✅")
                    st.markdown("###")  # 增加一点底部间距，让UI更好看

            col1, col2 = st.columns(2)
            with col1:
                st.caption("📅 销量走势")
                st.line_chart(trend_df[['销量']], use_container_width=True)
            with col2:
                st.caption("⭐ 好评率走势 (%)")
                st.line_chart(trend_df[['预估好评率']], color="#FF4B4B", use_container_width=True)

    # === 竞品比对区 ===
    if is_single and st.session_state.report_single:
        st.markdown("---")
        st.markdown("### ⚔️ 进阶功能：竞品比对")

        # 如果是客户，不让用这个功能
        if role == '客户':
            st.info("🔒 提示：您当前是【客户】身份。竞品多线程比对为【商家】和【管理员】专属功能。")
        else:
            has_comp_data = len(st.session_state.comp_comments) > 0

            col_act1, col_act2 = st.columns([1, 4])
            with col_act1:
                if not has_comp_data:
                    if st.button("🔍 自动抓取 3 个竞品",
                                 disabled=st.session_state.processing_comp or not can_use_spider()):
                        st.session_state.processing_comp = True
                        inc_spider()
                        st.rerun()
                else:
                    if st.button("🔄 清空重抓", disabled=st.session_state.processing_comp):
                        st.session_state.comp_comments = []
                        st.session_state.report_comp = None
                        st.rerun()
            with col_act2:
                if has_comp_data: st.success(f"✅ 已就绪：{len(st.session_state.comp_comments)} 条竞品数据")

            # 抓取逻辑
            if st.session_state.processing_comp and not has_comp_data:
                target_product = st.session_state.product_info
                with st.status("正在寻找并采集对手数据...", expanded=True) as status:
                    comp_links = get_search_links(target_product, count=3)
                    if comp_links:
                        temp_comp_comments = []


                        def task_wrapper(args):
                            link, idx = args
                            return run_spider(link, worker_id=idx + 1)


                        progress_bar = st.progress(0)
                        task_args = [(link, i) for i, link in enumerate(comp_links)]
                        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                            results = list(executor.map(task_wrapper, task_args))

                        for i, (res_file, _) in enumerate(results):
                            progress_bar.progress((i + 1) / len(comp_links))
                            if res_file and "Error" not in res_file:
                                try:
                                    c_df = pd.read_csv(res_file, encoding='utf-8-sig')
                                    # --- 竞品数据也同样清洗无日期的废话 ---
                                    if 'date' in c_df.columns:
                                        c_df['date_clean'] = c_df['date'].astype(str).str.strip().str.lower()
                                        c_df = c_df[~c_df['date_clean'].isin(['nan', 'none', '', 'nat', 'null'])]
                                    # -----------------------------------
                                    if 'content' in c_df.columns:
                                        temp_comp_comments.extend(c_df['content'].tolist())
                                except:
                                    pass

                        if len(temp_comp_comments) > 0:
                            st.session_state.comp_comments = temp_comp_comments
                            status.update(label="✅ 采集完成！", state="complete")
                        else:
                            status.update(label="❌ 采集失败", state="error")
                    else:
                        status.update(label="❌ 未找到竞品", state="error")
                st.session_state.processing_comp = False
                st.rerun()

            # 数据展示与生成报告
            if has_comp_data:
                df_comp_display = pd.DataFrame({'content': st.session_state.comp_comments, 'source': '竞品'})
                df_main_display = df.copy()
                df_main_display['source'] = '本品'
                df_all = pd.concat([df_main_display[['content', 'source']], df_comp_display[['content', 'source']]],
                                   ignore_index=True)

                with st.expander("📊 查看竞品详情 & 下载对比数据", expanded=True):
                    st.dataframe(df_comp_display.head(50), use_container_width=True, height=200)
                    st.download_button(
                        label="📥 下载完整对比数据",
                        data=df_all.to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"compare_data_{int(time.time())}.csv",
                        mime='text/csv'
                    )

                st.markdown("###")
                btn_label = "🔄 重新生成对比报告" if st.session_state.report_comp else f"⚖️ 生成竞品对比报告 ({selected_model})"
                if st.button(btn_label, type="primary", disabled=not can_use_ai() or st.session_state.processing_comp,
                             use_container_width=True):
                    inc_ai()
                    st.session_state.report_comp_model = selected_model
                    stream_gen = analyze_competitor_comparison_stream(
                        st.session_state.product_info,
                        df['content'].tolist(),
                        st.session_state.comp_comments,
                        user_api_key,
                        model=selected_model
                    )
                    st.session_state.report_comp = st.write_stream(stream_gen)
                    st.rerun()

            if st.session_state.report_comp:
                st.markdown("---")
                st.subheader("⚖️ 竞品差异化对比报告")
                st.info(f"由模型 **{st.session_state.report_comp_model}** 生成")
                st.markdown(st.session_state.report_comp)