import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import random
import time
from openai import OpenAI

# === 导入刚才写的爬虫脚本 ===
# 注意：real_crawler.py 必须和 main.py 在同一个文件夹内
try:
    from real_crawler import ECommerceCrawler

    HAS_CRAWLER = True
except ImportError:
    HAS_CRAWLER = False

# ==========================================
# 1. 基础配置
# ==========================================

st.set_page_config(page_title="电商客户体验分析系统", page_icon="🛍️", layout="wide")

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# AI 配置
USE_MOCK_AI = True
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = "https://api.deepseek.com"


def analyze_sentiment_with_ai(text):
    """
    调用AI进行情感分析 (DeepSeek)
    """
    if USE_MOCK_AI:
        # 演示模式：根据关键词简单判断
        time.sleep(0.1)
        keywords = ["差", "慢", "坏", "发热", "破损", "不行", "卡顿"]
        if any(k in text for k in keywords):
            return "负面", round(random.uniform(0.8, 0.99), 2)
        elif len(text) > 15:
            return "正面", round(random.uniform(0.8, 0.99), 2)
        else:
            return "中性", round(random.uniform(0.5, 0.7), 2)

    try:
        # 真实调用 DeepSeek API
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=BASE_URL)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "判断情感倾向，返回：正面、负面、或中性。"},
                {"role": "user", "content": text},
            ]
        )
        return response.choices[0].message.content.strip(), 0.95
    except:
        return "中性", 0.0


# ==========================================
# 2. 核心逻辑：连接前后端
# ==========================================

def get_real_data(url):
    """
    连接 real_crawler.py 获取真实数据，并补充AI分析结果
    """
    status_text = st.empty()
    progress_bar = st.progress(0)

    status_text.text("正在启动爬虫引擎...")

    # 1. 调用后端爬虫
    crawler = ECommerceCrawler()
    # 注意：如果 crawler.run 返回 None (比如被反爬拦截)，我们需要处理
    df_raw = crawler.run(url)
    progress_bar.progress(50)

    if df_raw is None or df_raw.empty:
        status_text.error("抓取失败！可能原因：1.Cookie过期 2.反爬拦截 3.网络超时。已自动切换回演示数据。")
        time.sleep(2)
        return fetch_mock_data(url)  # 失败时回退到模拟数据

    status_text.text(f"成功抓取 {len(df_raw)} 条评论，正在进行 AI 情感分析...")

    # 2. 对抓取到的每一条评论进行 AI 分析
    analyzed_data = []
    total = len(df_raw)
    for index, row in df_raw.iterrows():
        sentiment, conf = analyze_sentiment_with_ai(row['content'])
        analyzed_data.append({
            "content": row['content'],
            "date": row['date'],
            "sentiment": sentiment,
            "confidence": conf
        })
        # 更新进度条
        current_progress = 50 + int((index / total) * 50)
        progress_bar.progress(min(current_progress, 100))

    df_comments = pd.DataFrame(analyzed_data)

    # 3. 补充销量数据
    # (注：单次爬取很难获得历史销量曲线，这里通常需要用模拟数据来填补图表)
    df_sales = generate_mock_sales_data()

    status_text.success("分析完成！")
    time.sleep(1)
    status_text.empty()
    progress_bar.empty()

    return df_sales, df_comments


def fetch_mock_data(url):
    """
    (原有的) 模拟数据生成函数，用于演示或爬虫失败时的兜底
    """
    # ... 保留原有的模拟逻辑以便演示 ...
    # 简写版：
    df_sales = generate_mock_sales_data()

    comments_pool = [
        ("物流超级快，第二天就到了！", "正面"),
        ("质量一般般，对得起这个价格吧。", "中性"),
        ("客服态度太差了，半天不回消息。", "负面"),
        ("非常满意的一次购物，下次还来。", "正面"),
        ("电池不太耐用，发热严重。", "负面")
    ]
    fetched_comments = []
    for _ in range(20):
        text, _ = random.choice(comments_pool)
        sent, conf = analyze_sentiment_with_ai(text)
        fetched_comments.append({
            "content": text,
            "sentiment": sent,
            "confidence": conf,
            "date": (datetime.now() - timedelta(days=random.randint(0, 7))).strftime("%Y-%m-%d")
        })
    return df_sales, pd.DataFrame(fetched_comments)


def generate_mock_sales_data():
    dates = [datetime.now() - timedelta(days=i) for i in range(14)]
    dates.reverse()
    sales_data = []
    for date in dates:
        sales_data.append({"date": date.strftime("%Y-%m-%d"), "sales": random.randint(100, 300)})
    return pd.DataFrame(sales_data)


# ==========================================
# 3. Streamlit 页面
# ==========================================

with st.sidebar:
    st.title("控制面板")
    target_url = st.text_input("请输入商品链接:", value="https://detail.tmall.com/item.htm?id=XXXX")
    # 添加一个开关，允许用户选择模式
    use_real_crawler = st.checkbox("启用真实爬虫 (需配置Cookie)", value=False)
    st.info("提示：真实抓取速度较慢，且需要有效的Cookie。")

st.title("📊 基于AI的电商平台客户购买体验分析")

if st.button("🚀 开始分析", type="primary"):
    if use_real_crawler and HAS_CRAWLER:
        df_sales, df_comments = get_real_data(target_url)
    else:
        if use_real_crawler and not HAS_CRAWLER:
            st.warning("未找到 real_crawler.py 文件，已切换回模拟模式。")
        df_sales, df_comments = fetch_mock_data(target_url)

    # --- 下面是展示逻辑 (与之前相同) ---
    if not df_comments.empty:
        # 指标计算
        pos_rate = round((len(df_comments[df_comments['sentiment'] == '正面']) / len(df_comments)) * 100, 1)

        col1, col2, col3 = st.columns(3)
        col1.metric("分析评论数", len(df_comments))
        col2.metric("AI好评率", f"{pos_rate}%")
        col3.metric("数据来源", "真实抓取" if use_real_crawler else "模拟演示")

        st.markdown("---")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("📈 销量趋势 (模拟补全)")
            st.plotly_chart(px.line(df_sales, x='date', y='sales'), use_container_width=True)
        with c2:
            st.subheader("💬 情感分布")
            st.plotly_chart(px.pie(df_comments, names='sentiment', color='sentiment',
                                   color_discrete_map={'正面': '#10b981', '负面': '#ef4444', '中性': '#9ca3af'}),
                            use_container_width=True)

        st.subheader("📝 详细评论数据")
        st.dataframe(df_comments, use_container_width=True)