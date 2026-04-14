import os
import time
import random
import re
import datetime
import streamlit as st
import pandas as pd
import altair as alt
import concurrent.futures
from dotenv import load_dotenv
import db_manager
from urllib.parse import urlparse, parse_qs
import platform
from wordcloud import WordCloud
import json
import numpy as np
from streamlit_echarts import st_echarts
from streamlit_echarts import JsCode
from datetime import timedelta
from crawler import run_spider, get_search_links
from analysis import (
    analyze_single_product_stream,
    analyze_market_trends_stream,
    analyze_competitor_comparison_stream
)

load_dotenv()

default_key_from_env = os.getenv("ALIYUN_API_KEY")
st.set_page_config(page_title="基于AI的电商平台客户购买体验分析系统", page_icon="/app/static/logo4.png", layout="wide")


@st.cache_data(show_spinner=False)
def auto_tag_dimensions(df):
    """
    轻量级基于关键词的评论多维打标引擎
    """
    if df is None or df.empty:
        return df

    # 如果已经打过标，避免重复计算
    if '维度标签' in df.columns:
        return df

    # 定义四大维度核心关键词库（可根据具体品类随时扩充词库）
    keywords = {
        "产品": ["质量", "正品", "材质", "做工", "颜色", "包装", "味道", "效果", "好用", "破损", "瑕疵", "外观", "尺寸",
                 "一般", "不错"],
        "物流": ["物流", "快递", "发货", "派送", "驿站", "速度", "慢", "快", "顺丰", "运费", "收到", "送货",
                 "包装破损"],
        "价格": ["价格", "贵", "便宜", "划算", "性价比", "降价", "差价", "折扣", "优惠", "不值", "坑", "羊毛"],
        "服务": ["客服", "态度", "售后", "退款", "换货", "回复", "解决", "差评", "投诉", "骗人", "理人"]
    }

    def _tag(text):
        if not isinstance(text, str):
            return "未分类"
        tags = []
        for dim, kws in keywords.items():
            if any(kw in text for kw in kws):
                tags.append(dim)
        return "、".join(tags) if tags else "未分类"

    # 复制一份防止 SettingWithCopyWarning
    tagged_df = df.copy()
    # 应用打标逻辑
    tagged_df['维度标签'] = tagged_df['content'].apply(_tag)

    # 把标签列移到最前面，方便用户第一眼看到
    cols = ['维度标签'] + [c for c in tagged_df.columns if c != '维度标签']
    return tagged_df[cols]


# ==========================================
# 【性能优化 1】：利用单例缓存，拦截冗余的数据库建表 DDL 请求
# ==========================================
def init_system_databases():
    db_manager.init_stats_db()
    db_manager.init_db()
    db_manager.init_ecommerce_db()
    return True

init_system_databases()

def render_trend_prediction_charts(plot_df):
    """
    接收包含 ['日期', '销量', '综合CBEI指数'] 的 dataframe，
    自动计算线性预测并渲染 Echarts 双图
    """
    combined_df = plot_df.copy()
    if len(plot_df) >= 3:
        try:
            plot_df['date_obj'] = pd.to_datetime(plot_df['日期'])
            plot_df['date_num'] = plot_df['date_obj'].map(lambda x: x.toordinal())

            last_date = plot_df['date_obj'].iloc[-1]
            last_date_num = plot_df['date_num'].iloc[-1]
            last_sales = plot_df['销量'].iloc[-1]
            last_cbei = plot_df['综合CBEI指数'].iloc[-1]

            # 1. 计算长线基准斜率 (全局线性回归)
            z_sales = np.polyfit(plot_df['date_num'], plot_df['销量'], 1)
            z_rate = np.polyfit(plot_df['date_num'], plot_df['综合CBEI指数'], 1)
            base_slope_sales = z_sales[0]
            base_slope_cbei = z_rate[0]

            # 2. 计算短线动能斜率 (最近两天的瞬时变化率)
            recent_slope_sales = (last_sales - plot_df['销量'].iloc[-2]) / (
                    last_date_num - plot_df['date_num'].iloc[-2])
            recent_slope_cbei = (last_cbei - plot_df['综合CBEI指数'].iloc[-2]) / (
                    last_date_num - plot_df['date_num'].iloc[-2])

            # 3. 核心商业算法：动能加权融合
            # 赋予最新变化 70% 的权重，全局底色 30% 的权重
            weight_recent = 0.7
            weight_base = 0.3

            # 销量依然保持“熔断机制”，坚决不允许出现负增长
            final_slope_sales = max(0, (weight_base * base_slope_sales) + (
                    weight_recent * recent_slope_sales))
            # CBEI 分数融合（允许随最新反弹趋势向上）
            final_slope_cbei = (weight_base * base_slope_cbei) + (weight_recent * recent_slope_cbei)

            future_dates = [last_date + timedelta(days=i) for i in range(1, 6)]
            pred_data = []

            # 新增：设定基础振幅 (误差随时间放大)
            cbei_margin_per_day = 1.5
            sales_margin_pct_per_day = 0.002  # 销量每天增加 0.2% 的误差

            for d in future_dates:
                d_num = d.toordinal()
                days_ahead = d_num - last_date_num

                # 1. 基础预测线 (中性预期)
                pred_sales = int(last_sales + final_slope_sales * days_ahead)
                pred_cbei = last_cbei + final_slope_cbei * days_ahead

                # 2. 新增：计算销量区间 (悲观/乐观)
                sales_variance = int(pred_sales * (sales_margin_pct_per_day * days_ahead))
                sales_upper = pred_sales + sales_variance
                # 销量底线逻辑：最差的情况是销量完全停滞不动，绝不能比昨天少
                sales_lower = max(last_sales, pred_sales - sales_variance)

                # 3. 新增：计算 CBEI 区间
                cbei_variance = cbei_margin_per_day * days_ahead
                cbei_upper = min(100.0, pred_cbei + cbei_variance)
                cbei_lower = max(0.0, pred_cbei - cbei_variance)

                # 中性线限值
                pred_cbei = max(0.0, min(100.0, round(pred_cbei, 2)))

                pred_data.append({
                    '日期': d.strftime('%Y-%m-%d'),
                    '销量': pred_sales,
                    '销量_上限': sales_upper,
                    '销量_下限': sales_lower,
                    '综合CBEI指数': pred_cbei,
                    'CBEI_上限': round(cbei_upper, 2),
                    'CBEI_下限': round(cbei_lower, 2),
                    '数据类型': '预测数据'
                })

            pred_df = pd.DataFrame(pred_data)

            # 核心修复：锚点必须增加上下限字段，并与真实值相等，这样面积图才会从一个"针尖"完美展开
            connection_point = plot_df.iloc[-1:].copy()
            connection_point['数据类型'] = '预测数据'
            connection_point['销量_上限'] = connection_point['销量']
            connection_point['销量_下限'] = connection_point['销量']
            connection_point['CBEI_上限'] = connection_point['综合CBEI指数']
            connection_point['CBEI_下限'] = connection_point['综合CBEI指数']

            combined_df = pd.concat([plot_df.drop(columns=['date_obj', 'date_num']),
                                     connection_point.drop(columns=['date_obj', 'date_num']),
                                     pred_df], ignore_index=True)
        except Exception as e:
            st.warning(f"数据波动异常，暂时无法生成预测折线：{e}")

    st.markdown("### :material/area_chart:  数据走势与未来预测")
    st.caption("实线为真实历史数据；虚线为 AI 根据历史线性拟合推演的未来 5 天趋势。")

    # ==========================================
    # Echarts 绝美平滑曲线与预测扇区渲染
    # ==========================================
    col1, col2 = st.columns(2)

    # 1. 结构化处理 Echarts 需要的纯列表数据
    dates = []
    real_sales, pred_sales, sales_lower, sales_upper_diff = [], [], [], []
    real_cbei, pred_cbei, cbei_lower, cbei_upper_diff = [], [], [], []

    # 🌟 核心防御：强制将 Pandas/Numpy 类型洗白为原生 Python 类型，防止 Echarts 序列化崩溃
    def to_int(val):
        return int(val) if pd.notna(val) else None

    def to_float(val):
        return float(val) if pd.notna(val) else None

    for d in combined_df['日期'].unique():
        dates.append(str(d))  # 确保日期是纯字符串

        # 提取真实数据
        row_real = combined_df[(combined_df['日期'] == d) & (combined_df['数据类型'] == '真实数据')]
        if not row_real.empty:
            real_sales.append(to_int(row_real['销量'].iloc[0]))
            real_cbei.append(to_float(row_real['综合CBEI指数'].iloc[0]))
        else:
            real_sales.append(None)
            real_cbei.append(None)

        # 提取预测数据及区间
        row_pred = combined_df[(combined_df['日期'] == d) & (combined_df['数据类型'] == '预测数据')]
        if not row_pred.empty:
            pred_sales.append(to_int(row_pred['销量'].iloc[0]))
            pred_cbei.append(to_float(row_pred['综合CBEI指数'].iloc[0]))

            if '销量_下限' in row_pred.columns:
                l_s = to_int(row_pred['销量_下限'].iloc[0])
                u_s = to_int(row_pred['销量_上限'].iloc[0])
                sales_lower.append(l_s)
                # Echarts 区间面积必须用差值堆叠
                sales_upper_diff.append(u_s - l_s if u_s is not None and l_s is not None else None)

                l_c = to_float(row_pred['CBEI_下限'].iloc[0])
                u_c = to_float(row_pred['CBEI_上限'].iloc[0])
                cbei_lower.append(l_c)
                cbei_upper_diff.append(
                    round(u_c - l_c, 2) if u_c is not None and l_c is not None else None)
            else:
                sales_lower.append(None);
                sales_upper_diff.append(None)
                cbei_lower.append(None);
                cbei_upper_diff.append(None)
        else:
            pred_sales.append(None);
            pred_cbei.append(None)
            sales_lower.append(None);
            sales_upper_diff.append(None)
            cbei_lower.append(None);
            cbei_upper_diff.append(None)

    # 2. 封装 Echarts 配置项生成器
    def get_echarts_option(title, data_real, data_pred, data_lower, data_diff, color_real,
                           color_pred):
        return {
            # 🌟 修复 1：强制 Echarts 画布背景完全透明，完美融入你的米黄色网页背景
            "backgroundColor": "transparent",

            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross", "label": {"backgroundColor": "#6a7985"}}
            },
            # 图例放在最底部
            "legend": {"data": ["真实数据", "推演预测"], "bottom": 0,
                       "textStyle": {"color": "#475569"}},

            # 🌟 修改：把 grid 的 bottom 稍微调大一点 (18%)，给下面的缩放条留出空间
            "grid": {"left": "3%", "right": "4%", "bottom": "18%", "containLabel": True},

            # 🌟 修复 2：加入 dataZoom (数据缩放) 组件，专治数据密集！
            "dataZoom": [
                {
                    "type": "inside",  # 允许用户直接在图表上用鼠标滚轮缩放和拖拽平移
                    "start": 0,
                    "end": 100
                },
                {
                    "type": "slider",  # 在底部显示一个极简的滑动条
                    "bottom": "8%",  # 放在图例上方
                    "height": 12,
                    "borderColor": "transparent",
                    "backgroundColor": "rgba(148, 163, 184, 0.1)",
                    "fillerColor": "rgba(148, 163, 184, 0.3)",
                    "handleStyle": {"color": "#cbd5e1"},
                    "textStyle": {"color": "transparent"},  # 隐藏滑动条两端的文字，保持整洁
                    "showDetail": False  # 拖拽时不显示具体数值放大镜
                }
            ],

            "xAxis": {
                "type": "category", "boundaryGap": False, "data": dates,
                "axisLabel": {
                    "rotate": 45,
                    "color": "#94a3b8",
                    # 🌟 核心防拥挤：如果标签太多放不下，自动隐藏部分标签，保证不重叠！
                    "hideOverlap": True,
                    "interval": "auto"
                },
                "axisLine": {"lineStyle": {"color": "#cbd5e1"}}
            },
            "yAxis": {
                "type": "value", "scale": True,
                "min": 0 if title == "CBEI" else "dataMin",
                "max": 100 if title == "CBEI" else None,
                "axisLabel": {"color": "#94a3b8"},
                "splitLine": {"lineStyle": {"color": "#f1f5f9", "type": "dashed"}}
            },
            "series": [
                {
                    "name": "区间底座", "type": "line", "stack": "confidence_band",
                    "symbol": "none", "lineStyle": {"opacity": 0},
                    "smooth": True, "data": data_lower
                },
                {
                    "name": "预测置信区间", "type": "line", "stack": "confidence_band",
                    "symbol": "none", "lineStyle": {"opacity": 0},
                    "areaStyle": {"color": color_pred, "opacity": 0.15},
                    "smooth": True, "data": data_diff
                },
                {
                    "name": "真实数据", "type": "line", "smooth": True,
                    "symbolSize": 6, "itemStyle": {"color": color_real},
                    "lineStyle": {"width": 3, "shadowColor": "rgba(0,0,0,0.1)",
                                  "shadowBlur": 5},
                    "data": data_real
                },
                {
                    "name": "推演预测", "type": "line", "smooth": True,
                    "symbolSize": 6, "itemStyle": {"color": color_pred},
                    "lineStyle": {"width": 3, "type": "dashed"},
                    "data": data_pred
                }
            ]
        }

    with col1:
        st.caption(":material/trending_up: 销量走势 (含未来5天推演数据)")
        opt_sales = get_echarts_option(
            "销量", real_sales, pred_sales, sales_lower, sales_upper_diff,
            color_real="#4c78a8", color_pred="#f58518"
        )
        st_echarts(options=opt_sales, height="350px")

    with col2:
        st.caption(":material/thumb_up: 综合 CBEI 体验指数走势 (分)")
        opt_cbei = get_echarts_option(
            "CBEI", real_cbei, pred_cbei, cbei_lower, cbei_upper_diff,
            color_real="#e11d48", color_pred="#f58518"
        )
        st_echarts(options=opt_cbei, height="350px")

    return combined_df



hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display: none;}
    [data-testid="block-container"] {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }
    [data-testid="stHeader"] {
        height: 2.5rem !important;
    }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
today_str = datetime.date.today().strftime("%Y-%m-%d")
def get_new_user_template(password, role):
    return {
        'password': password,
        'role': role,
        'last_date': today_str,
        'spider_count': 0,
        'ai_count': 0,
        'dl_count': 0
    }
if 'current_page' not in st.session_state: st.session_state.current_page = 'main'
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'theme_color' not in st.session_state: st.session_state.theme_color = "#BD9A94"
if 'auth_page' not in st.session_state: st.session_state.auth_page = 'login'
if 'users_db' not in st.session_state:
    st.session_state.users_db = {
        'admin': get_new_user_template('123456', '管理员')
    }
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'current_user_id' not in st.session_state: st.session_state.current_user_id = None
if 'current_role' not in st.session_state: st.session_state.current_role = None
if 'product_id' not in st.session_state: st.session_state.product_id = ""
def switch_page(page_name):
    st.session_state.auth_page = page_name
    st.rerun()


# ==========================================================
# 缓存层：一次读取，无限次极速翻页
# ==========================================================
def load_cached_comments_with_category():
    """将原本耗时的数据库查询、表关联动作封装并缓存到内存中"""
    df_c = db_manager.get_all_ecommerce_comments()
    df_p = db_manager.get_all_ecommerce_products()

    if not df_c.empty and not df_p.empty:
        df_c['product_id'] = df_c['product_id'].astype(str)
        df_p['product_id'] = df_p['product_id'].astype(str)
        if 'category' not in df_c.columns:
            df_c = df_c.merge(df_p[['product_id', 'category']], on='product_id', how='left')
            df_c['category'] = df_c['category'].fillna('general')
    else:
        if 'category' not in df_c.columns:
            df_c['category'] = 'general'

    return df_c

# ==========================================================
# 缓存层：一次读取，无限次极速翻页 (商品元数据库专属)
# ==========================================================
def load_cached_products():
    """将商品主表的读取动作封装并缓存到内存中"""
    return db_manager.get_all_ecommerce_products()

# ==========================================================
# 缓存层：一次读取，无限次极速翻页 (历史查询记录专属)
# ==========================================================
def load_cached_stats():
    """将历史查询记录（商品追踪数据）的读取动作封装并缓存到内存中"""
    return db_manager.get_all_product_stats_admin()

# ==========================================================
# 缓存层：一次读取，无限次极速翻页 (全局用户表专属)
# ==========================================================
def load_cached_users():
    """将全局用户表的读取动作封装并缓存到内存中"""
    return db_manager.get_all_users_admin()


if not st.session_state.logged_in:

    import base64
    import os
    import streamlit.components.v1 as components

    # ======== 1. 极速引用本地静态视频 ========
    video_src = "/app/static/bg.mp4"

    # ======== 2. 注入全屏动态视频与兜底背景 ========
    video_bg_html = f"""
    <style>
    .stApp, [data-testid="stAppViewContainer"] {{
        background: transparent !important;
    }}
    [data-testid="stHeader"] {{ background-color: transparent !important; }}
    </style>
    <div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: -999; overflow: hidden; background-color: #0f172a;">
        <video autoplay loop muted playsinline style="width: 100%; height: 100%; object-fit: cover; filter: brightness(0.65) contrast(1.1);">
            <source src="{video_src}" type="video/mp4">
        </video>
    </div>
    """
    st.markdown(video_bg_html, unsafe_allow_html=True)

    # ======== 3. 终极几何美学：时钟射线 + 爆炸粒子引擎 ========
    particle_js = """
        <script>
        (function() {
            const parentWindow = window.parent;
            const parentDoc = parentWindow.document;

            if (parentDoc.getElementById('neuralCanvas')) {
                parentDoc.getElementById('neuralCanvas').remove();
            }

            const canvas = parentDoc.createElement('canvas');
            canvas.id = 'neuralCanvas';
            canvas.style.position = 'fixed';
            canvas.style.top = '0';
            canvas.style.left = '0';
            canvas.style.width = '100vw';
            canvas.style.height = '100vh';
            canvas.style.zIndex = '-500'; 
            canvas.style.pointerEvents = 'none'; 
            parentDoc.body.appendChild(canvas);

            const ctx = canvas.getContext('2d');
            let width = canvas.width = parentWindow.innerWidth;
            let height = canvas.height = parentWindow.innerHeight;
            let particles = [];

            let mouse = { x: -1000, y: -1000, radius: 280, clicked: false };

            parentDoc.addEventListener('mousemove', function(event) {
                mouse.x = event.clientX;
                mouse.y = event.clientY;
            });

            parentDoc.addEventListener('mousedown', function() {
                mouse.clicked = true;
            });
            parentDoc.addEventListener('mouseup', function() {
                mouse.clicked = false;
            });

            parentWindow.addEventListener('resize', function() {
                width = canvas.width = parentWindow.innerWidth;
                height = canvas.height = parentWindow.innerHeight;
                init();
            });

            class Particle {
                constructor(x, y) {
                    this.x = x; this.y = y;
                    this.baseX = x; this.baseY = y;
                    this.vx = 0; this.vy = 0; 

                    // 【视觉大改】去掉糖果色！改成极简的半透明纯白点，模拟神经节点
                    this.size = Math.random() * 1.5 + 0.5; 
                    this.color = `rgba(255, 255, 255, ${Math.random() * 0.4 + 0.2})`;

                    // 【时钟阵列】核心：将圆360度强制切分成 12 等份（像时钟或切蛋糕）
                    const slices = 12;
                    const sliceAngle = (Math.PI * 2) / slices;
                    this.targetAngle = Math.floor(Math.random() * slices) * sliceAngle; 

                    this.orbitSpeed = 0.015; // 整体时钟盘面缓慢、优雅地旋转
                    // 拉长时钟指针的长度，让射线的视觉更明显 (20 到 100 像素)
                    this.orbitRadius = (Math.random() * 80) + 20; 

                    this.captured = false; 
                }

                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.fillStyle = this.color;
                    ctx.fill();
                }

                update() {
                    this.baseX += (Math.random() - 0.5) * 0.3;
                    this.baseY += (Math.random() - 0.5) * 0.3;

                    // 1. 【点击爆炸逻辑优化】：让散开更柔和、自然
                    if (mouse.clicked && mouse.x > 0) {
                        let dx = this.x - mouse.x;
                        let dy = this.y - mouse.y;
                        let distance = Math.sqrt(dx * dx + dy * dy);

                        if (distance < 350) {
                            this.captured = false; 

                            // 【修改点】：增大分母，大幅降低爆炸瞬间的爆发力，解决飞出去太快的问题
                            let force = (350 - distance) / 80; 

                            this.vx += (dx / distance) * force;
                            this.vy += (dy / distance) * force;
                        }
                    }

                    // 应用速度与摩擦力衰减
                    this.x += this.vx; 
                    this.y += this.vy;

                    // 【修改点】：降低摩擦力，让粒子被炸开后有一种失重的丝滑滑行感，解决太快消失的问题
                    this.vx *= 0.94; 
                    this.vy *= 0.94;

                    // 2. 【吸附与旋转逻辑优化】：确保严格时钟形状
                    let dx = mouse.x - this.x;
                    let dy = mouse.y - this.y;
                    let distance = Math.sqrt(dx * dx + dy * dy);

                    if (distance < mouse.radius && !mouse.clicked) {
                        this.captured = true; 
                        this.targetAngle += this.orbitSpeed; 
                        let targetX = mouse.x + Math.cos(this.targetAngle) * this.orbitRadius;
                        let targetY = mouse.y + Math.sin(this.targetAngle) * this.orbitRadius;

                        this.x += (targetX - this.x) * 0.08;
                        this.y += (targetY - this.y) * 0.08;
                    } else {
                        this.captured = false; 
                        if (this.x !== this.baseX) this.x -= (this.x - this.baseX) * 0.02;
                        if (this.y !== this.baseY) this.y -= (this.y - this.baseY) * 0.02;
                    }
                }
            }

            function init() {
                particles = [];
                // 【修改点】：减少粒子数量，最大只保留 80 个节点，呈现极简风，解决蜘蛛网太密的问题
                let numberOfParticles = Math.min((width * height) / 12000, 80); 
                for (let i = 0; i < numberOfParticles; i++) {
                    particles.push(new Particle(Math.random() * width, Math.random() * height));
                }
            }

            function connect() {
                for (let a = 0; a < particles.length; a++) {
                    for (let b = a + 1; b < particles.length; b++) {
                        let pA = particles[a];
                        let pB = particles[b];

                        // 【核心修改点】：如果两个粒子都被吸附了，严禁跨越刻度连线！
                        // 只有当它们在同一条时钟指针上（targetAngle相同），才允许连线！彻底切断蜘蛛网！
                        if (pA.captured && pB.captured) {
                            if (pA.targetAngle !== pB.targetAngle) {
                                continue; 
                            }
                        }

                        let dx = pA.x - pB.x;
                        let dy = pA.y - pB.y;
                        let distance = dx * dx + dy * dy; 

                        // 【修改点】：缩短连线判定距离，让线条更清爽，只连接同一刻度线上的邻居，解决刻度串线问题
                        if (distance < 3000) { 
                            let opacity = 1 - (distance / 3000);
                            ctx.strokeStyle = `rgba(255, 255, 255, ${opacity * 0.35})`;
                            ctx.lineWidth = 0.8;
                            ctx.beginPath();
                            ctx.moveTo(pA.x, pA.y);
                            ctx.lineTo(pB.x, pB.y);
                            ctx.stroke();
                        }
                    }
                }
            }

            function animate() {
                ctx.clearRect(0, 0, width, height);
                for (let i = 0; i < particles.length; i++) {
                    particles[i].update();
                    particles[i].draw();
                }
                connect(); 
                parentWindow.requestAnimationFrame(animate);
            }

            init();
            animate();
        })();
        </script>
        """
    components.html(particle_js, width=0, height=0)

    # ======== 4. 完美复刻双拼卡片 + 全新金光特效 CSS ========
    login_style = """
    <style>
    [data-testid="block-container"] {
        background: linear-gradient(90deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.2) 45%, #ffffff 45%, #ffffff 100%) !important;
        backdrop-filter: blur(25px) !important;
        -webkit-backdrop-filter: blur(25px) !important;
        border-radius: 24px !important;
        box-shadow: 0 25px 60px rgba(0, 0, 0, 0.3) !important;
        padding: 0px !important; 
        max-width: 850px !important;
        margin-top: 10vh !important;
        overflow: hidden !important;
        border: 1px solid rgba(255,255,255,0.3) !important;
        border-right: none !important;
        border-bottom: none !important;
    }
    .stTextInput input {
        border-radius: 20px !important;
        border: 1px solid #e2e8f0 !important;
        background-color: #f8fafc !important;
        padding: 12px 20px !important;
        color: #333 !important;
        font-size: 14px !important;
    }
    .stTextInput input:focus {
        border-color: #a1c4fd !important;
        background-color: #fff !important;
        box-shadow: 0 0 0 3px rgba(161, 196, 253, 0.2) !important;
    }
    button[kind="primary"] {
        background: linear-gradient(90deg, #a1c4fd 0%, #f4d9d9 100%) !important;
        color: #555 !important;
        border: none !important;
        border-radius: 20px !important;
        font-weight: 800 !important;
        font-size: 16px !important;
        padding: 8px 0 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(161, 196, 253, 0.4) !important;
    }
    button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(161, 196, 253, 0.6) !important;
        color: #fff !important;
    }
    button[kind="secondary"] {
        border: none !important;
        background: transparent !important;
        color: #94a3b8 !important;
        font-weight: 600 !important;
        font-size: 14px !important;
    }
    button[kind="secondary"]:hover { 
        color: #a1c4fd !important; 
        background: transparent !important;
    }
    @keyframes dazzlingHalo {
        0% { box-shadow: 0 8px 24px rgba(0,0,0,0.08), 0 0 10px rgba(161, 196, 253, 0.2); }
        50% { box-shadow: 0 12px 30px rgba(0,0,0,0.1), 0 0 25px rgba(255, 126, 179, 0.4); }
        100% { box-shadow: 0 8px 24px rgba(0,0,0,0.08), 0 0 10px rgba(161, 196, 253, 0.2); }
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 126, 179, 0.8); }
        70% { transform: scale(1); box-shadow: 0 0 0 25px rgba(255, 126, 179, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 126, 179, 0); }
    }
    @keyframes blink { 50% { opacity: 0.4; } }

    /* ======== 金光闪闪动态渐变字体特效 ======== */
    @keyframes shimmerGold {
        0% { background-position: -100% 50%; }
        100% { background-position: 200% 50%; }
    }
    .gold-text {
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-size: 200% auto;
        display: inline-block;
    }
    .gold-1 {
        background-image: linear-gradient(120deg, #FFDF00 20%, #FFF8DC 40%, #D4AF37 60%, #FFDF00 80%);
        animation: shimmerGold 3s infinite linear;
    }
    .gold-2 {
        background-image: linear-gradient(120deg, #FDB931 20%, #FFE5B4 40%, #FF8C00 60%, #FDB931 80%);
        animation: shimmerGold 3.5s infinite linear; 
    }
    .gold-3 {
        background-image: linear-gradient(120deg, #FFD700 20%, #FFFACD 40%, #DAA520 60%, #FFD700 80%);
        animation: shimmerGold 4s infinite linear; 
    }
    .gold-dot {
        color: #FDB931;
        text-shadow: 0 0 10px rgba(253, 185, 49, 0.9);
        margin: 0 6px;
        font-weight: 900;
    }
    .gold-wrapper {
        margin-top: 25px;
        font-weight: 900;
        letter-spacing: 2px;
        filter: drop-shadow(0 4px 8px rgba(0,0,0,0.5)); 
    }
    </style>
    """
    st.markdown(login_style, unsafe_allow_html=True)

    # ======== 5. 读取 static 静态图片并融入背景 ========
    # 使用 mix-blend-mode: screen 滤除图片的黑色背景，保留霓虹光效
    img_html = '<img src="/app/static/logo4.png" style="width: 100%; height: 100%; object-fit: contain; mix-blend-mode: screen; filter: drop-shadow(0 0 10px rgba(161,196,253,0.5));">'
    col_left, col_right = st.columns([4.5, 5.5], gap="small")

    with col_left:
        # 修改说明：1. width和height调大为 200px (之前是160px)
        #            2. 添加 border-radius: 50% 和 overflow: hidden 强制变为圆形裁剪，
        #            3. 并添加 subtle box-shadow 增加质感
        left_html = f'''
        <div style="padding: 5rem 2rem; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center;">
            <div style="width: 280px; height: 280px; margin: 0 auto; border-radius: 50%; display: flex; align-items: center; justify-content: center; animation: dazzlingHalo 4s infinite; overflow: hidden; box-shadow: 0 0 15px rgba(161, 196, 253, 0.4); border: 2px solid rgba(255,255,255,0.2);">
                {img_html}
            </div>
            <h2 class="gold-wrapper"><span class="gold-text gold-1">洞察</span><span class="gold-dot">·</span><span class="gold-text gold-2">预测</span><span class="gold-dot">·</span><span class="gold-text gold-3">赋能</span></h2><p style="color: #f1f5f9; font-size: 15px; margin-top: 10px; text-shadow: 0 1px 5px rgba(0,0,0,0.3);">基于AI的电商平台客户体验分析系统</p>
        </div>
        '''
        st.markdown(left_html, unsafe_allow_html=True)

    with col_right:
        st.markdown('<div style="padding: 4rem 3rem 4rem 2rem;">', unsafe_allow_html=True)

        if st.session_state.auth_page == 'login':
            st.markdown(
                "<h1 style='background: linear-gradient(90deg, #8ec5fc 0%, #e0c3fc 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; text-align: center; margin-bottom: 5px; font-size: 36px; letter-spacing: 1px;'>Welcome Back</h1><p style='color: #94a3b8; text-align: center; font-size: 14px; margin-bottom: 30px;'>请登录您的账号</p>",
                unsafe_allow_html=True)

            login_user = st.text_input("用户名", value="admin", label_visibility="collapsed",
                                       placeholder="请输入用户名")
            login_pwd = st.text_input("密码", value="123456", type="password", label_visibility="collapsed",
                                      placeholder="请输入密码")

            loading_placeholder = st.empty()

            if st.button("登 录", type="primary", width="stretch"):
                # 修改说明：1. width和height调大为 150px (之前是130px)
                #            2. 添加 border-radius 和 overflow，并增加 subtle glow。
                loading_html = f'''
                            <div style="text-align: center; padding: 20px;">
                                <div style="width: 150px; height: 150px; margin: 0 auto; border-radius: 50%; display: flex; align-items: center; justify-content: center; animation: pulse 1.5s infinite; overflow: hidden; box-shadow: 0 0 15px rgba(255, 126, 179, 0.4); border: 2px solid rgba(255,255,255,0.1);">
                                    {img_html}
                                </div>
                                <div style="margin-top: 25px; color: #ff758c; font-weight: bold; font-size: 16px; animation: blink 1.8s infinite; text-shadow: 0 1px 2px rgba(0,0,0,0.05);">正在为您连接AI分析引擎...</div>
                            </div>
                            '''
                loading_placeholder.markdown(loading_html, unsafe_allow_html=True)

                import time

                time.sleep(0.8)

                success, user_id, role = db_manager.verify_login(login_user, login_pwd)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.current_user = login_user
                    st.session_state.current_user_id = user_id
                    st.session_state.current_role = role
                    st.rerun()
                else:
                    loading_placeholder.empty()
                    st.error("用户名或密码错误！")

            st.markdown("<hr style='margin: 20px 0; border: none; border-top: 1px solid #f1f5f9;'>",
                        unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("还没有账号？ 立即注册", width="stretch"): switch_page('register')
            with c2:
                if st.button("忘记密码？ 修改密码", width="stretch"): switch_page('reset_pwd')

        elif st.session_state.auth_page == 'register':
            st.markdown(
                "<h1 style='background: linear-gradient(90deg, #8ec5fc 0%, #e0c3fc 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; text-align: center; margin-bottom: 30px; font-size: 36px; letter-spacing: 2px;'>注册账号</h1>",
                unsafe_allow_html=True)
            reg_user = st.text_input("用户名", placeholder="请输入用户名", label_visibility="collapsed")
            reg_pwd = st.text_input("密码", type="password", placeholder="请输入密码", label_visibility="collapsed")
            reg_pwd2 = st.text_input("确认密码", type="password", placeholder="请确认密码",
                                     label_visibility="collapsed")
            reg_role = st.selectbox("选择角色", ["商家", "客户"], label_visibility="collapsed")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("提交注册", type="primary", width="stretch"):
                if not reg_user or not reg_pwd:
                    st.warning("请填写完整信息！")
                elif reg_pwd != reg_pwd2:
                    st.error("两次输入密码不一致！")
                else:
                    success, msg = db_manager.register_user(reg_user, reg_pwd, reg_role)
                    if success:
                        st.success("注册成功，请返回登录！")
                    else:
                        st.error(msg)
            if st.button("返回登录", width="stretch"): switch_page('login')

        elif st.session_state.auth_page == 'reset_pwd':
            st.markdown(
                "<h1 style='background: linear-gradient(90deg, #8ec5fc 0%, #e0c3fc 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; text-align: center; margin-bottom: 30px; font-size: 36px; letter-spacing: 2px;'>修改密码</h1>",
                unsafe_allow_html=True)
            reset_user = st.text_input("用户名", placeholder="请输入用户名", label_visibility="collapsed")
            reset_pwd = st.text_input("新密码", type="password", placeholder="请输入新密码",
                                      label_visibility="collapsed")
            reset_pwd2 = st.text_input("确认新密码", type="password", placeholder="请确认新密码",
                                       label_visibility="collapsed")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("确认修改", type="primary", width="stretch"):
                if reset_pwd != reset_pwd2:
                    st.error("两次输入密码不一致！")
                else:
                    success, msg = db_manager.update_password(reset_user, reset_pwd)
                    if success:
                        st.success("密码修改成功，请返回登录！")
                    else:
                        st.error(msg)
            if st.button("返回登录", width="stretch"): switch_page('login')

        st.markdown('</div>', unsafe_allow_html=True)

    st.stop()


# ======== 动态主题色覆盖引擎 (读取个人中心的设置) ========
# ======== 动态主题色覆盖引擎 (全量暖白背景 + 动效升级 + 强对比度修复) ========
dynamic_theme_css = f"""
<style>
/* ========================================================== */
/* 0. 基础布局与背景：全局暖白渐变                              */
/* ========================================================== */
/* 彻底透明化 Streamlit 默认 Header，解决顶部白块 */
[data-testid="stHeader"] {{
    background-color: transparent !important;
    background: transparent !important;
    box-shadow: none !important;
}}

/* 清除大盘背景限制 */
.stApp [data-testid="block-container"] {{
    background: transparent !important;
    box-shadow: none !important;
    border: none !important;
    max-width: 95% !important;
}}

/* 强制覆盖底层主界面的背景为暖白渐变 */
.stApp, [data-testid="stAppViewContainer"] {{
    background: linear-gradient(135deg, #FDFBF7 0%, #EFEBE4 50%, #DFD5C9 100%) !important;
    color: #334155 !important; 
}}

/* ========================================================== */
/* 特殊独立按钮专属颜色 (通过 Marker 定位)                      */
/* ========================================================== */

/* 1. 【Admin/个人中心】按钮：高级的紫灰/靛蓝色调 */
div[data-testid="stElementContainer"]:has(.profile-marker) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.profile-marker) + div[data-testid="element-container"] button {{
    background: linear-gradient(90deg, #EEF2FF 0%, #E0E7FF 100%) !important;
    border-color: #C7D2FE !important;
    color: #4338CA !important;
    font-weight: 600 !important;
}}
div[data-testid="stElementContainer"]:has(.profile-marker) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="element-container"]:has(.profile-marker) + div[data-testid="element-container"] button:hover {{
    background: #4338CA !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 12px rgba(67, 56, 202, 0.3) !important;
    border-color: #4338CA !important;
}}

/* 2. 【退出登录】按钮：柔和的警示红/橘色调 */
div[data-testid="stElementContainer"]:has(.logout-marker) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.logout-marker) + div[data-testid="element-container"] button {{
    background: linear-gradient(90deg, #FEF2F2 0%, #FEE2E2 100%) !important;
    border-color: #FECACA !important;
    color: #B91C1C !important;
    font-weight: 600 !important;
}}
div[data-testid="stElementContainer"]:has(.logout-marker) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="element-container"]:has(.logout-marker) + div[data-testid="element-container"] button:hover {{
    background: #DC2626 !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 12px rgba(220, 38, 38, 0.3) !important;
    border-color: #DC2626 !important;
}}

/* ========================================================== */
/* 个性化主题设置：四个预设颜色按钮专属动效                    */
/* ========================================================== */

/* 1. 古木棕按钮 */
div[data-testid="stElementContainer"]:has(.theme-brown) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.theme-brown) + div[data-testid="element-container"] button {{
    background: linear-gradient(90deg, #FDFBFB 0%, #F5F0EF 100%) !important;
    border-color: #E6DCDA !important;
    color: #8C6A64 !important; 
    font-weight: 600 !important;
}}
div[data-testid="stElementContainer"]:has(.theme-brown) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="element-container"]:has(.theme-brown) + div[data-testid="element-container"] button:hover {{
    /* 升级为高级古木棕渐变 */
    background: linear-gradient(135deg, #D5B9B2 0%, #BD9A94 100%) !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 15px rgba(189, 154, 148, 0.5) !important;
    border-color: #BD9A94 !important;
}}

/* 2. 暮色紫按钮 */
div[data-testid="stElementContainer"]:has(.theme-purple) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.theme-purple) + div[data-testid="element-container"] button {{
    background: linear-gradient(90deg, #FAF5FF 0%, #F3E8FF 100%) !important;
    border-color: #E9D5FF !important;
    color: #6D28D9 !important;
    font-weight: 600 !important;
}}
div[data-testid="stElementContainer"]:has(.theme-purple) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="element-container"]:has(.theme-purple) + div[data-testid="element-container"] button:hover {{
    background: #7c3aed !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3) !important;
    border-color: #7c3aed !important;
}}

/* 3. 抹茶绿按钮 */
div[data-testid="stElementContainer"]:has(.theme-green) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.theme-green) + div[data-testid="element-container"] button {{
    background: linear-gradient(90deg, #F7FEE7 0%, #ECFCCB 100%) !important;
    border-color: #D9F99D !important;
    color: #4D7C0F !important;
    font-weight: 600 !important;
}}
div[data-testid="stElementContainer"]:has(.theme-green) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="element-container"]:has(.theme-green) + div[data-testid="element-container"] button:hover {{
    background: #65a30d !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 12px rgba(101, 163, 13, 0.3) !important;
    border-color: #65a30d !important;
}}

/* 4. 琥珀橘按钮 */
div[data-testid="stElementContainer"]:has(.theme-orange) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.theme-orange) + div[data-testid="element-container"] button {{
    background: linear-gradient(90deg, #FFF7ED 0%, #FFEDD5 100%) !important;
    border-color: #FED7AA !important;
    color: #C2410C !important;
    font-weight: 600 !important;
}}
div[data-testid="stElementContainer"]:has(.theme-orange) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="element-container"]:has(.theme-orange) + div[data-testid="element-container"] button:hover {{
    background: #ea580c !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 12px rgba(234, 88, 12, 0.3) !important;
    border-color: #ea580c !important;
}}

/* ========================================================== */
/* 1. 按钮基础显示与交互动画                                  */
/* ========================================================== */
.stButton button {{
    background-color: #ffffff !important;
    background-image: none !important;
    color: #475569 !important; /* 按钮文字改为深色 */
    box-shadow: 0 2px 5px rgba(0,0,0,0.05) !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important; 
}}

/* 让侧边栏按钮默认带上微弱的主题色边框 */
[data-testid="stSidebar"] .stButton button {{
    border: 1px solid {st.session_state.theme_color}60 !important;
}}

/* 悬浮 (Hover) */
.stButton button:hover {{
    border-color: {st.session_state.theme_color} !important;
    box-shadow: 0 4px 12px {st.session_state.theme_color}30 !important;
    color: {st.session_state.theme_color} !important;
    transform: translateY(-2px); 
}}

/* 按压 (Active) */
.stButton button:active {{
    transform: scale(0.95) !important; 
    background: {st.session_state.theme_color} !important; 
    box-shadow: 0 2px 10px {st.session_state.theme_color}80 !important;
    color: #ffffff !important; 
    border-color: transparent !important;
}}

/* ========================================================== */
/* 引入呼吸灯动画关键帧 (全局可用)                              */
/* ========================================================== */
@keyframes pulse-app {{
    0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(161, 196, 253, 0.8); }}
    70% {{ transform: scale(1); box-shadow: 0 0 0 25px rgba(161, 196, 253, 0); }}
    100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(161, 196, 253, 0); }}
}}
@keyframes blink-app {{ 50% {{ opacity: 0.4; }} }}

/* 原 primary 按钮样式覆盖 */
.stButton > button[kind="primary"] {{
    /* 升级为高级渐变色，叠加半透明高光层以提升质感 */
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.25) 0%, rgba(0, 0, 0, 0.1) 100%), {st.session_state.theme_color} !important;
    color: white !important;
    border: none !important;
    box-shadow: 0 4px 15px {st.session_state.theme_color}50 !important;
    transition: all 0.3s ease !important;
}}
/* 【新增】强制将 primary 按钮内部的文字和图标变成白色 */
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"] span,
.stButton > button[kind="primary"] div {{
    color: #ffffff !important;
}}
.stButton > button[kind="primary"]:hover {{
    /* 悬浮时渐变反光增强，实现呼吸感 */
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.4) 0%, rgba(0, 0, 0, 0) 100%), {st.session_state.theme_color} !important;
    box-shadow: 0 6px 20px {st.session_state.theme_color}70 !important;
    transform: translateY(-2px);
    color: white !important;
}}

/* ========================================================== */
/* 2. 【核心修复】输入框、下拉框、搜索框的样式与文字隐形问题  */
/* ========================================================== */
/* 输入框和下拉框铺上干净的白底 */
.stTextInput input, div[data-baseweb="select"] > div {{
    background-color: #ffffff !important; 
    border: 1px solid rgba(0, 0, 0, 0.1) !important;
    color: #1e293b !important; /* 输入文字改为深色 */
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.02) !important;
}}

/* 修复下拉框选中的文字颜色 */
div[data-baseweb="select"] span {{
    color: #1e293b !important;
}}

/* 修复下拉选项菜单里的列表文字发白看不见的问题 */
div[data-baseweb="popover"] li, div[data-baseweb="popover"] span {{
    color: #1e293b !important; /* 强制下拉列表里的字变成深色 */
}}
div[data-baseweb="popover"] li:hover {{
    background-color: {st.session_state.theme_color}25 !important; /* 透明度从 15 提高到 25 */
    color: {st.session_state.theme_color} !important;
    font-weight: 600 !important;
}}

/* 修复占位符(Placeholder)看不清的问题 */
.stTextInput input::placeholder {{
    color: #94a3b8 !important;
}}

/* 聚焦状态发光 */
.stTextInput input:focus, div[data-baseweb="select"] > div:focus-within {{
    border-color: {st.session_state.theme_color} !important;
    box-shadow: 0 0 0 2px {st.session_state.theme_color}30 !important;
}}

/* ========================================================== */
/* 3. 全局卡片颜色渗透与文字提亮                              */
/* ========================================================== */
/* 卡片背景融入主题色，变成干净的白卡片 */
/* ========================================================== */
/* 3. 全局卡片颜色渗透与文字提亮 (修复折叠面板白底问题)           */
/* ========================================================== */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background-color: rgba(255, 255, 255, 0.4) !important; 
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(0,0,0,0.05) !important; 
    box-shadow: 0 8px 30px rgba(0,0,0,0.05) !important; 
}}

/* 彻底透明化 Expander (折叠面板) 及其内部结构 */
[data-testid="stExpander"] {{
    background-color: transparent !important;
    border: 1px solid rgba(0,0,0,0.05) !important;
    box-shadow: none !important;
}}
[data-testid="stExpander"] details {{
    background-color: transparent !important;
}}
[data-testid="stExpander"] summary {{
    background-color: rgba(255, 255, 255, 0.3) !important; /* 标题栏微微透白增加质感 */
    border-radius: 8px !important;
}}
[data-testid="stExpander"] details > div {{
    background-color: transparent !important;
}}

/* 侧边栏改为非常柔和的米白色渐变 */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, rgba(250, 250, 250, 0.8) 20%, {st.session_state.theme_color}30 100%) !important;
    border-right: 1px solid {st.session_state.theme_color}25 !important;
    backdrop-filter: blur(15px) !important;
}}

/* 侧边栏标题、主界面强调文字去除非必要的发光，改为干净的深色+主题色 */
h1, h2, h3 {{
    color: #1e293b !important; /* 主标题深色 */
    background: none !important;
    -webkit-text-fill-color: initial !important;
}}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
    color: {st.session_state.theme_color} !important;
    text-shadow: none !important;
}}

/* 指标数值和选中的 Tab 高亮 */
[data-testid="stMetricValue"], [data-testid="stTabs"] button[aria-selected="true"] p {{
    color: {st.session_state.theme_color} !important;
    text-shadow: none !important;
    font-weight: 700 !important;
}}

/* 选中的 Tab 底部横条 */
[data-testid="stTabs"] button[aria-selected="true"] {{
    border-bottom-color: {st.session_state.theme_color} !important;
    box-shadow: none !important;
}}
[data-testid="stTabs"] button p {{
    color: #64748b !important; /* 未选中状态的 tab 文字 */
}}

/* 预警框/提示框变成干净的样式 */
[data-testid="stAlert"] {{
    background-color: #ffffff !important;
    border: 1px solid {st.session_state.theme_color}40 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.02) !important;
}}

/* 所有常规文字改为深灰色，确保亮色背景下的可读性 */
.stMarkdown p, .stMarkdown span, label p {{
    color: #334155 !important;
}}

/* ========================================================== */
/* 图表与表格容器：去死白，改为半透明磨砂玻璃融入背景           */
/* ========================================================== */
/* 定位 Altair 图表容器 */
[data-testid="stVegaLiteChart"] > div {{
    background-color: rgba(255, 255, 255, 0.3) !important;
    border-radius: 12px !important;
    padding: 10px !important;
}}

/* 定位数据表格容器 */
[data-testid="stDataFrame"] > div {{
    background-color: rgba(255, 255, 255, 0.4) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(0,0,0,0.05) !important;
    overflow: hidden !important;
}}

[data-testid="stDataFrame"] th {{
    background-color: rgba(245, 241, 234, 0.8) !important; 
    color: #475569 !important;
}}

/* ========================================================== */
/* 全局数据表格 (Data Editor) 高级卡片化融合外观 (修复白底)      */
/* ========================================================== */
[data-testid="stDataFrame"] {{
    background: transparent !important; /* 【核心修复】：彻底透明，跟随底层全局渐变 */
    border: 1px solid rgba(0,0,0,0.05) !important; 
    border-radius: 12px !important; 
    box-shadow: 0 4px 16px rgba(0,0,0,0.05) !important; 
    overflow: hidden !important;
    padding: 28px 6px 6px 6px !important; 
    position: relative !important; 
    --background-color: transparent !important; 
    --secondary-background-color: rgba(255,255,255,0.2) !important; 
}}

/* 2. 抹除底层默认直角边框，确保内层透明以透出暖咖白 */
[data-testid="stDataFrame"] > div {{
    border: none !important;
    border-radius: 6px !important;
    background-color: transparent !important; 
}}

/* 3. 把小图标强行“拔”进我们预留的顶部空白区域 */
[data-testid="stDataFrame"] [data-testid="stElementToolbar"] {{
    opacity: 0.6 !important; 
    position: absolute !important; 
    top: -10px !important;   /* 【核心修复】：必须用负数！把它向上拉出表格内容区 */
    right: 8px !important; 
    z-index: 99 !important; 
}}

/* 鼠标放上去时图标清晰度恢复 */
[data-testid="stDataFrame"] [data-testid="stElementToolbar"]:hover {{
    opacity: 1.0 !important;
}}

/* ========================================================== */
/* 专属下载按钮美化 (天蓝色渐变效果)                             */
/* ========================================================== */
/* 1. 平时状态：淡雅天蓝渐变 */
[data-testid="stDownloadButton"] button {{
    background: linear-gradient(90deg, #E0F2FE 0%, #BAE6FD 100%) !important;
    border: 1px solid #BAE6FD !important;
    color: #0EA5E9 !important; /* 深一点的天蓝色文字，保证在浅底色上的清晰度 */
    font-weight: 600 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 8px rgba(14, 165, 233, 0.1) !important;
    transition: all 0.3s ease !important;
}}

/* 2. 悬停与点击状态：纯正天蓝色爆发 */
[data-testid="stDownloadButton"] button:hover,
[data-testid="stDownloadButton"] button:active {{
    background: #0EA5E9 !important; /* 纯正天蓝色 */
    color: #FFFFFF !important; /* 文字变白 */
    border-color: #0EA5E9 !important;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3) !important;
    transform: translateY(-2px); /* 悬浮动效 */
}}

/* ========================================================== */
/* 表格内部纯白底色消除魔法 (混合模式)                        */
/* ========================================================== */
[data-testid="stDataFrame"] canvas {{
    mix-blend-mode: multiply !important;
}}

/* ========================================================== */
/* 修复下拉菜单选项“白字隐形”问题                              */
/* ========================================================== */
div[data-baseweb="popover"] > div {{
    background-color: #FFFFFF !important;
}}
div[data-baseweb="popover"] li,
div[data-baseweb="popover"] span {{
    color: #475569 !important; 
}}
div[data-baseweb="popover"] li:hover,
div[data-baseweb="popover"] li:hover span {{
    background-color: #F5F0EF !important;
    color: #8C6A64 !important; 
}}

/* ========================================================== */
/* 新增：侧边栏【返回主页】渐变紫按钮                          */
/* ========================================================== */
/* 1. 基础状态：高质感的渐变紫 */
div[data-testid="stElementContainer"]:has(.home-marker) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.home-marker) + div[data-testid="element-container"] button {{
    background: linear-gradient(135deg, #d8b4fe 0%, #a855f7 100%) !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3) !important;
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
}}

/* 2. 强行将按钮内的文字和图标变成纯白色，防止被全局深色覆盖 */
div[data-testid="stElementContainer"]:has(.home-marker) + div[data-testid="stElementContainer"] button p,
div[data-testid="stElementContainer"]:has(.home-marker) + div[data-testid="stElementContainer"] button span,
div[data-testid="stElementContainer"]:has(.home-marker) + div[data-testid="stElementContainer"] button div,
div[data-testid="element-container"]:has(.home-marker) + div[data-testid="element-container"] button p,
div[data-testid="element-container"]:has(.home-marker) + div[data-testid="element-container"] button span,
div[data-testid="element-container"]:has(.home-marker) + div[data-testid="element-container"] button div {{
    color: #ffffff !important;
    font-weight: 700 !important;
    letter-spacing: 0.5px !important;
}}

/* 3. 悬停状态：加深紫色并增加悬浮感 */
div[data-testid="stElementContainer"]:has(.home-marker) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="element-container"]:has(.home-marker) + div[data-testid="element-container"] button:hover {{
    background: linear-gradient(135deg, #c084fc 0%, #9333ea 100%) !important;
    box-shadow: 0 6px 16px rgba(147, 51, 234, 0.4) !important;
    transform: translateY(-2px);
}}

/* ========================================================== */
/* 新增：管理员后台【确认覆盖】专属渐变红按钮                  */
/* ========================================================== */
/* 1. 基础状态：醒目的红橙渐变 */
div[data-testid="stElementContainer"]:has(.admin-fix-marker) + div[data-testid="stElementContainer"] button,
div[data-testid="element-container"]:has(.admin-fix-marker) + div[data-testid="element-container"] button {{
    background: linear-gradient(90deg, #ff416c 0%, #ff4b2b 100%) !important;
    border: none !important;
    box-shadow: 0 4px 15px rgba(255, 75, 43, 0.3) !important;
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
}}

/* 2. 强行将按钮内的文字和图标变成纯白色，防止被全局深色覆盖 */
div[data-testid="stElementContainer"]:has(.admin-fix-marker) + div[data-testid="stElementContainer"] button p,
div[data-testid="stElementContainer"]:has(.admin-fix-marker) + div[data-testid="stElementContainer"] button span,
div[data-testid="stElementContainer"]:has(.admin-fix-marker) + div[data-testid="stElementContainer"] button div,
div[data-testid="element-container"]:has(.admin-fix-marker) + div[data-testid="element-container"] button p,
div[data-testid="element-container"]:has(.admin-fix-marker) + div[data-testid="element-container"] button span,
div[data-testid="element-container"]:has(.admin-fix-marker) + div[data-testid="element-container"] button div {{
    color: #ffffff !important;
    font-weight: 700 !important;
    letter-spacing: 1px !important;
}}

/* 3. 悬停与点击状态：变为纯正的红色，并增加悬浮感 */
div[data-testid="stElementContainer"]:has(.admin-fix-marker) + div[data-testid="stElementContainer"] button:hover,
div[data-testid="stElementContainer"]:has(.admin-fix-marker) + div[data-testid="stElementContainer"] button:active,
div[data-testid="element-container"]:has(.admin-fix-marker) + div[data-testid="element-container"] button:hover,
div[data-testid="element-container"]:has(.admin-fix-marker) + div[data-testid="element-container"] button:active {{
    background: #FF0000 !important; /* 纯正红色 */
    box-shadow: 0 6px 20px rgba(255, 0, 0, 0.5) !important;
    transform: translateY(-2px);
}}

/* ========================================================== */
/* 侧边栏下拉框 (Selectbox) 质感重塑 (修复光标与旋转动效)       */
/* ========================================================== */

/* 1. 下拉框本体：增加悬浮质感、微光边框和【小手光标】 */
div[data-baseweb="select"] > div {{
    background-color: rgba(255, 255, 255, 0.7) !important;
    backdrop-filter: blur(10px) !important;
    border: 1px solid rgba(255, 255, 255, 0.5) !important;
    border-radius: 12px !important;
    box-shadow: 
        0 2px 6px rgba(0,0,0,0.05), 
        inset 0 1px 0 rgba(255,255,255,0.8) !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    cursor: pointer !important; /* 【核心修复1】默认显示为小手 */
}}

/* 【核心修复1 补充】穿透底层 input 的文字光标拦截 */
div[data-baseweb="select"] input {{
    cursor: pointer !important; /* 未输入时，强制显示为小手 */
}}
div[data-baseweb="select"] input:focus {{
    cursor: text !important; /* 只有真正聚焦准备打字搜索时，才恢复成文本光标 */
}}

/* 2. 鼠标悬停/聚焦时：边框颜色跟随主题色并增加发光 */
div[data-baseweb="select"] > div:hover, 
div[data-baseweb="select"] > div:focus-within {{
    border-color: {st.session_state.theme_color} !important;
    box-shadow: 
        0 4px 12px {st.session_state.theme_color}20,
        inset 0 1px 0 rgba(255,255,255,0.8) !important;
    transform: translateY(-1px);
}}

/* 3. 下拉弹出的菜单面板：增加深度阴影 */
div[data-baseweb="popover"] > div {{
    border-radius: 12px !important;
    background-color: rgba(255, 255, 255, 0.95) !important;
    backdrop-filter: blur(15px) !important;
    border: 1px solid rgba(0, 0, 0, 0.05) !important;
    box-shadow: 0 10px 25px rgba(0,0,0,0.1) !important;
    margin-top: 8px !important;
    overflow: hidden !important;
}}

/* 4. 选项列表交互：悬停时的高亮效果 */
div[data-baseweb="popover"] li {{
    padding: 10px 15px !important;
    margin: 4px 8px !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
    color: #475569 !important;
    cursor: pointer !important; /* 确保列表选项也是小手 */
}}

div[data-baseweb="popover"] li:hover {{
    background-color: {st.session_state.theme_color}15 !important;
    color: {st.session_state.theme_color} !important;
    padding-left: 20px !important;
}}

/* 5. 修复下拉框内的文字颜色与图标 */
div[data-baseweb="select"] span {{
    color: #1e293b !important;
    font-weight: 500 !important;
}}

/* 下拉箭头小图标着色 */
div[data-baseweb="select"] svg {{
    fill: #94a3b8 !important;
    transition: transform 0.3s ease !important;
}}

/* 【核心修复2】展开时箭头旋转动效：监听原生的 aria-expanded 真实展开状态 */
div[data-baseweb="select"] div[aria-expanded="true"] svg {{
    fill: {st.session_state.theme_color} !important;
    transform: rotate(180deg) !important;
}}
</style>
"""
st.markdown(dynamic_theme_css, unsafe_allow_html=True)

@st.cache_data(ttl=2.0, show_spinner=False)
def get_user_data_debounced(user_id):
    if not user_id:
        return None
    return db_manager.get_user_data_and_check_reset(user_id)

user_data = get_user_data_debounced(st.session_state.current_user_id)

if user_data:
    role = user_data['role']
    spider_cnt = user_data['spider_count']
    ai_cnt = user_data['ai_count']
    dl_cnt = user_data['dl_count']
else:
    # 兜底防止报错
    role = '客户'
    spider_cnt = ai_cnt = dl_cnt = 0


with st.sidebar:
    # ====== 新增：渐变紫色的返回主页按钮 ======
    # 如果当前不在主页，才显示返回主页按钮（保持UI清爽）
    if st.session_state.current_page != 'main':
        st.markdown('<span class="home-marker"></span>', unsafe_allow_html=True)
        if st.button(":material/home: 返回分析大厅", width="stretch"):
            st.session_state.current_page = 'main'
            st.rerun()
        # st.markdown("---")
    # ==========================================
    if st.session_state.current_page != 'profile':
        st.markdown('<span class="profile-marker"></span>', unsafe_allow_html=True)
        if st.button(f":material/account_circle: {st.session_state.current_user}  ({role})", width="stretch",
                     help="点击进入个人中心"):
            st.session_state.current_page = 'profile'
            st.rerun()

    if role == '客户':
        st.markdown(f"**今日额度 (3次/日):**\n- 今日爬虫额度: {spider_cnt}/3\n- 今日 AI 额度: {ai_cnt}/3\n-  下载: {dl_cnt}/3")
    elif role == '商家':
        st.markdown(f"**今日免费额度 (10次/日):**\n- 今日爬虫额度: {spider_cnt}/10\n- 今日 AI 额度: {ai_cnt}/10")

    st.markdown('<span class="logout-marker"></span>', unsafe_allow_html=True)
    if st.button(":material/logout: 退出登录"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.logged_in = False
        st.session_state.auth_page = 'login'
        st.session_state.current_page = 'main'
        st.rerun()
    if role == '管理员':
        st.markdown("---")
        st.header(":material/manage_accounts: 系统全局管理")
        admin_btn_label = ":material/home: 返回分析大厅" if st.session_state.current_page == 'admin' else ":material/manage_search: 进入后台"
        if st.button(admin_btn_label, width="stretch", type="primary"):
            st.session_state.current_page = 'admin' if st.session_state.current_page != 'admin' else 'main'
            st.rerun()
    st.markdown("---")
    if role in ['商家', '管理员']:
        st.header(":material/History: 历史数据")
        btn_label = ":material/home: 返回分析大厅" if st.session_state.current_page == 'history' else ":material/deployed_code_history: 查看历史记录"
        if st.button(btn_label, width="stretch", type="primary"):
            st.session_state.current_page = 'main' if st.session_state.current_page == 'history' else 'history'
            st.rerun()
    if role != '客户': st.markdown("---")
    st.header(":material/Neurology: AI 模型选择")
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
    if role == '商家': st.markdown("---")
    user_api_key = default_key_from_env
    is_using_custom_key = False
    if role != '管理员':
        if role == '商家':
            st.header(":material/settings: 配置API-key")
            if ai_cnt >= 10:
                st.warning(":material/warning: 今日免费额度已用尽，需配置自有 Key")
                user_api_key = st.text_input("API Key", value="", type="password", placeholder="请输入您的 API Key")
                if user_api_key:
                    is_using_custom_key = True
            else:
                st.caption("正在使用系统自带的 API Key，您可配置自己的 API Key 解除 AI 额度限制")
                custom_key = st.text_input("自定义 API Key (选填)", value="", type="password")
                if custom_key: user_api_key = custom_key
                if custom_key:
                    user_api_key = custom_key
                    is_using_custom_key = True
    else:
        if not default_key_from_env:
            st.error("系统环境变量缺失 API Key！")
            user_api_key = st.text_input("系统 API Key 兜底配置 (仅管理员可见)", type="password")
    st.markdown("---")
    st.markdown("""
            <style>
            /* 找到内部包含 .red-marker 的区块，强行把它紧邻的下一个区块里的按钮变红！ */
            div[data-testid="stElementContainer"]:has(.red-marker) + div[data-testid="stElementContainer"] button,
            div[data-testid="element-container"]:has(.red-marker) + div[data-testid="element-container"] button {
                background-color: #FF4B4B !important;
                border-color: #FF4B4B !important;
                color: #ffffff !important;
            }

            /* 【核心修复】强行将红色按钮内部的文字(p)、图标(span/div)也彻底变成白色 */
            div[data-testid="stElementContainer"]:has(.red-marker) + div[data-testid="stElementContainer"] button p,
            div[data-testid="stElementContainer"]:has(.red-marker) + div[data-testid="stElementContainer"] button span,
            div[data-testid="stElementContainer"]:has(.red-marker) + div[data-testid="stElementContainer"] button div,
            div[data-testid="element-container"]:has(.red-marker) + div[data-testid="element-container"] button p,
            div[data-testid="element-container"]:has(.red-marker) + div[data-testid="element-container"] button span,
            div[data-testid="element-container"]:has(.red-marker) + div[data-testid="element-container"] button div {
                color: #ffffff !important;
            }

            div[data-testid="stElementContainer"]:has(.red-marker) + div[data-testid="stElementContainer"] button:hover,
            div[data-testid="element-container"]:has(.red-marker) + div[data-testid="element-container"] button:hover {
                background-color: #FF3333 !important;
                border-color: #FF3333 !important;
            }
            </style>
        """, unsafe_allow_html=True)
    st.markdown('<span class="red-marker"></span>', unsafe_allow_html=True)
    if st.button(":material/delete: 清空当前页面记录", width="stretch"):
        for k in list(st.session_state.keys()):
            if k not in ['current_user', 'current_user_id', 'current_role', 'current_page', 'auth_status', 'logged_in',
                         'spider_cnt', 'ai_cnt', 'dl_cnt']:
                del st.session_state[k]
        st.rerun()

# ======== 新增：个人中心与主题设置页面 ========
if st.session_state.current_page == 'profile':
    st.title(":material/person: 个人中心与偏好设置")

    st.markdown("---")

    col_info, col_theme = st.columns(2, gap="large")
    with col_info:
        st.subheader(":material/badge: 账户概览")
        with st.container(border=True):
            # 将 Emoji 替换为 Material Icons
            st.markdown(f"**:material/person: 用户名：** {st.session_state.current_user}")
            st.markdown(f"**:material/fingerprint: 专属 ID：** {st.session_state.current_user_id}")
            st.markdown(f"**:material/security: 角色权限：** {st.session_state.current_role}")
            st.markdown(f"**:material/calendar_today: 上次活跃：** {user_data.get('last_date', today_str)}")

        st.subheader(":material/donut_small: 今日额度详情")
        with st.container(border=True):
            if role == '客户':
                # travel_explore 代表爬虫抓取，psychology 代表 AI 分析，download 代表下载
                st.write(f"- :material/travel_explore: 爬虫抓取: **{spider_cnt}** / 3 次")
                st.write(f"- :material/psychology: AI 分析: **{ai_cnt}** / 3 次")
                st.write(f"- :material/download: 数据下载: **{dl_cnt}** / 3 次")
            elif role == '商家':
                st.write(f"- :material/travel_explore: 爬虫抓取: **{spider_cnt}** / 10 次")
                st.write(f"- :material/psychology: AI 分析: **{ai_cnt}** / 10 次")
                st.write("- :material/download: 数据下载: 不限次数")
            else:
                st.success(":material/workspace_premium: 管理员权限：系统全功能无限制")

    with col_theme:
        st.subheader(":material/palette: 个性化主题设置")
        with st.container(border=True):
            st.write("自定义您的专属科技高亮色：")

            # 【优化】：将颜色选择和应用分离，防止拖动时疯狂刷新
            col_picker, col_apply = st.columns([3, 2], vertical_alignment="bottom")
            with col_picker:
                # 只存临时状态，不直接修改 session_state.theme_color
                temp_color = st.color_picker("拾取霓虹高亮色", st.session_state.theme_color, key="temp_theme_picker")
            with col_apply:
                if st.button(":material/palette: 应用高亮色", type="primary", width="stretch"):
                    st.session_state.theme_color = temp_color
                    st.rerun()

            st.caption("提示：点击应用后，将实时接管全站的输入框、数字看板、选项卡和悬浮光效。")

            st.markdown("<br>或者快速应用预设方案：", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown('<span class="theme-brown"></span>', unsafe_allow_html=True)
                if st.button("古木棕", width="stretch"):
                    st.session_state.theme_color = "#BD9A94"
                    st.rerun()
            with c2:
                st.markdown('<span class="theme-purple"></span>', unsafe_allow_html=True)
                if st.button("暮色紫", width="stretch"):
                    st.session_state.theme_color = "#7c3aed"
                    st.rerun()
            with c3:
                st.markdown('<span class="theme-green"></span>', unsafe_allow_html=True)
                if st.button("抹茶绿", width="stretch"):
                    st.session_state.theme_color = "#65a30d"
                    st.rerun()
            with c4:
                st.markdown('<span class="theme-orange"></span>', unsafe_allow_html=True)
                if st.button("琥珀橘", width="stretch"):
                    st.session_state.theme_color = "#ea580c"
                    st.rerun()

    st.stop()  # 必须保留，阻断主页面的渲染


if st.session_state.current_page == 'history':
    st.title(f":material/data_table: {st.session_state.current_role}历史数据看板")
    import db_manager
    tab_view, tab_edit = st.tabs([":material/insights: 可视化走势分析", ":material/table_chart: 我的数据大盘 (增删改查)"])
    with tab_view:
        history_products = db_manager.get_merchant_products(st.session_state.current_user_id)
        if not history_products:
            st.info("暂无历史记录。请先在分析大厅抓取单品数据，AI 分析后会自动保存。")
        else:
            selected_item = st.selectbox(
                "选择要查阅的商品",
                history_products,
                format_func=lambda x: f"{x[1]} (ID: {x[0]})"
            )
            if selected_item:
                product_id = selected_item[0]
                trend_df = db_manager.get_product_trend(st.session_state.current_user_id, product_id)
                if not trend_df.empty:
                    st.markdown("---")
                    trend_df.set_index('日期', inplace=True)
                    trend_df_sorted = trend_df.sort_index()
                    if len(trend_df_sorted) >= 2:
                        curr_sales = trend_df_sorted['销量'].iloc[-1]
                        prev_sales = trend_df_sorted['销量'].iloc[-2]
                        if prev_sales > 0:
                            growth_rate = ((curr_sales - prev_sales) / prev_sales) * 100
                            st.subheader(" 销量核心指标监控")
                            col_m1, col_m2 = st.columns(2)
                            with col_m1:
                                st.metric(label="最新记录销量", value=f"{curr_sales} 单", delta=f"{growth_rate:.2f}%")
                            if growth_rate < 10.0:
                                st.warning(
                                    f"**销量增长预警！** 最近一期销量较上期增长仅为 {growth_rate:.2f}%，低于 10% 阈值！",
                                    icon=":material/alarm:")
                            else:
                                st.success(f"销量增长健康！近期增长率为 {growth_rate:.2f}%。", icon="")
                            st.markdown("---")
                    plot_df = trend_df_sorted.reset_index().copy()
                    plot_df['数据类型'] = '真实数据'
                    combined_df = render_trend_prediction_charts(plot_df)

                    if combined_df is not None:
                        st.markdown("### :material/database: 详细数据明细 (含预测数据)")
                        st.dataframe(combined_df, width="stretch")
                        st.download_button(
                            label=":material/download: 下载该商品历史及预测数据 (.csv)",
                            data=combined_df.to_csv(index=False).encode('utf-8-sig'),
                            file_name=f"trend_prediction.csv",
                            mime='text/csv'
                        )
    with tab_edit:
        st.subheader(":material/edit_document: 管理我的所有追踪记录")
        st.caption("提示：双击单元格即可修改数据。选中行按 Delete 键可删除。点击底部加号可新增记录。")
        df_my_stats = db_manager.get_merchant_product_stats(st.session_state.current_user_id)
        col_search_input, col_search_btn = st.columns([5, 1])
        with col_search_input:
            search_my_pid = st.text_input(
                "搜索商品ID",
                placeholder="筛选商品 ID (支持模糊查询)",
                label_visibility="collapsed",
                key="search_merchant_pid"
            )
        with col_search_btn:
            st.button(":material/search: 搜索", type="primary", width="stretch")
        filtered_my_stats = df_my_stats.copy()
        if search_my_pid:
            filtered_my_stats = filtered_my_stats[
                filtered_my_stats['product_id'].astype(str).str.contains(search_my_pid.strip(), case=False,
                                                                         na=False)
            ]
        edited_my_stats = st.data_editor(
            filtered_my_stats,
            num_rows="dynamic",
            disabled=["id", "user_id"],
            width="stretch",
            key="merchant_stat_editor",
            column_config={
                "id": None,
                "user_id": None,
                "product_id": "商品 ID",
                "product_name": "商品名称",
                "record_date": "记录日期",
                "sales_volume": "销量记录",
                "positive_rate": "综合 CBEI 记录分"
            }
        )
        st.markdown('<span class="red-marker"></span>', unsafe_allow_html=True)
        if st.button(":material/check_circle: 确认并覆盖我的数据"):
            db_manager.sync_merchant_product_stats(edited_my_stats, filtered_my_stats,
                                                   st.session_state.current_user_id)
            st.toast(":material/check_circle: 您的历史数据更新成功！")
            import time
            time.sleep(1.2)
            st.rerun()
    st.stop()

if st.session_state.current_page == 'admin':
    if st.session_state.current_role != '管理员':
        st.error(":material/gpp_maybe: 越权访问拦截：您不是管理员！")
        st.stop()
    st.title(":material/manage_search: 系统管理员全局控制台")
    st.caption("提示：在表格中双击单元格即可修改数据。选中行按 Delete 键可删除。点击底部加号可新增。")

    # ==========================================
    # 【UI 魔法】：将丑陋的单选框爆改为“高级苹果风分段控制器”
    # ==========================================
    st.markdown(f"""
        <style>
        /* 1. 给整个导航栏底座加上半透明玻璃磨砂质感 */
        div[data-testid="stRadio"] > div {{
            background: rgba(255, 255, 255, 0.6) !important;
            backdrop-filter: blur(10px) !important;
            padding: 6px 8px !important;
            border-radius: 12px !important;
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.03), 0 4px 15px rgba(0,0,0,0.02) !important;
            display: flex !important;
            gap: 8px !important;
            flex-wrap: wrap !important;
        }}

        /* 2. 彻底隐藏原生单选小圆圈 */
        div[data-testid="stRadio"] label div[data-baseweb="radio"] > div:first-child {{
            display: none !important;
        }}

        /* 3. 重塑每个选项卡为独立的高级按钮 */
        div[data-testid="stRadio"] label {{
            background: transparent !important;
            padding: 10px 20px !important;
            border-radius: 8px !important;
            cursor: pointer !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
            margin: 0 !important;
            border: 1px solid transparent !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }}

        /* 未选中时的文字样式 */
        div[data-testid="stRadio"] label p {{
            color: #64748b !important;
            font-weight: 600 !important;
            font-size: 15px !important;
            margin: 0 !important;
        }}

        /* 4. 鼠标悬停时的微浮动反馈 */
        div[data-testid="stRadio"] label:hover {{
            background: rgba(255, 255, 255, 0.9) !important;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05) !important;
            transform: translateY(-2px) !important;
        }}

        /* 5. 🌟 选中时的终极高亮质感（动态跟随个人中心的主题色） */
        div[data-testid="stRadio"] label:has(input:checked) {{
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(0, 0, 0, 0) 100%), {st.session_state.theme_color} !important;
            box-shadow: 0 4px 15px {st.session_state.theme_color}50 !important;
            border: 1px solid rgba(255,255,255,0.2) !important;
            transform: translateY(-2px) !important;
        }}

        /* 选中时的文字变成纯白发光 */
        div[data-testid="stRadio"] label:has(input:checked) p {{
            color: #ffffff !important;
            text-shadow: 0 1px 3px rgba(0,0,0,0.2) !important;
            font-weight: 700 !important;
        }}
        </style>
        """, unsafe_allow_html=True)

    admin_module = st.radio(
        "管理模块导航",
        [
            ":material/manage_accounts: 账号权限管控",
            ":material/history: 历史查询记录",
            ":material/bar_chart: CBEI 品类全局大盘",
            ":material/inventory_2: 核心商品元数据库",
            ":material/forum: AI 打分评论明细库"
        ],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("---")

    if admin_module == ":material/manage_accounts: 账号权限管控":
        st.subheader(":material/manage_accounts: 全局用户表")

        # 1. 获取数据 (直接从内存缓存拉取)
        df_users = load_cached_users().copy()

        # 2. 搜索栏
        col_u_search1, col_u_search2, col_u_btn = st.columns([4, 4, 1])
        with col_u_search1:
            search_u_id = st.text_input("搜索用户ID", placeholder=" 筛选用户 ID (模糊查询)",
                                        label_visibility="collapsed", key="search_u_id_input")
        with col_u_search2:
            search_u_name = st.text_input("搜索用户名", placeholder=" 搜索用户名 (模糊查询)",
                                          label_visibility="collapsed", key="search_u_name_input")
        with col_u_btn:
            st.button(":material/search: 搜索", key="btn_u_search", type="primary", width="stretch")

        # 3. 向量化极速过滤
        # 3. 向量化极速过滤
        filtered_users_df = df_users.copy()
        if search_u_id:
            filtered_users_df = filtered_users_df[
                filtered_users_df['id'].astype(str).str.contains(search_u_id.strip(), case=False, na=False)
            ]
        if search_u_name:
            filtered_users_df = filtered_users_df[
                filtered_users_df['username'].astype(str).str.contains(search_u_name.strip(), case=False, na=False)
            ]


        # ==========================================
        # 【极致流畅优化 3】：将 Admin 表格的分页与渲染打包为 Fragment
        # ==========================================
        @st.fragment
        def render_users_pagination_and_table(filtered_df):
            if 'usr_page_size' not in st.session_state: st.session_state.usr_page_size = 50
            if 'usr_page_num' not in st.session_state: st.session_state.usr_page_num = 1

            total_rows_u = len(filtered_df)
            total_pages_u = max(1, (total_rows_u - 1) // st.session_state.usr_page_size + 1)

            if st.session_state.usr_page_num > total_pages_u:
                st.session_state.usr_page_num = total_pages_u

            st.markdown("""
                    <style>
                    div[data-baseweb="popover"] li { margin: 0px !important; }
                    </style>
                    """, unsafe_allow_html=True)

            col_size_u, col_empty_u, col_prev_u, col_page_u, col_next_u = st.columns([1.5, 5.5, 0.8, 1.8, 0.8],
                                                                                     vertical_alignment="center")

            with col_size_u:
                new_size_u = st.selectbox(
                    "单页显示条数", [50, 100, 200, 500],
                    index=[50, 100, 200, 500].index(st.session_state.usr_page_size),
                    format_func=lambda x: f"每页 {x} 条", label_visibility="collapsed", key="usr_size_selector"
                )
                if new_size_u != st.session_state.usr_page_size:
                    st.session_state.usr_page_size = new_size_u
                    st.session_state.usr_page_num = 1
                    st.rerun(scope="fragment")  # 局部刷新

            with col_prev_u:
                if st.button("⬅", width="stretch", disabled=st.session_state.usr_page_num <= 1,
                             key="btn_usr_prev"):
                    st.session_state.usr_page_num -= 1
                    st.rerun(scope="fragment")

            with col_page_u:
                new_page_u = st.selectbox(
                    "跳转页码", options=list(range(1, total_pages_u + 1)),
                    index=st.session_state.usr_page_num - 1,
                    format_func=lambda x: f"第 {x} / {total_pages_u} 页", label_visibility="collapsed",
                    key="usr_page_selector"
                )
                if new_page_u != st.session_state.usr_page_num:
                    st.session_state.usr_page_num = new_page_u
                    st.rerun(scope="fragment")

            with col_next_u:
                if st.button("➡", width="stretch", disabled=st.session_state.usr_page_num >= total_pages_u,
                             key="btn_usr_next"):
                    st.session_state.usr_page_num += 1
                    st.rerun(scope="fragment")

            st.markdown(
                f"<div style='text-align:right; margin-top:-10px; margin-bottom: 5px; color:#94a3b8; font-size:13px;'>共匹配到 {total_rows_u} 个用户</div>",
                unsafe_allow_html=True)

            start_idx_u = (st.session_state.usr_page_num - 1) * st.session_state.usr_page_size
            end_idx_u = start_idx_u + st.session_state.usr_page_size
            page_df_u = filtered_df.iloc[start_idx_u:end_idx_u].copy()

            edited_users = st.data_editor(
                page_df_u, num_rows="dynamic", disabled=["id"], width="stretch",
                key=f"admin_users_editor_p{st.session_state.usr_page_num}",
                column_config={
                    "username": "用户名", "role": "角色权限", "last_date": "最后活跃/重置日期",
                    "spider_count": "爬虫已用次数", "ai_count": "AI已用次数", "dl_count": "下载已用次数"
                }
            )

            st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
            st.markdown('<span class="admin-fix-marker"></span>', unsafe_allow_html=True)

            if st.button(f":material/check_circle: 确认并覆盖第 {st.session_state.usr_page_num} 页的用户数据",
                         type="primary", key="save_users_btn", width="stretch"):
                db_manager.sync_users_admin(edited_users, page_df_u)
                st.toast("本页用户数据同步完成！")
                st.rerun()  # 保存数据后进行全局刷新，以同步顶部的搜索状态


        # 调用这个 Fragment
        render_users_pagination_and_table(filtered_users_df)


    elif admin_module == ":material/history: 历史查询记录":

        st.subheader(":material/history: 全局商品追踪记录")

        # 1. 获取数据 (内存缓存拉取)

        df_stats = load_cached_stats().copy()

        # 2. 全局搜索栏 (左右并排的检索框)

        col_search1, col_search2, col_btn = st.columns([4, 4, 1])

        with col_search1:

            search_uid = st.text_input("筛选用户ID", placeholder=" 筛选用户 ID (模糊查询)",

                                       label_visibility="collapsed", key="search_stats_uid_input")

        with col_search2:

            search_pid = st.text_input("筛选商品ID或名称", placeholder=" 筛选商品 ID 或 名称 (模糊查询)",

                                       label_visibility="collapsed", key="search_stats_pid_input")

        with col_btn:
            st.button(":material/search: 搜索", key="btn_stats_search", type="primary", width="stretch")

        # 3. 向量化极速过滤

        filtered_df = df_stats.copy()

        if search_uid:
            filtered_df = filtered_df[
                filtered_df['user_id'].astype(str).str.contains(search_uid.strip(), case=False, na=False)]

        if search_pid:
            search_term_s = search_pid.strip()

            mask_s = (
                    filtered_df['product_id'].astype(str).str.contains(search_term_s, case=False, na=False) |
                    filtered_df['product_name'].astype(str).str.contains(search_term_s, case=False, na=False)
            )
            filtered_df = filtered_df[mask_s]

        # ======================
        # 4. 分页控制核心逻辑
        # ======================

        # ==========================================
        # 【极致流畅优化】：历史查询记录分页 Fragment 封装
        # ==========================================
        @st.fragment
        def render_stats_pagination_and_table(filtered_df):
            if 'stat_page_size' not in st.session_state: st.session_state.stat_page_size = 50
            if 'stat_page_num' not in st.session_state: st.session_state.stat_page_num = 1

            total_rows_s = len(filtered_df)
            total_pages_s = max(1, (total_rows_s - 1) // st.session_state.stat_page_size + 1)

            if st.session_state.stat_page_num > total_pages_s:
                st.session_state.stat_page_num = total_pages_s

            st.markdown("""
                    <style>
                        div[data-baseweb="popover"] li { margin: 0px !important; }
                    </style>
                    """, unsafe_allow_html=True)

            col_size_s, col_empty_s, col_prev_s, col_page_s, col_next_s = st.columns([1.5, 5.5, 0.8, 1.8, 0.8],
                                                                                     vertical_alignment="center")

            with col_size_s:
                new_size_s = st.selectbox(
                    "单页显示条数", [50, 100, 200, 500],
                    index=[50, 100, 200, 500].index(st.session_state.stat_page_size),
                    format_func=lambda x: f"每页 {x} 条", key="stat_size_selector", label_visibility="collapsed"
                )
                if new_size_s != st.session_state.stat_page_size:
                    st.session_state.stat_page_size = new_size_s
                    st.session_state.stat_page_num = 1
                    st.rerun(scope="fragment")  # 局部刷新

            with col_prev_s:
                if st.button("⬅", width="stretch", disabled=st.session_state.stat_page_num <= 1,
                             key="btn_stat_prev"):
                    st.session_state.stat_page_num -= 1
                    st.rerun(scope="fragment")

            with col_page_s:
                new_page_s = st.selectbox(
                    "跳转页码", options=list(range(1, total_pages_s + 1)),
                    index=st.session_state.stat_page_num - 1,
                    format_func=lambda x: f"第 {x} / {total_pages_s} 页", key="stat_page_selector",
                    label_visibility="collapsed"
                )
                if new_page_s != st.session_state.stat_page_num:
                    st.session_state.stat_page_num = new_page_s
                    st.rerun(scope="fragment")

            with col_next_s:
                if st.button("➡", width="stretch",
                             disabled=st.session_state.stat_page_num >= total_pages_s, key="btn_stat_next"):
                    st.session_state.stat_page_num += 1
                    st.rerun(scope="fragment")

            st.markdown(
                f"<div style='text-align:right; margin-top:-10px; margin-bottom: 5px; color:#94a3b8; font-size:13px;'>共匹配到 {total_rows_s} 条历史记录</div>",
                unsafe_allow_html=True)

            # 截取并渲染表格
            start_idx_s = (st.session_state.stat_page_num - 1) * st.session_state.stat_page_size
            end_idx_s = start_idx_s + st.session_state.stat_page_size
            page_df_s = filtered_df.iloc[start_idx_s:end_idx_s].copy()

            edited_stats = st.data_editor(
                page_df_s, num_rows="dynamic", disabled=["id", "user_id"], width="stretch",
                key=f"admin_stat_editor_p{st.session_state.stat_page_num}",
                column_config={
                    "user_id": None, "product_id": "商品 ID", "product_name": "商品名称",
                    "record_date": "记录日期", "sales_volume": "销量记录", "positive_rate": "综合 CBEI 记录分"
                }
            )

            # 保存与强制刷新缓存
            st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
            st.markdown('<span class="red-marker"></span>', unsafe_allow_html=True)

            if st.button(f":material/save: 确认覆盖第 {st.session_state.stat_page_num} 页的历史数据",
                         type="primary", key="save_stats_btn"):
                db_manager.sync_product_stats_admin(edited_stats, page_df_s)

                st.toast("本页历史查询数据已成功同步！")
                import time
                time.sleep(1)
                st.rerun()  # 提交数据库后全局刷新


        # 调用 Fragment
        render_stats_pagination_and_table(filtered_df)

    # ==========================================
    # Tab 3：CBEI 品类全局可视化大屏
    # ==========================================

    elif admin_module == ":material/bar_chart: CBEI 品类全局大盘":

        st.subheader(":material/monitoring: CBEI 跨品类注意力动态对比大屏")

        df_cbei = db_manager.get_cbei_dashboard_data()

        if df_cbei.empty:

            st.info("暂无数据，请先执行数据入库脚本。")


        else:

            # 【核心保留 1】：强制锁定 DataFrame 的列顺序，确保下方表格绝对一致

            col_order = ['category', '产品关注度', '服务关注度', '物流关注度', '价格关注度']

            existing_cols = [col for col in col_order if col in df_cbei.columns]

            df_cbei = df_cbei[existing_cols]

            # ==========================================

            # 🌟 Echarts 重构：数据结构准备

            # ==========================================

            import pandas as pd

            # 【核心保留 2】：强制按照你的品类顺序进行排序

            category_order = ['digital', 'lifestyle', 'snack', 'sports', 'general']

            # 利用 Pandas 的 Categorical 实现绝对顺序锁定

            df_cbei['category'] = pd.Categorical(df_cbei['category'], categories=category_order, ordered=True)

            df_sorted = df_cbei.sort_values('category')

            # 拆解出 Echarts 需要的纯列表数据

            categories = df_sorted['category'].tolist()

            # 1. 前三个维度正常执行独立的四舍五入
            prod_data = df_sorted['产品关注度'].round(2).tolist()
            serv_data = df_sorted['服务关注度'].round(2).tolist()
            logi_data = df_sorted['物流关注度'].round(2).tolist()

            # 2. 核心补齐策略：最后一个维度用减法兜底，吃掉所有浮点数舍入误差
            price_data = []
            for p, s, l in zip(prod_data, serv_data, logi_data):
                # 用 100 减去前三个，并再次 round(2) 防止 Python 出现 100 - 33.33 = 66.670000000001 的底层浮点数幽灵
                remainder = round(100.0 - (p + s + l), 2)

                # 防极端情况爆表（确保不会出现负数）
                remainder = max(0.0, remainder)
                price_data.append(remainder)

            # ==========================================

            # 🌟 Echarts 绝美簇状分组柱状图配置

            # ==========================================

            option_bar = {

                "backgroundColor": "transparent",

                "tooltip": {

                    "trigger": "axis",

                    "axisPointer": {

                        "type": "shadow"  # 绝美的灰色悬浮遮罩

                    }

                },

                "legend": {

                    # 严格按照你的维度顺序排列顶部图例

                    "data": ["产品关注度", "服务关注度", "物流关注度", "价格关注度"],

                    "top": "0%",

                    "left": "left",  # 图例靠左对齐，视觉更稳定

                    "textStyle": {"color": "#475569", "fontSize": 13}

                },

                "grid": {

                    "left": "3%",

                    "right": "4%",

                    "bottom": "5%",

                    "top": "12%",  # 给顶部图例留出空间

                    "containLabel": True

                },

                "xAxis": {

                    "type": "category",

                    "data": categories,

                    "axisLabel": {"color": "#94a3b8", "fontSize": 14},

                    "axisLine": {"lineStyle": {"color": "#cbd5e1"}},

                    "axisTick": {"show": False},

                    "name": "商品品类 (Category)",

                    "nameLocation": "middle",

                    "nameGap": 30,

                    "nameTextStyle": {"color": "#475569", "fontWeight": "bold", "fontSize": 13}

                },

                "yAxis": {

                    "type": "value",

                    "max": 100,  # 百分比锁死 100

                    "name": "CBEI 平均关注度 (%)",

                    "nameTextStyle": {"color": "#475569", "fontWeight": "bold", "padding": [0, 0, 0, 30]},

                    "axisLabel": {"color": "#94a3b8"},

                    "splitLine": {"lineStyle": {"color": "#f1f5f9", "type": "dashed"}}

                },

                "series": [

                    {

                        "name": "产品关注度",

                        "type": "bar",

                        "barGap": "15%",  # 簇状柱子内部的缝隙

                        "itemStyle": {"color": "#34d399", "borderRadius": [4, 4, 0, 0]},

                        "data": prod_data

                    },

                    {

                        "name": "服务关注度",

                        "type": "bar",

                        "itemStyle": {"color": "#fb923c", "borderRadius": [4, 4, 0, 0]},

                        "data": serv_data

                    },

                    {

                        "name": "物流关注度",

                        "type": "bar",

                        "itemStyle": {"color": "#60a5fa", "borderRadius": [4, 4, 0, 0]},

                        "data": logi_data

                    },

                    {

                        "name": "价格关注度",

                        "type": "bar",

                        "itemStyle": {"color": "#f472b6", "borderRadius": [4, 4, 0, 0]},

                        "data": price_data

                    }

                ]

            }

            # 渲染图表

            from streamlit_echarts import st_echarts

            st_echarts(options=option_bar, height="500px")

            # 底部保留数据表格展示

            st.markdown("##### 各品类详细关注度表")

            st.dataframe(df_cbei.style.format(precision=2), width="stretch")


    # ==========================================
    # Tab 4：核心商品元数据库 (内存缓存 + 完美兼容分页版)
    # ==========================================
    elif admin_module == ":material/inventory_2: 核心商品元数据库":
        st.subheader(":material/inventory_2: 商品主数据池管控")

        # 1. 获取数据 (直接从内存缓存拉取，极速加载)
        df_products = load_cached_products().copy()

        # 2. 全局搜索栏
        col_p_search1, col_p_btn = st.columns([8, 1])
        with col_p_search1:
            search_p_id = st.text_input("筛选商品ID、品类或标题",
                                        placeholder=" 模糊搜索商品 ID、品类或标题 (将同步过滤下方表格)",
                                        label_visibility="collapsed", key="search_p_id_input")
        with col_p_btn:
            st.button(":material/search: 搜索", key="btn_p_search", type="primary", width="stretch")

        # 3. 执行数据过滤 (C语言级向量化搜索)
        filtered_products_df = df_products.copy()

        if search_p_id:
            search_term_p = search_p_id.strip()
            mask_p = (
                    filtered_products_df['product_id'].astype(str).str.contains(search_term_p, case=False, na=False) |
                    filtered_products_df['category'].astype(str).str.contains(search_term_p, case=False, na=False) |
                    filtered_products_df['title'].astype(str).str.contains(search_term_p, case=False, na=False)
            )
            filtered_products_df = filtered_products_df[mask_p]

        # ======================
        # 4. 分页控制核心逻辑 (完美兼容版：左右箭头 + 下拉定位 + CSS修复)
        # ======================
        # ==========================================
        # 【极致流畅优化】：商品元数据库分页 Fragment 封装
        # ==========================================
        @st.fragment
        def render_products_pagination_and_table(filtered_df):
            if 'prod_page_size' not in st.session_state: st.session_state.prod_page_size = 50
            if 'prod_page_num' not in st.session_state: st.session_state.prod_page_num = 1

            total_rows_p = len(filtered_df)
            total_pages_p = max(1, (total_rows_p - 1) // st.session_state.prod_page_size + 1)

            if st.session_state.prod_page_num > total_pages_p:
                st.session_state.prod_page_num = total_pages_p

            st.markdown("""
                    <style>
                    div[data-baseweb="popover"] li { margin: 0px !important; }
                    </style>
                    """, unsafe_allow_html=True)

            col_size_p, col_empty_p, col_prev_p, col_page_p, col_next_p = st.columns([1.5, 5.5, 0.8, 1.8, 0.8],
                                                                                     vertical_alignment="center")

            with col_size_p:
                new_size_p = st.selectbox(
                    "单页显示条数", [50, 100, 200, 500],
                    index=[50, 100, 200, 500].index(st.session_state.prod_page_size),
                    format_func=lambda x: f"每页 {x} 条", key="prod_size_selector", label_visibility="collapsed"
                )
                if new_size_p != st.session_state.prod_page_size:
                    st.session_state.prod_page_size = new_size_p
                    st.session_state.prod_page_num = 1
                    st.rerun(scope="fragment")

            with col_prev_p:
                if st.button("⬅", width="stretch", disabled=st.session_state.prod_page_num <= 1,
                             key="btn_prod_prev"):
                    st.session_state.prod_page_num -= 1
                    st.rerun(scope="fragment")

            with col_page_p:
                new_page_p = st.selectbox(
                    "跳转页码", options=list(range(1, total_pages_p + 1)),
                    index=st.session_state.prod_page_num - 1,
                    format_func=lambda x: f"第 {x} / {total_pages_p} 页", label_visibility="collapsed"
                )
                if new_page_p != st.session_state.prod_page_num:
                    st.session_state.prod_page_num = new_page_p
                    st.rerun(scope="fragment")

            with col_next_p:
                if st.button("➡", width="stretch",
                             disabled=st.session_state.prod_page_num >= total_pages_p, key="btn_prod_next"):
                    st.session_state.prod_page_num += 1
                    st.rerun(scope="fragment")

            st.markdown(
                f"<div style='text-align:right; margin-top:-10px; margin-bottom: 5px; color:#94a3b8; font-size:13px;'>共匹配到 {total_rows_p} 条商品数据</div>",
                unsafe_allow_html=True)

            # 截取当前页数据并渲染
            start_idx_p = (st.session_state.prod_page_num - 1) * st.session_state.prod_page_size
            end_idx_p = start_idx_p + st.session_state.prod_page_size
            page_df_p = filtered_df.iloc[start_idx_p:end_idx_p].copy()

            edited_products = st.data_editor(
                page_df_p, num_rows="dynamic", width="stretch",
                key=f"admin_products_editor_p{st.session_state.prod_page_num}",
                column_config={
                    "title": st.column_config.TextColumn("商品标题", width="large"),
                    "product_url": st.column_config.TextColumn("购买链接", width="medium"),
                    "shop_name": st.column_config.TextColumn("店铺名称", width="medium"),
                }
            )

            # 保存按钮与缓存清除
            st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
            st.markdown('<span class="red-marker"></span>', unsafe_allow_html=True)

            if st.button(f":material/save: 确认覆盖第 {st.session_state.prod_page_num} 页的商品主表",
                         type="primary", key="save_master_btn"):
                db_manager.sync_ecommerce_products(edited_products, page_df_p)
                st.toast("本页商品库修改已成功同步！")
                import time
                time.sleep(1)
                st.rerun()  # 提交数据库后全局刷新


        # 调用 Fragment
        render_products_pagination_and_table(filtered_products_df)

    # ==========================================
    # Tab 5：AI 打分评论明细库
    # ==========================================
    elif admin_module == ":material/forum: AI 打分评论明细库":
        # ==========================================================
        # 新增：定义独立的数据录入弹窗
        # ==========================================================
        @st.dialog(":material/add_comment: 手动录入新评论")
        def add_comment_dialog():
            st.markdown(":material/info: 请在下方填写数据，系统将自动进行去重并入库：")

            with st.form("new_comment_form", clear_on_submit=True):
                new_pid = st.text_input("关联商品 ID *", placeholder="例如: 807387608223")
                new_content = st.text_area("用户原始评论 *", placeholder="请输入详细的评论正文...", height=150)

                # 提交按钮
                submitted = st.form_submit_button("确认并写入数据库", type="primary", width="stretch")

                if submitted:
                    if not new_pid.strip() or not new_content.strip():
                        st.error(":material/error: 商品 ID 和评论内容不能为空！")
                    else:
                        # 借用你写好的现成函数直接入库！(自带去重和 NULL 占位)
                        db_manager.batch_save_scraped_comments(new_pid.strip(), [new_content.strip()])


                        st.success(":material/check_circle: 数据添加成功！")
                        import time
                        time.sleep(0.8)  # 停顿一下让用户看到成功提示
                        st.rerun()  # 刷新页面关闭弹窗


        # ==========================================================

        st.subheader(":material/forum: AI 结构化评论语料库")
        if 'editor_reset_key' not in st.session_state:
            st.session_state.editor_reset_key = 0

            # 2. 闪存消息接收器（代替极度卡顿的 time.sleep）
        if 'flash_warning' in st.session_state:
            st.warning(st.session_state.flash_warning)
            del st.session_state.flash_warning  # 显示完立刻阅后即焚
        if 'flash_success' in st.session_state:
            st.success(st.session_state.flash_success)
            del st.session_state.flash_success
        # ==========================================================

        # 1. 获取数据并做底层关联
        df_comments = load_cached_comments_with_category().copy()
        df_products = load_cached_products().copy()

        if not df_comments.empty and not df_products.empty:
            df_comments['product_id'] = df_comments['product_id'].astype(str)
            df_products['product_id'] = df_products['product_id'].astype(str)
            if 'category' not in df_comments.columns:
                df_comments = df_comments.merge(df_products[['product_id', 'category']], on='product_id',
                                                how='left')
                df_comments['category'] = df_comments['category'].fillna('general')
        else:
            if 'category' not in df_comments.columns:
                df_comments['category'] = 'general'

        # 2. 品类独立切换器
        st.markdown("<div style='margin-bottom: 15px;'>", unsafe_allow_html=True)
        cat_filter = st.radio(
            "品类筛选",
            [
                ":material/apps: 全部大类",
                ":material/devices: 数码 (Digital)",
                ":material/living: 生活用品 (Lifestyle)",
                ":material/icecream: 零食 (Snack)",
                ":material/directions_run: 运动 (Sports)"
            ],
            horizontal=True,
            label_visibility="collapsed",
            key="comment_cat_filter"
        )
        st.markdown("</div>", unsafe_allow_html=True)

        # 3. 全局搜索栏
        col_c_search1, col_c_btn = st.columns([8, 1])
        with col_c_search1:
            search_c_id = st.text_input("筛选商品ID或内容",
                                        placeholder=" 模糊搜索商品 ID 或 评论关键字 (将同步过滤下方表格与图表)",
                                        label_visibility="collapsed", key="search_c_id_input")
        with col_c_btn:
            st.button(":material/search: 搜索", key="btn_c_search", type="primary", width="stretch")

        # 4. 执行数据过滤 (★★ 解决严重卡顿的核心优化区域 ★★)
        filtered_comments_df = df_comments.copy()

        if "全部大类" not in cat_filter:
            cat_map = {
                ":material/devices: 数码 (Digital)": "digital",
                ":material/living: 生活用品 (Lifestyle)": "lifestyle",
                ":material/icecream: 零食 (Snack)": "snack",
                ":material/directions_run: 运动 (Sports)": "sports"
            }
            target_cat = cat_map[cat_filter]
            filtered_comments_df = filtered_comments_df[filtered_comments_df['category'].str.lower() == target_cat]

        if search_c_id:
            search_term = search_c_id.strip()
            # 【核心提速魔法】：废弃 apply(axis=1) 循环，改用 Pandas C语言级的底层向量化掩码！
            # 性能提升约 100 倍，1万多条数据瞬间出结果！
            # 【终极修复】：强制 regex=False，让系统把所有特殊符号(*, (, 等)都当成普通文字处理！
            mask = (
                    filtered_comments_df['product_id'].astype(str).str.contains(search_term, case=False, na=False,
                                                                                regex=False) |
                    filtered_comments_df['content'].astype(str).str.contains(search_term, case=False, na=False,
                                                                             regex=False)
            )
            filtered_comments_df = filtered_comments_df[mask]

        # ======================
        # 5. 分页控制核心逻辑 (完美兼容版：左右箭头 + 下拉定位 + CSS修复)
        # ======================
        # ==========================================
        # 【极致流畅优化】：评论明细库全区域 Fragment 封装 (含表格与轮播)
        # ==========================================
        @st.fragment
        def render_comments_section(filtered_df, cat_filter_value):
            if 'cmt_page_size' not in st.session_state: st.session_state.cmt_page_size = 50
            if 'cmt_page_num' not in st.session_state: st.session_state.cmt_page_num = 1

            total_rows = len(filtered_df)
            total_pages = max(1, (total_rows - 1) // st.session_state.cmt_page_size + 1)

            if st.session_state.cmt_page_num > total_pages:
                st.session_state.cmt_page_num = total_pages

            st.markdown("""
                    <style>
                    div[data-baseweb="popover"] li { margin: 0px !important; }
                    </style>
                    """, unsafe_allow_html=True)

            col_size, col_btn_add, col_empty, col_prev, col_page, col_next = st.columns(
                [1.5, 1.5, 4.0, 0.8, 1.8, 0.8], vertical_alignment="center")

            with col_size:
                new_size = st.selectbox(
                    "单页显示条数", [50, 100, 200, 500],
                    index=[50, 100, 200, 500].index(st.session_state.cmt_page_size),
                    format_func=lambda x: f"每页 {x} 条", label_visibility="collapsed"
                )
                if new_size != st.session_state.cmt_page_size:
                    st.session_state.cmt_page_size = new_size
                    st.session_state.cmt_page_num = 1
                    st.rerun(scope="fragment")

            with col_btn_add:
                # 弹窗逻辑独立在系统层，点击会正常浮出
                if st.button(":material/add_box: 新增录入", type="primary", width="stretch"):
                    add_comment_dialog()

            with col_prev:
                if st.button(":material/arrow_back:", width="stretch",
                             disabled=st.session_state.cmt_page_num <= 1):
                    st.session_state.cmt_page_num -= 1
                    st.rerun(scope="fragment")

            with col_page:
                new_page = st.selectbox(
                    "跳转页码", options=list(range(1, total_pages + 1)),
                    index=st.session_state.cmt_page_num - 1,
                    format_func=lambda x: f"第 {x} / {total_pages} 页", label_visibility="collapsed"
                )
                if new_page != st.session_state.cmt_page_num:
                    st.session_state.cmt_page_num = new_page
                    st.rerun(scope="fragment")

            with col_next:
                if st.button(":material/arrow_forward:", width="stretch",
                             disabled=st.session_state.cmt_page_num >= total_pages):
                    st.session_state.cmt_page_num += 1
                    st.rerun(scope="fragment")

            st.markdown(
                f"<div style='text-align:right; margin-top:-10px; margin-bottom: 5px; color:#94a3b8; font-size:13px;'>共匹配到 {total_rows} 条数据</div>",
                unsafe_allow_html=True)

            start_idx = (st.session_state.cmt_page_num - 1) * st.session_state.cmt_page_size
            end_idx = start_idx + st.session_state.cmt_page_size
            page_df = filtered_df.iloc[start_idx:end_idx].copy()

            edited_comments = st.data_editor(
                page_df, num_rows="fixed", disabled=["id", "category"], width="stretch",
                key=f"admin_comments_editor_p{st.session_state.cmt_page_num}_{cat_filter_value}_{st.session_state.editor_reset_key}",
                column_config={
                    "content": st.column_config.TextColumn("用户原始评论", width="large"),
                    "product_id": st.column_config.TextColumn("商品 ID", width="small"),
                    "category": st.column_config.TextColumn("所属品类", width="small")
                }
            )

            st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

            # ======================
            # 嵌套的评论轮播区 Fragment
            # ======================
            if filtered_df.empty:
                st.info("当前筛选条件下暂无图表分析数据。")
            else:
                total_cmts_carousel = len(filtered_df)
                if 'admin_carousel_idx' not in st.session_state:
                    st.session_state.admin_carousel_idx = 0
                    st.session_state.skip_auto_inc = True

                def go_prev_carousel():
                    st.session_state.admin_carousel_idx = (
                                                                      st.session_state.admin_carousel_idx - 1) % total_cmts_carousel
                    st.session_state.skip_auto_inc = True

                def go_next_carousel():
                    st.session_state.admin_carousel_idx = (
                                                                      st.session_state.admin_carousel_idx + 1) % total_cmts_carousel
                    st.session_state.skip_auto_inc = True

                @st.fragment(run_every=8)
                def render_carousel_fragment():
                    if st.session_state.get('skip_auto_inc', False):
                        st.session_state.skip_auto_inc = False
                        idx = st.session_state.admin_carousel_idx % total_cmts_carousel
                    else:
                        idx = (st.session_state.admin_carousel_idx + 1) % total_cmts_carousel
                        st.session_state.admin_carousel_idx = idx

                    col_prev_c, col_page_c, col_next_c = st.columns([1, 3, 1])
                    with col_prev_c:
                        st.button("⬅ 上一条", on_click=go_prev_carousel, width="stretch",
                                  key="btn_prev_carousel")
                    with col_next_c:
                        st.button("➡ 下一条", on_click=go_next_carousel, width="stretch",
                                  key="btn_next_carousel")
                    with col_page_c:
                        st.markdown(
                            f"<div style='text-align:center; font-weight:bold; margin-top:8px; color:#475569;'>抽样分析中：该类目第 {idx + 1} / {total_cmts_carousel} 条</div>",
                            unsafe_allow_html=True)

                    current_cmt = filtered_df.iloc[idx]
                    with st.container(border=True):
                        col_text, col_chart = st.columns([1.8, 1])
                        with col_text:
                            st.markdown(
                                f"**绑定商品 ID:** `{current_cmt['product_id']}` &nbsp;|&nbsp; :material/label: **{current_cmt.get('category', 'general').upper()}**")
                            full_content = str(current_cmt['content'])
                            short_content = full_content[:150] + "..." if len(full_content) > 150 else full_content
                            st.markdown(f"> “ {short_content} ”")

                        with col_chart:
                            import pandas as pd
                            import altair as alt
                            plot_data = pd.DataFrame({
                                '维度': ['产品', '服务', '物流', '价格'],
                                '关注度': [
                                    current_cmt['score_product'], current_cmt['score_service'],
                                    current_cmt['score_logistics'], current_cmt['score_price']
                                ]
                            })
                            chart = alt.Chart(plot_data).mark_bar(cornerRadiusEnd=4, clip=False).encode(
                                x=alt.X('关注度:Q', title='注意力占比 (%)', scale=alt.Scale(domain=[0, 100]),
                                        axis=alt.Axis(format='.0f')),
                                y=alt.Y('维度:N', title='', sort=None),
                                color=alt.Color('维度:N', scale=alt.Scale(scheme='set2'), legend=None),
                                tooltip=['维度', '关注度']
                            ).properties(height=160, background='transparent',
                                         padding={'left': 5, 'right': 25, 'top': 5, 'bottom': 5})
                            st.altair_chart(chart, width="stretch", theme=None)

                render_carousel_fragment()

            # 保存按钮逻辑
            st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
            st.markdown('<span class="red-marker"></span>', unsafe_allow_html=True)

            if st.button(f":material/save: 确认覆盖第 {st.session_state.cmt_page_num} 页的 AI 评论数据",
                         type="primary", key="save_comments_btn"):
                score_cols = ['score_product', 'score_service', 'score_logistics', 'score_price']
                for col in score_cols:
                    edited_comments[col] = pd.to_numeric(edited_comments[col], errors='coerce')

                scored_mask = edited_comments[score_cols].notna().any(axis=1)
                invalid_ids = []

                for index, row in edited_comments[scored_mask].iterrows():
                    total_score = row[score_cols].fillna(0).sum()
                    if abs(total_score - 100.0) > 0.1:
                        invalid_id = str(int(row['id'])) if pd.notna(row['id']) else "新增异常行"
                        invalid_ids.append(invalid_id)
                        edited_comments.loc[index, score_cols] = page_df.loc[index, score_cols]

                try:
                    db_manager.sync_ecommerce_comments(edited_comments, page_df)

                    if invalid_ids:
                        st.session_state.flash_warning = f":material/history: **检测到异常，已自动回滚！** ID 为 **{', '.join(invalid_ids)}** 的数据因总和不等于 100 已被丢弃。表格已恢复至修改前的状态。"
                    else:
                        st.session_state.flash_success = ":material/check_circle: 数据严密校验通过，全量成功覆写至底层数据库！"

                    st.session_state.editor_reset_key += 1
                    st.rerun()  # 全局刷新
                except Exception as e:
                    st.error(f":material/error: 写入数据库时发生致命异常：{e}")


        # 调用总 Fragment
        render_comments_section(filtered_comments_df, cat_filter)

    # =========================================================
    # 【重点注意】st.stop() 的位置必须顶格！！！
    # =========================================================
    st.stop()

st.title("基于AI的电商平台客户购买体验分析系统")

for key in ['last_query', 'product_info', 'report_single_model', 'report_market_model', 'report_comp_model']:
    if key not in st.session_state: st.session_state[key] = ""
if 'df_result' not in st.session_state: st.session_state.df_result = None
if 'analysis_type' not in st.session_state: st.session_state.analysis_type = None
if 'comp_comments' not in st.session_state: st.session_state.comp_comments = []
for key in ['report_single', 'report_market', 'report_comp']:
    if key not in st.session_state: st.session_state[key] = None
if 'processing_comp' not in st.session_state: st.session_state.processing_comp = False
def can_use_spider():
    if role == '管理员': return True
    if role == '客户' and spider_cnt >= 3: return False
    if role == '商家' and spider_cnt >= 10: return False
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
st.markdown("### :material/search: 目标商品搜索")
col_input, col_btn = st.columns([5, 1], vertical_alignment="bottom")
with col_input:
    user_input = st.text_input("输入框", placeholder="粘贴天猫/淘宝链接 或 输入关键词...",
                               label_visibility="collapsed")
with col_btn:
    start_analysis = st.button(":material/search_check_2: 立即分析", type="primary", width="stretch", disabled=not can_use_spider())
def is_url(text):
    return re.search(r'(http|https|tmall\.com|taobao\.com)', text)
def extract_product_id(url):
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if 'id' in params:
            return params['id'][0]
    except:
        pass
    return "未知ID"


# 加上这行缓存代码，让同样的词汇字典不再重复计算！
@st.cache_data(show_spinner=False, ttl=3600, max_entries=50)
def generate_wordcloud_image(word_freq_dict, theme='positive', word_hue_map=None, target_hue=None):
    """直接接收 AI 提取的词频字典画图，支持动态 HSL 染色（频率越高，颜色越深）"""
    sys_type = platform.system()
    if sys_type == "Windows":
        font_path = "C:/Windows/Fonts/simhei.ttf"
    elif sys_type == "Darwin":
        font_path = "/System/Library/Fonts/PingFang.ttc"
    else:
        font_path = None

    wc = WordCloud(
        font_path=font_path,
        width=1000, height=400,
        scale=2,
        mode="RGBA",
        background_color=None,
        max_words=100
    ).generate_from_frequencies(word_freq_dict)

    current_font_sizes = [v[1] for v in wc.layout_]
    if current_font_sizes:
        max_font = max(current_font_sizes)
        min_font = min(current_font_sizes)
    else:
        max_font = 100
        min_font = 10

    def dynamic_hsl_color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        if max_font == min_font:
            normalized_size = 1.0
        else:
            normalized_size = (font_size - min_font) / (max_font - min_font)

        # 获取该维度对应的基础色相 (Hue)
        if target_hue is not None:
            hue = target_hue
        elif word_hue_map and word in word_hue_map:
            hue = word_hue_map[word]
        else:
            hue = 120 if theme == 'positive' else 0

        # ==========================================
        # 🌟 核心修改：通过 theme 参数区分正面与负面的色彩质感
        # ==========================================
        if theme == 'positive':
            # 【正面词云】：鲜艳、明快
            # 饱和度高 (85%)，亮度保持在 30% ~ 65% 之间
            saturation = 85
            lightness = 65 - (normalized_size * 35)
        else:
            # 【负面词云】：沉重、暗淡、痛点感
            # 饱和度降低 (50%) 增加灰暗感，亮度整体调暗 (15% ~ 45%)
            saturation = 50
            lightness = 45 - (normalized_size * 30)

        return f"hsl({hue}, {saturation}%, {int(lightness)}%)"

    wc.recolor(color_func=dynamic_hsl_color_func)

    return wc.to_image()

def _update_wordclouds(data, pos_data, neg_data):
    """辅助函数4.0：递归查找+极致模糊匹配键名，专治各种嵌套和奇葩命名"""
    if isinstance(data, list):
        for item in data:
            _update_wordclouds(item, pos_data, neg_data)
        return
    if not isinstance(data, dict):
        return
    for k, v in data.items():
        k_lower = str(k).lower()
        target = None
        if any(w in k_lower for w in ["positive", "好评", "正面", "优点", "优势", "亮点", "满意", "好词"]):
            target = pos_data
        elif any(w in k_lower for w in
                 ["negative", "差评", "痛点", "缺点", "劣势", "不足", "抱怨", "吐槽", "负面", "坏词"]):
            target = neg_data
        if target is not None:
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    try:
                        target[str(sub_k)] = float(sub_v)
                    except:
                        pass
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        keys = list(item.keys())
                        if len(keys) >= 2:
                            try:
                                target[str(item[keys[0]])] = float(item[keys[1]])
                            except:
                                pass
                        elif len(keys) == 1:
                            try:
                                target[str(keys[0])] = float(item[keys[0]])
                            except:
                                pass
        else:
            if isinstance(v, (dict, list)):
                _update_wordclouds(v, pos_data, neg_data)
def extract_dual_wordclouds(text):
    """终极鲁棒提取器 4.1：增加对 AI '平铺输出' 的兜底识别"""
    pos_data, neg_data = {}, {}
    blocks_to_try = []
    blocks_to_try.extend(re.findall(r'`{3}(?:json)?\s*(.*?)\s*`{3}', text, re.DOTALL | re.IGNORECASE))
    start_idx = 0
    while True:
        start = text.find('{', start_idx)
        if start == -1: break
        depth, in_string, escape, end = 0, False, False, -1
        for i in range(start, len(text)):
            char = text[i]
            if escape: escape = False; continue
            if char == '\\': escape = True; continue
            if char == '"': in_string = not in_string; continue
            if not in_string:
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        end = i;
                        break
        if end != -1:
            blocks_to_try.append(text[start:end + 1])
            start_idx = end + 1
        else:
            start_idx = start + 1
    flat_dicts = []
    for block in blocks_to_try:
        block = block.strip()
        if not block: continue
        try:
            data = json.loads(block)
            _update_wordclouds(data, pos_data, neg_data)
            if isinstance(data, dict) and len(data) > 0:
                is_flat = True
                for v in data.values():
                    if not (isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.', '', 1).isdigit())):
                        is_flat = False
                        break
                if is_flat:
                    flat_dicts.append({str(k): float(v) for k, v in data.items()})
        except json.JSONDecodeError:
            try:
                fixed_block = "{" + block + "}" if not block.startswith("{") else block
                data = json.loads(fixed_block)
                _update_wordclouds(data, pos_data, neg_data)
            except:
                pass
    if not pos_data and not neg_data and len(flat_dicts) > 0:
        if len(flat_dicts) >= 1:
            pos_data.update(flat_dicts[0])
        if len(flat_dicts) >= 2:
            neg_data.update(flat_dicts[1])
    return pos_data, neg_data


def show_breathing_loading(text):
    """
    方案二：行业干货轮播 + 呼吸灯 Logo
    利用纯 CSS 实现高性能文字平滑切换，提升等待期间的专业感知。
    """
    placeholder = st.empty()

    # 定义轮播的干货内容（你可以根据业务随时修改这些文案）
    insights = [
        "CBEI 洞察：产品维度的关注度权重通常占据总分的 65% 以上，是品牌忠诚度的核心。",
        "行业基准：数码品类的物流投诉率若高于 15%，将直接导致次月复购率下降 8.2%。",
        "算法逻辑：系统正在通过 NLP 神经网络，对评论中的隐含情感进行多维矢量化建模。",
        "体验优化：优先修复玫瑰图中半径最大的『痛点扇区』，通常能获得最高的 ROI 回报。",
        "价值预警：价格关注度过高往往意味着产品同质化严重，需加强服务维度的差异化建设。"
    ]

    img_html = '<img src="/app/static/logo4.png" style="width: 100%; height: 100%; object-fit: contain;">'

    # 构造 CSS 动画
    # pulse: 呼吸灯效果
    # slide: 轮播文字切换效果
    html_content = f'''
    <style>
        .loading-container {{
            text-align: center;
            padding: 40px 20px;
            background-color: rgba(255, 255, 255, 0.4);
            border-radius: 12px;
            border: 1px solid rgba(161, 196, 253, 0.2);
            margin-bottom: 25px;
        }}

        .breathing-logo {{
            width: 100px;
            height: 100px;
            margin: 0 auto;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            background-color: #ffffff;
            box-shadow: 0 0 20px rgba(123, 158, 214, 0.2);
            animation: pulse-app 2s infinite ease-in-out;
            border: 2px solid #f0f4f8;
        }}

        @keyframes pulse-app {{
            0% {{ transform: scale(0.98); box-shadow: 0 0 5px rgba(123, 158, 214, 0.2); }}
            50% {{ transform: scale(1.05); box-shadow: 0 0 25px rgba(123, 158, 214, 0.5); }}
            100% {{ transform: scale(0.98); box-shadow: 0 0 5px rgba(123, 158, 214, 0.2); }}
        }}

        .main-status {{
            margin-top: 25px;
            color: #475569;
            font-weight: bold;
            font-size: 15px;
            letter-spacing: 1px;
        }}

        .insight-carousel {{
            margin-top: 15px;
            height: 40px;
            overflow: hidden;
            position: relative;
        }}

        .insight-text {{
            position: absolute;
            width: 100%;
            opacity: 0;
            color: #7B9ED6;
            font-size: 13px;
            line-height: 1.5;
            animation: rotate-insight 20s infinite;
        }}

        /* 5条文案，每条分配 4秒 (20s / 5) */
        .insight-text:nth-child(1) {{ animation-delay: 0s; }}
        .insight-text:nth-child(2) {{ animation-delay: 4s; }}
        .insight-text:nth-child(3) {{ animation-delay: 8s; }}
        .insight-text:nth-child(4) {{ animation-delay: 12s; }}
        .insight-text:nth-child(5) {{ animation-delay: 16s; }}

        @keyframes rotate-insight {{
            0%   {{ opacity: 0; transform: translateY(10px); }}
            5%   {{ opacity: 1; transform: translateY(0); }}
            20%  {{ opacity: 1; transform: translateY(0); }}
            25%  {{ opacity: 0; transform: translateY(-10px); }}
            100% {{ opacity: 0; }}
        }}
    </style>

    <div class="loading-container">
        <div class="breathing-logo">{img_html}</div>
        <div class="main-status">{text}</div>
        <div class="insight-carousel">
            <div class="insight-text">{insights[0]}</div>
            <div class="insight-text">{insights[1]}</div>
            <div class="insight-text">{insights[2]}</div>
            <div class="insight-text">{insights[3]}</div>
            <div class="insight-text">{insights[4]}</div>
        </div>
    </div>
    '''
    placeholder.markdown(html_content, unsafe_allow_html=True)
    return placeholder


def fetch_multiple_spiders(links, show_progress=False):
    """通用的多线程爬虫提取逻辑，并在底层自动将所有抓取到的竞品/市场数据入库"""
    all_comments = []
    progress_bar = st.progress(0) if show_progress else None

    def task_wrapper(args):
        link, idx = args
        time.sleep(random.uniform(1.5, 5.0))
        # 核心：不仅返回结果，把链接也带出来，方便提取商品 ID
        return run_spider(link, worker_id=idx + 1), link

    task_args = [(link, i) for i, link in enumerate(links)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(links)) as executor:
        results = list(executor.map(task_wrapper, task_args))

    saved_total_count = 0  # 记录总计入库了多少条

    for i, (res_tuple, original_link) in enumerate(results):
        if show_progress and progress_bar:
            progress_bar.progress((i + 1) / len(links))

        # 1. 防御性解包：确保爬虫正常返回了三个值，防止直接解包崩溃
        if not isinstance(res_tuple, (tuple, list)) or len(res_tuple) != 3:
            print(f"爬虫返回值异常，链接: {original_link}")
            continue

        res_file, title, sales_vol = res_tuple

        # 2. 检查爬虫是否明确宣告失败
        if not res_file or "Error" in str(res_file):
            print(f"该链接抓取失败或被网站拦截: {original_link}")
            continue

        # 3. 数据解析与入库，抓取真实异常
        try:
            c_df = pd.read_csv(res_file, encoding='utf-8-sig')

            # 处理日期逻辑
            if 'date' in c_df.columns:
                c_df['date_clean'] = c_df['date'].astype(str).str.strip().str.lower()
                c_df = c_df[~c_df['date_clean'].isin(['nan', 'none', '', 'nat', 'null'])]
            else:
                c_df['date'] = '未知'  # 如果某平台没抓到日期，兜底补齐

            if 'content' not in c_df.columns or c_df.empty:
                print(f"CSV文件为空或缺少'content'列: {res_file}")
                continue  # 跳过这个无效文件，不执行入库

            # 核心修改：转化为包含 content 和 date 的字典列表
            c_df_valid = c_df.dropna(subset=['content']).copy()
            new_cmts_dict_list = c_df_valid[['content', 'date']].to_dict('records')

            pid = extract_product_id(original_link)
            if pid != "未知ID":

                # 入库商品信息
                try:
                    db_manager.insert_ecommerce_product(
                        product_id=pid, title=title, category=None,
                        price=None, province=None, city=None,
                        sales=sales_vol, product_url=original_link
                    )
                except Exception as db_e:
                    pass  # 不打断主流程

                # 入库评论数据 (传入字典列表！)
                saved_total_count += db_manager.batch_save_scraped_comments(pid, new_cmts_dict_list)

                # 拉取历史数据 (经过第1步修改，这里拉出来的已经是字典列表了)
                full_product_cmts = db_manager.get_all_comments_by_product(pid)
                all_comments.extend(full_product_cmts)
            else:
                # 兜底追加
                all_comments.extend(new_cmts_dict_list)

        except Exception as e:
            # 核心修改：绝对不能 pass，必须把具体的报错暴露出来！
            st.error(f"解析数据或入库时发生异常: {str(e)}\n来源文件: {res_file}")

    if show_progress and progress_bar:
        progress_bar.empty()

    if saved_total_count > 0:
        st.toast(f"底层数据库同步完毕：已将 {saved_total_count} 条竞品/市场数据入库沉淀。")

    return all_comments

def clean_ai_report_text(report_text):
    """专门用于清洗 AI 报告正文，切除末尾的 JSON 数据，防止在前端暴露残缺代码"""
    # 寻找 JSON 的核心特征标识并从这里一刀切断
    match = re.search(r'\{\s*"category"', report_text)
    if match:
        report_text = report_text[:match.start()].strip()

    # 容错：去除尾部可能残留的 Markdown 代码块标记
    # (使用 `{3}` 语法代替连续的三个反引号，避免解析冲突)
    report_text = re.sub(r'`{3}(?:json)?\s*$', '', report_text).strip()

    return report_text


def parse_and_display_report(report_text):
    """解析 AI 报告中的 think 标签并渲染，同时彻底切除末尾的 JSON 代码"""
    clean_report = report_text
    think_content = ""
    think_match = re.search(r'<think>(.*?)</think>', clean_report, flags=re.DOTALL | re.IGNORECASE)

    if think_match:
        think_content = think_match.group(1).strip()
        clean_report = re.sub(r'<think>.*?</think>\n*', '', clean_report, flags=re.DOTALL | re.IGNORECASE)
    else:
        alt_match = re.search(r'(.*?)(?=\n#|\n---)', clean_report, flags=re.DOTALL)
        if alt_match:
            think_content = alt_match.group(1).strip()
            clean_report = clean_report.replace(alt_match.group(0), "").strip()

    # ==========================================
    # 【新增】：在彻底清洗 JSON 之前，先把它截获出来！
    # ==========================================
    raw_json = ""
    json_match = re.search(r'\{\s*"category"[\s\S]*', clean_report)
    if json_match:
        raw_json = json_match.group(0)
        # 去掉尾部可能残留的反引号
        raw_json = re.sub(r'`{3}(?:json)?\s*$', '', raw_json).strip()

    # 【核心修改】：调用我们刚才写的强力清洗函数，一刀切除底部所有 JSON 及其残留物
    clean_report = clean_ai_report_text(clean_report)

    if think_content:
        with st.expander(" 查看 AI 深度思考逻辑", expanded=False):
            st.caption("以下是 AI 总结报告前的数据梳理与推演过程：")
            st.markdown(think_content)

    # 最后渲染出极其纯净的 Markdown 报告！
    st.markdown(clean_report.strip())

    # ==========================================
    # 【新增】：在报告的最底部，挂载开发者专属的 JSON 探查器
    # ==========================================
    if raw_json:
        with st.expander("🛠️ 查看 AI 原始 JSON 数据 (开发者/调试模式)", expanded=False):
            st.code(raw_json, language="json")


@st.cache_data(show_spinner=False, ttl=300)
def get_cached_cbei_data():
    """缓存 CBEI 大盘数据，防止每次渲染图表时都要去数据库做聚合计算"""
    return db_manager.get_cbei_dashboard_data()


# 1. 终极容错 JSON 提取与修复算法
def robust_json_parse(text):
        match = re.search(r'\{\s*"category"', text)
        if match:
            s = text[match.start():]
        else:
            start_idx = text.rfind('{')
            if start_idx == -1: return None
            s = text[start_idx:]
        if s.count('"') % 2 != 0: s += '"'
        s += ']' * max(0, s.count('[') - s.count(']'))
        s += '}' * max(0, s.count('{') - s.count('}'))
        # s = re.sub(r'\{\{+', '{', s)
        # s = re.sub(r'\}\}+', '}', s)
        s = re.sub(r',\s*\}', '}', s)
        s = re.sub(r',\s*\]', ']', s)
        s = re.sub(r':\s*\}', ': null}', s)
        try:
            return json.loads(s)
        except:
            return None

def render_report_visualizations(report_text, title_prefix="本品"):
    # ==========================================
    # 局部碎片化渲染
    # ==========================================
    @st.fragment
    def render_async_wordcloud(kw_dict, title, icon_name, theme, color_hex, target_hue):
        """
        利用 st.fragment 使得每个词云独立计算和渲染
        主程序不会因为某一个复杂的词云计算而阻塞整个页面
        """
        # 保持你之前的 Icon 和标题样式
        title_html = f"""
            <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded" rel="stylesheet">
            <div style='display: flex; align-items: center; justify-content: center; gap: 6px; color: {color_hex}; font-weight: bold; font-size: 16px; margin-bottom: 5px;'>
                <span class="material-symbols-rounded" style="font-size: 20px;">{icon_name}</span>
                <span>{title}</span>
            </div>
            """
        st.markdown(title_html, unsafe_allow_html=True)

        if kw_dict and len(kw_dict) > 0:
            # 渲染词云
            st.image(generate_wordcloud_image(kw_dict, theme=theme, target_hue=target_hue))
        else:
            st.markdown(
                f"<div style='height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; "
                f"color: #94a3b8; border: 2px dashed #e2e8f0; border-radius: 12px; margin-bottom: 15px; background-color: #f8fafc;'>"
                f"<span class='material-symbols-rounded' style='font-size: 32px; margin-bottom: 8px;'>check_circle</span>"
                f"<span style='font-size: 13px;'>该维度目前无评论样本</span></div>",
                unsafe_allow_html=True
            )


    st.markdown("---")


    data = robust_json_parse(report_text)
    if not data:
        st.error(":material/warning: 无法从 AI 报告中提取有效的 JSON 数据，图表渲染终止。")
        return

    category = data.get('category', 'general').lower()
    scores = data.get('scores', {})
    dims_data = data.get('dimensions_data', {})

    # 2. 动态获取真实的 CBEI 权重
    df_cbei = get_cached_cbei_data()
    weights = {'product': 70.0, 'service': 10.0, 'logistics': 10.0, 'price': 10.0}
    actual_category_used = category

    if not df_cbei.empty:
        cat_df = df_cbei[df_cbei['category'] == category]
        if cat_df.empty: cat_df = df_cbei[df_cbei['category'] == 'general']
        if not cat_df.empty:
            row = cat_df.iloc[0]
            weights = {'product': float(row['产品关注度']), 'service': float(row['服务关注度']),
                       'logistics': float(row['物流关注度']), 'price': float(row['价格关注度'])}

    # 3. 计算最终 CBEI 综合得分
    final_cbei = (scores.get('product', 50) * weights['product'] + scores.get('price', 50) * weights['price'] +
                  scores.get('service', 50) * weights['service'] + scores.get('logistics', 50) * weights[
                      'logistics']) / 100.0

    # ==========================================
    # 模块 1：品类 CBEI 关注度模型 (权重分布)
    # ==========================================
    # 映射品类为中文，提升 UI 友好度
    cat_cn_map = {'digital': '数码', 'lifestyle': '生活用品', 'snack': '零食', 'sports': '运动', 'general': '通用'}
    cat_cn = cat_cn_map.get(category, '通用')

    st.markdown(f"### :material/donut_small: 【{cat_cn}】品类 CBEI 关注度权重", unsafe_allow_html=True)
    st.caption(f"基于全网大数据分析得到的消费者对于{cat_cn}品类CBEI(产品，服务，物流，价格)各维度的关注权重")

    # === 新增：前端展示级的精度控制与二次误差补齐 ===
    w_prod = round(weights['product'], 1)
    w_ser = round(weights['service'], 1)
    w_log = round(weights['logistics'], 1)
    w_pri = round(weights['price'], 1)

    total_w = w_prod + w_ser + w_log + w_pri
    # 解决 UI 层的四舍五入引发的 99.9 或 100.1 问题
    if total_w != 100.0:
        diff = round(100.0 - total_w, 1)
        # 找到最大的权重，把由于四舍五入丢失/多出的 0.1 补给它
        max_key = max({'product': w_prod, 'service': w_ser, 'logistics': w_log, 'price': w_pri},
                      key=lambda k: {'product': w_prod, 'service': w_ser, 'logistics': w_log, 'price': w_pri}[k])
        if max_key == 'product':
            w_prod = round(w_prod + diff, 1)
        elif max_key == 'service':
            w_ser = round(w_ser + diff, 1)
        elif max_key == 'logistics':
            w_log = round(w_log + diff, 1)
        else:
            w_pri = round(w_pri + diff, 1)

    # 用完美处理后的 1位小数 覆盖原字典，供后续 HTML 和 玫瑰图调用
    weights = {'product': w_prod, 'service': w_ser, 'logistics': w_log, 'price': w_pri}

    # 动态面积缩放权重条 (增加 title 悬浮提示)
    weight_bar_html = (
        "<div style='width: 100%; height: 24px; border-radius: 12px; display: flex; overflow: hidden; box-shadow: inset 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 25px;'>\n"
        f"    <div title='产品关注度占比: {weights['product']}%' style='width: {weights['product']}%; background-color: #34d399; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold; cursor: pointer;'>产品 {weights['product']}%</div>\n"
        f"    <div title='价格关注度占比: {weights['price']}%' style='width: {weights['price']}%; background-color: #fb923c; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold; cursor: pointer;'>价格 </div>\n"
        f"    <div title='服务关注度占比: {weights['service']}%' style='width: {weights['service']}%; background-color: #60a5fa; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold; cursor: pointer;'>服务</div>\n"
        f"    <div title='物流关注度占比: {weights['logistics']}%' style='width: {weights['logistics']}%; background-color: #f472b6; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; font-weight: bold; cursor: pointer;'>物流</div>\n"
        "</div>"
    )
    st.markdown(weight_bar_html, unsafe_allow_html=True)

    # ==========================================
    # 模块 1.5：各维度体验得分与综合 CBEI 指数柱状图
    # ==========================================
    st.markdown("### :material/emoji_events: 各维度体验得分与综合 CBEI 指数")
    st.info(
        "**图表说明**：柱状图展示了 AI 基于语义情感计算的绝对满意度（满分100）。综合 CBEI 指数则是这四项得分结合【品类权重】的加权结果。")

    # 构建 Echarts 单列柱状图选项
    option_cbei_bar = {
        "backgroundColor": "transparent",
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": "3%", "right": "4%", "bottom": "5%", "top": "15%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": ['产品体验', '价格感受', '服务水平', '物流履约', '综合指数 (CBEI)'],
            "axisLabel": {"color": "#475569", "fontSize": 13, "interval": 0},
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": "#cbd5e1"}}
        },
        "yAxis": {
            "type": "value", "max": 100,
            "axisLabel": {"color": "#94a3b8"},
            "splitLine": {"lineStyle": {"color": "#f1f5f9", "type": "dashed"}}
        },
        "series": [{
            "type": "bar",
            "barWidth": "35%",  # 控制柱子粗细，更具呼吸感
            "itemStyle": {"borderRadius": [6, 6, 0, 0]},
            # 自动把顶部分数标出来，且颜色跟随柱子颜色
            "label": {"show": True, "position": "top", "color": "inherit", "fontWeight": "bold", "fontSize": 16},
            "data": [
                {"value": round(scores.get('product', 50), 1), "itemStyle": {"color": "#34d399"}},
                {"value": round(scores.get('price', 50), 1), "itemStyle": {"color": "#fb923c"}},
                {"value": round(scores.get('service', 50), 1), "itemStyle": {"color": "#60a5fa"}},
                {"value": round(scores.get('logistics', 50), 1), "itemStyle": {"color": "#f472b6"}},
                {"value": round(final_cbei, 1), "itemStyle": {"color": "#e11d48"}}
            ]
        }]
    }

    st_echarts(options=option_cbei_bar, height="350px")
    st.markdown("<br>", unsafe_allow_html=True)



    # ==========================================
    # 模块 A：分维度正面好评 2x2 矩阵
    # ==========================================
    st.markdown("### :material/thumb_up: CBEI正向体验词云 (2x2 好评矩阵)")
    st.info(
        "**图表说明**：词云中的【词语大小与颜色深浅】代表该优势/劣势的出现频率。正面情绪采用高亮鲜艳色，负面痛点采用低饱和沉闷色。")
    pos_r1c1, pos_r1c2 = st.columns(2)
    with pos_r1c1:
        render_async_wordcloud(dims_data.get('product', {}).get('positive_keywords', {}),
                              "产品体验优势", "inventory_2", "positive", "#34d399", 158)
    with pos_r1c2:
        render_async_wordcloud(dims_data.get('price', {}).get('positive_keywords', {}),
                              "价格感受优势", "payments", "positive", "#fb923c", 27)
    pos_r2c1, pos_r2c2 = st.columns(2)
    with pos_r2c1:
        render_async_wordcloud(dims_data.get('service', {}).get('positive_keywords', {}),
                              "服务水平优势", "support_agent", "positive", "#60a5fa", 213)
    with pos_r2c2:
        render_async_wordcloud(dims_data.get('logistics', {}).get('positive_keywords', {}),
                              "物流履约优势", "local_shipping", "positive", "#f472b6", 329)

    # ==========================================
    # 模块 B：分维度负面差评 2x2 矩阵
    # ==========================================
    st.markdown("---")
    st.markdown("### :material/thumb_down: CBEI负向体验词云 (2x2 差评矩阵)")
    neg_r1c1, neg_r1c2 = st.columns(2)
    with neg_r1c1:
        render_async_wordcloud(dims_data.get('product', {}).get('negative_keywords', {}),
                              "产品体验劣势", "inventory_2", "negative", "#34d399", 158)
    with neg_r1c2:
        render_async_wordcloud(dims_data.get('price', {}).get('negative_keywords', {}),
                              "价格感受劣势", "payments", "negative", "#fb923c", 27)
    neg_r2c1, neg_r2c2 = st.columns(2)
    with neg_r2c1:
        render_async_wordcloud(dims_data.get('service', {}).get('negative_keywords', {}),
                              "服务水平劣势", "support_agent", "negative", "#60a5fa", 213)
    with neg_r2c2:
        render_async_wordcloud(dims_data.get('logistics', {}).get('negative_keywords', {}),
                              "物流履约劣势", "local_shipping", "negative", "#f472b6", 329)

    # ==========================================
    # 聚合全局数据 (为后续图表做准备)
    # ==========================================
    all_pos_kw = {}
    all_neg_kw = {}

    for dim_key in ['product', 'price', 'service', 'logistics']:
        dim_info = dims_data.get(dim_key, {})
        for k, v in dim_info.get("positive_keywords", {}).items():
            all_pos_kw[k] = all_pos_kw.get(k, 0) + float(v)
        for k, v in dim_info.get("negative_keywords", {}).items():
            all_neg_kw[k] = all_neg_kw.get(k, 0) + float(v)

    import pandas as pd
    import altair as alt

    top_pos = dict(sorted(all_pos_kw.items(), key=lambda item: item[1], reverse=True)[:10]) if all_pos_kw else {}
    top_neg = dict(sorted(all_neg_kw.items(), key=lambda item: item[1], reverse=True)[:10]) if all_neg_kw else {}

    # ==========================================
    # 模块 C：全局多维占比分析 (饼图 & 环形图)
    # ==========================================
    # ==========================================
    # 模块 C：全局多维占比分析 (饼图 & 环形图) [Echarts 顺时针排序版]
    # ==========================================
    st.markdown("---")
    st.markdown(f"### :material/pie_chart: {title_prefix}全域声量结构大盘")
    st.caption("基于真实品类关注度与 AI 情感计算的交叉映射，直观定位体验核心驱动力与主要短板。")
    st.info(
        "**图表说明**：左侧饼图代表用户夸奖的火力分布，右侧中空环形图代表用户抱怨的重灾区。面积越大，说明该维度的讨论声量越高。")

    # 1. 重新计算宏观数据：统计四大维度的声量总和
    dim_summary = []
    dim_names_map = {'product': '产品体验', 'price': '价格感受', 'service': '服务水平', 'logistics': '物流履约'}
    dim_colors_pos = {'产品体验': '#34d399', '价格感受': '#fb923c', '服务水平': '#60a5fa', '物流履约': '#f472b6'}

    for dim_key, dim_name in dim_names_map.items():
        base_weight = weights.get(dim_key, 25.0)
        score = scores.get(dim_key, 50.0)

        pos_volume = base_weight * (score / 100.0)
        neg_volume = base_weight * ((100.0 - score) / 100.0)

        dim_summary.append({'维度': dim_name, '正面声量': pos_volume, '负面声量': neg_volume})

    df_dim = pd.DataFrame(dim_summary)

    # 2. 转换为 Echarts 需要的字典列表格式
    echarts_data_pos = []
    echarts_data_neg = []

    for idx, row in df_dim.iterrows():
        dim_name = row['维度']
        color = dim_colors_pos.get(dim_name, '#94a3b8')

        if row['正面声量'] > 0:
            echarts_data_pos.append({
                "value": round(row['正面声量'], 2),
                "name": dim_name,
                "itemStyle": {"color": color}
            })

        if row['负面声量'] > 0:
            echarts_data_neg.append({
                "value": round(row['负面声量'], 2),
                "name": dim_name,
                "itemStyle": {"color": color}
            })

    # ==========================================
    # 核心修改：强行对生成的数组按 value 从小到大排序
    # ==========================================
    echarts_data_pos = sorted(echarts_data_pos, key=lambda x: x["value"])
    echarts_data_neg = sorted(echarts_data_neg, key=lambda x: x["value"])

    col_pie, col_donut = st.columns(2)

    with col_pie:
        st.markdown(
            "<div style='text-align: center; color: #16a34a; font-weight: bold; margin-bottom: 10px;'><span class='material-symbols-rounded' style='font-size:18px; vertical-align:middle;'>thumb_up</span> 爽点声量来源分布</div>",
            unsafe_allow_html=True)

        if sum(item['value'] for item in echarts_data_pos) > 0:
            option_pie = {
                "backgroundColor": "transparent",
                "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                "legend": {"orient": "horizontal", "bottom": 0, "icon": "circle", "textStyle": {"color": "#64748b"}},
                "series": [{
                    "type": "pie",
                    "radius": "70%",
                    "center": ["50%", "45%"],
                    "startAngle": 90,  # 🌟 确保从 12 点钟方向开始
                    "clockwise": True,  # 🌟 确保顺时针渲染
                    "data": echarts_data_pos,
                    "label": {"show": False},
                    "itemStyle": {
                        "borderColor": "#f8fafc",
                        "borderWidth": 2
                    }
                }]
            }
            st_echarts(options=option_pie, height="340px")
        else:
            st.info("暂无正面声量数据")

    with col_donut:
        st.markdown(
            "<div style='text-align: center; color: #dc2626; font-weight: bold; margin-bottom: 10px;'><span class='material-symbols-rounded' style='font-size:18px; vertical-align:middle;'>warning</span> 痛点声量重灾区</div>",
            unsafe_allow_html=True)

        if sum(item['value'] for item in echarts_data_neg) > 0:
            option_donut = {
                "backgroundColor": "transparent",
                "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                "legend": {"orient": "horizontal", "bottom": 0, "icon": "circle", "textStyle": {"color": "#64748b"}},
                "series": [{
                    "type": "pie",
                    "radius": ["35%", "70%"],
                    "center": ["50%", "45%"],
                    "startAngle": 90,  # 🌟 确保从 12 点钟方向开始
                    "clockwise": True,  # 🌟 确保顺时针渲染
                    "data": echarts_data_neg,
                    "label": {"show": False},
                    "itemStyle": {
                        "borderColor": "#f8fafc",
                        "borderWidth": 2
                    }
                }]
            }
            st_echarts(options=option_donut, height="340px")
        else:
            st.info("暂无负面声量数据")

    # ==========================================
    # 模块 D：AI 深度洞察与核心痛点诊断 (按权重分布)
    # ==========================================
    st.markdown("---")
    st.markdown(f"### :material/psychology: {title_prefix}核心痛点深度诊断 (AI 洞察)")
    st.caption(
        "基于大模型语义理解提取的具体痛点场景。玫瑰花瓣大小代表该维度的全局关注度权重，助您优先解决高权重问题。")
    st.info(
        "**图表说明**：玫瑰花瓣的大小（半径）**不代表差评多少**，而是代表该维度在当前品类中的**重要性权重**。花瓣越大的痛点，越需要优先解决！")

    # 构建真正的四维权重玫瑰图数据
    dim_keys = ['product', 'price', 'service', 'logistics']
    dim_names = ['产品体验', '价格感受', '服务水平', '物流履约']
    dim_colors = ['#34d399', '#fb923c', '#60a5fa', '#f472b6']
    dim_icons = ['inventory_2', 'payments', 'support_agent', 'local_shipping']

    rose_data = []
    for i, key in enumerate(dim_keys):
        rose_data.append({
            '维度': dim_names[i],
            '权重': weights[key],
            '颜色': dim_colors[i],
            '图标': dim_icons[i],
            '原键': key
        })
    import pandas as pd
    import altair as alt
    df_rose_ai = pd.DataFrame(rose_data)

    # 采用 1 : 1.5 的黄金比例分栏，左图右文
    col_radar, col_text = st.columns([1, 1.5], gap="large")

    with col_radar:
        # 绘制基于权重的四瓣实心玫瑰图
        rose_chart = alt.Chart(df_rose_ai).mark_arc(
            innerRadius=0,  # 彻底取消中空，变为实心扇叶
            stroke="#ffffff",
            strokeWidth=2.5
        ).encode(
            # 🌟 核心排序修复：强行按“权重”从小到大 (ascending) 排列扇叶位置
            theta=alt.Theta("维度:N", sort=alt.EncodingSortField(field="权重", order="ascending")),
            # 🌟 必须同时注入 Order 通道，防止 Altair 的颜色图例干扰顺时针渲染顺序
            order=alt.Order("权重:Q", sort="ascending"),
            # 🌟 中空修复：将 zero=True，确保实心扇叶的尖端完美收束在绝对中心 (0点)
            radius=alt.Radius("权重:Q",
                              scale=alt.Scale(type="pow", exponent=0.15, zero=True, rangeMin=85, rangeMax=160)),
            color=alt.Color("颜色:N", scale=None),
            tooltip=['维度', alt.Tooltip('权重:Q', format='.1f', title='关注度(%)')]
        ).properties(
            height=480,
            background='transparent',
            # 控制图表在容器内向下居中
            padding={'left': 0, 'right': 0, 'top': 80, 'bottom': 100}
        ).configure_view(strokeWidth=0)

        st.altair_chart(rose_chart, width="stretch")

    with col_text:
        # 🌟 核心改动：在遍历渲染前，先按照“权重”进行降序排序 (ascending=False)
        df_text_display = df_rose_ai.sort_values(by='权重', ascending=False)

        # 引入图标字体库
        st.markdown(
            '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded" rel="stylesheet">',
            unsafe_allow_html=True)

        # 🌟 修改点：这里遍历排序后的 df_text_display
        for idx, row in df_text_display.iterrows():
            key = row['原键']
            color = row['颜色']
            icon = row['图标']
            dim_name = row['维度']

            # 提取真正在 JSON 里的 core_pain_points 数组
            pain_points = dims_data.get(key, {}).get('core_pain_points', [])

            # 拼装列表项 HTML
            points_html = ""
            if pain_points and isinstance(pain_points, list):
                for pt in pain_points:
                    points_html += f"<li style='margin-bottom: 6px;'>{pt}</li>"
            else:
                points_html = "<li style='color: #94a3b8; list-style: none; margin-left: -20px;'>该维度无评论样本。</li>"

            # 构建卡片 HTML (保持你原来的精美样式)
            card_html = f"""
            <div style="border-left: 5px solid {color}; background-color: rgba(255, 255, 255, 0.6); padding: 12px 18px; border-radius: 0 8px 8px 0; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; color: {color}; font-weight: bold; font-size: 16px;">
                        <span class="material-symbols-rounded" style="font-size: 20px; margin-right: 6px;">{icon}</span>
                        {dim_name}核心痛点
                    </div>
                    <div style="font-size: 12px; font-weight: bold; color: white; background-color: {color}; padding: 2px 8px; border-radius: 10px;">
                        权重占比 {row['权重']:.1f}%
                    </div>
                </div>
                <ul style="margin: 0; padding-left: 20px; color: #475569; font-size: 14px; line-height: 1.6;">
                    {points_html}
                </ul>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)


def render_comp_visualizations(report_text):
    """专门用于解析竞品对比 JSON 并渲染对比图表"""

    # 注入磨砂玻璃 (Glassmorphism) 质感的 CSS
    st.markdown("""
            <style>
            /* 针对包含图表的列赋予磨砂质感 */
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                background: rgba(255, 255, 255, 0.25); /* 半透明白色底 */
                backdrop-filter: blur(12px);           /* 核心：高斯模糊，产生磨砂感 */
                -webkit-backdrop-filter: blur(12px);   /* 兼容 Safari */
                border-radius: 16px;                   /* 圆角 */
                border: 1px solid rgba(255, 255, 255, 0.4); /* 边缘高光线，增强玻璃体积感 */
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05); /* 微弱的阴影 */
                padding: 15px;
            }
            </style>
        """, unsafe_allow_html=True)

    data = robust_json_parse(report_text)
    if not data:
        st.error(":material/warning: 无法从 AI 报告中提取有效的 JSON 数据，图表渲染终止。")
        return

    scores = data.get("comparison_scores", {})
    if not scores:
        return

    # 准备数据
    dims = ["product", "price", "logistics", "service"]
    dim_names = {"product": "产品体验", "price": "价格感受", "logistics": "物流履约", "service": "服务水平"}

    my_scores = [scores.get(d, {}).get("mine", 50) for d in dims]
    comp_scores = [scores.get(d, {}).get("competitor", 50) for d in dims]

    # --- 布局：左边雷达图，右边象限散点图 ---
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown("**:material/radar: 核心维度雷达对抗**")
        radar_options = {
            "backgroundColor": "transparent",
            "tooltip": {"trigger": "item"},
            "legend": {"data": ["本品", "竞品"], "bottom": 0},
            "radar": {
                "indicator": [
                    {"name": "产品体验", "max": 100},
                    {"name": "价格感受", "max": 100},
                    {"name": "物流履约", "max": 100},
                    {"name": "服务水平", "max": 100}
                ]
            },
            "series": [{
                "name": "本品 vs 竞品",
                "type": "radar",
                "data": [
                    {
                        "value": my_scores,
                        "name": "本品",
                        "itemStyle": {"color": "#00E396"},
                        "areaStyle": {"opacity": 0.3}
                    },
                    {
                        "value": comp_scores,
                        "name": "竞品",
                        "itemStyle": {"color": "#FF4560"},
                        "areaStyle": {"opacity": 0.3}
                    }
                ]
            }]
        }
        st_echarts(radar_options, height="350px")

    with col_chart2:
        st.markdown("**:material/scatter_plot: 竞争象限落位图**")
        # 散点图数据格式: [竞品得分(X), 本品得分(Y), 维度名称]
        # --- 优化点 1：修改数据结构，并加入“智能红绿变色” ---
        # --- 优化点 1：使用标准 {name, value} 结构，并在 Python 端直接控制红绿节点颜色 ---
        scatter_data = []
        for i in range(4):
            # 判断胜负关系：本品赢用绿色，竞品赢用红色
            is_winning = my_scores[i] > comp_scores[i]
            # 这里使用高饱和度的专业颜色
            point_color = "#00E396" if is_winning else "#FF4560"

            # 将每个维度的数据封装成 ECharts 识别的标准对象
            scatter_data.append({
                "name": dim_names[dims[i]],
                # value 数组: [竞品得分(X), 本品得分(Y)]
                "value": [comp_scores[i], my_scores[i]],
                # 关键：直接在这里赋予点颜色
                "itemStyle": {"color": point_color}
            })

        scatter_options = {
            "backgroundColor": "transparent",

            # --- 优化点 2：使用更稳定的 ECharts 字典模板变量彻底修复 Bug ---
            "tooltip": {
                "trigger": "item",
                "formatter": JsCode("""
                    function(params) {
                        // params.name 是维度名 (如：服务水平)
                        // params.value[0] 是 X 轴数据 (竞品得分)
                        // params.value[1] 是 Y 轴数据 (本品得分)
                        return '<b>' + params.name + '</b><br/>' +
                               '竞品得分: ' + params.value[0] + ' 分<br/>' +
                               '本品得分: ' + params.value[1] + ' 分';
                    }
                """)
            },

            "xAxis": {
                "name": "竞品得分", "type": "value", "min": 0, "max": 100,
                "splitLine": {"lineStyle": {"type": "dashed", "color": "rgba(0,0,0,0.1)"}}
            },
            "yAxis": {
                "name": "本品得分", "type": "value", "min": 0, "max": 100,
                "splitLine": {"lineStyle": {"type": "dashed", "color": "rgba(0,0,0,0.1)"}}
            },

            # 之前的 visualMap 方案被移除，因为它不利于控制点色和区域划分同时进行
            # visualMap 配置已删除。

            "series": [
                # --- 1. ✨ 核心优化：整合所有 markLine 和 markArea 的核心 series ---
                {
                    "name": "核心维度落位",
                    "type": "scatter",
                    "symbolSize": 24,  # 稍微加大，更清晰
                    "data": scatter_data,  # 这里的点已经是红绿色的了
                    "label": {
                        "show": True,
                        "formatter": "{b}",  # 显示维度名称
                        "position": "top",
                        "color": "#333",
                        "fontWeight": "bold",
                        "backgroundColor": "rgba(255,255,255,0.7)",  # 加个淡淡的白底，防重叠看不清
                        "padding": [2, 4],
                        "borderRadius": 4
                    },
                    # zlevel 设高一点，让点和线浮在背景色块上面
                    "zlevel": 2,

                    # ============================================================
                    # ✨ 终极整合：将所有辅助线完美整合在此✨
                    # ============================================================
                    "markLine": {
                        "silent": True,  # 不响应鼠标事件
                        "animation": False,  # 关闭辅助线的动画
                        "lineStyle": {"type": "dashed", "color": "#999"},  # 及格线的样式
                        "data": [
                            # A. 及格线 (十字准星)
                            {"xAxis": 50, "name": "及格线", "label": {"formatter": "及格线", "color": "#999"}},
                            {"yAxis": 50, "name": "及格线", "label": {"formatter": "及格线", "color": "#999"}},
                            # B. ✨ 保留并优化：对角线 (势均力敌线)
                            [
                                # 定义对角线起点 [0,0]
                                {"coord": [0, 0], "symbol": "none"},
                                # 定义对角线终点 [100,100]，并设置其样式和标签
                                {
                                    "coord": [100, 100], "symbol": "none",
                                    "lineStyle": {"color": "#FFB822", "type": "solid", "width": 1.5},
                                    # 这个文字标签不再需要（因为有了 markArea 区域文字），注释掉
                                    # "label": {"formatter": "↖ 本品优势区 | 竞品优势区 ↘", "position": "middle", "color": "#FFB822"}
                                }
                            ]
                        ]
                    },

                    # --- ✨ 保留并优化：利用 markArea 实现【强视觉区域背景底色】✨ ---
                    "markArea": {
                        "silent": True,  # 不响应鼠标事件
                        "data": [
                            # 1. 填充 本品优势区 (左上角，淡淡的绿)
                            [
                                {
                                    "name": "↖ 本品优势区",
                                    "itemStyle": {"color": "rgba(0, 227, 150, 0.08)"},  # 极淡的绿色
                                    "label": {"position": "insideTopLeft", "color": "#00C386", "fontWeight": "bold",
                                              "fontSize": 14},
                                    "coord": [0, 100]  # 左上角顶点坐标
                                },
                                {
                                    "coord": [100, 100]  # 配合对角线 markLine 的对角点
                                }
                            ],
                            # 2. 填充 竞品优势区 (右下角，淡淡的红)
                            [
                                {
                                    "name": "竞品优势区 ↘",
                                    "itemStyle": {"color": "rgba(255, 69, 96, 0.08)"},  # 极淡的红色
                                    "label": {"position": "insideBottomRight", "color": "#EF3550", "fontWeight": "bold",
                                              "fontSize": 14},
                                    "coord": [100, 0]  # 右下角顶点坐标
                                },
                                {
                                    "coord": [100, 100]  # 同上
                                }
                            ]
                        ]
                    }
                }
            ]
        }
        st_echarts(scatter_options, height="350px")

    # --- 布局：下部使用原生 UI 展示核心差异结论 ---
    # --- 布局：下部使用原生 UI 展示核心差异结论 ---
    st.markdown("---")
    st.markdown("### :material/insights: 核心维度深度解析")

    dimensions_data = data.get("dimensions_data", {})

    # 💡 优化 1：使用 Tabs 折叠维度，告别无限滚动的“瀑布流”页面
    tab_titles = [dim_names[d] for d in dims]
    tabs = st.tabs(tab_titles)

    # 💡 优化 2：定义一个内部函数，把字典转换为漂亮的“胶囊标签云”
    def render_tag_cloud(data_dict, style_type):
        if not data_dict:
            return "<span style='color:#999; font-size:14px;'>暂无数据</span>"

        # 根据类型设置不同的标签颜色体系 (Glassmorphism 风格匹配)
        styles = {
            "pro": "background: rgba(0, 227, 150, 0.15); color: #00A669; border: 1px solid rgba(0,227,150,0.3);",
            "con": "background: rgba(255, 69, 96, 0.15); color: #D83048; border: 1px solid rgba(255,69,96,0.3);",
            "comp_pro": "background: rgba(255, 184, 34, 0.15); color: #D49000; border: 1px solid rgba(255,184,34,0.3);",
        }
        css = styles.get(style_type, styles["pro"])

        tags_html = "<div style='display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;'>"
        # 根据权重(v)对字典进行降序排序，让重点标签排在前面
        sorted_data = sorted(data_dict.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0,
                             reverse=True)

        for k, v in sorted_data:
            # 权重越高，可以考虑字体稍微加大一点点，体现词云的轻度效果
            font_size = "14px"
            if isinstance(v, (int, float)) and v > 80:
                font_size = "15px; font-weight: bold;"

            tags_html += f"<span style='{css} padding: 4px 10px; border-radius: 12px; font-size: {font_size}; line-height: 1.2;'>{k} <span style='opacity:0.6; font-size:0.85em;'>({v})</span></span>"
        tags_html += "</div>"
        return tags_html

    # 循环在各个 Tab 中渲染内容
    for i, dim_key in enumerate(dims):
            with tabs[i]:
                dim_data = dimensions_data.get(dim_key, {})
                if not dim_data:
                    st.caption("该维度暂无详细数据。")
                    continue

                # 顶部突出 AI 核心洞察
                st.info(f"**:material/psychology: AI 核心洞察：** {dim_data.get('core_difference', '暂无总结')}")

                # 左右两列对比，使用更加内敛的 Markdown 标题替代刺眼的大色块
                ui_col1, ui_col2 = st.columns(2)

                with ui_col1:
                    st.markdown("#### 本品画像")
                    st.markdown("**优势护城河**")
                    st.markdown(render_tag_cloud(dim_data.get("my_advantages", {}), "pro"), unsafe_allow_html=True)

                    st.markdown("**亟待优化的痛点**")
                    st.markdown(render_tag_cloud(dim_data.get("my_pain_points", {}), "con"), unsafe_allow_html=True)

                with ui_col2:
                    st.markdown("#### 竞品画像")
                    st.markdown("**对手核心壁垒**")
                    st.markdown(render_tag_cloud(dim_data.get("comp_advantages", {}), "comp_pro"),
                                unsafe_allow_html=True)

                    st.markdown("**可攻击的软肋**")
                    # 竞品的痛点就是我方的机会，用绿色体系
                    st.markdown(render_tag_cloud(dim_data.get("comp_pain_points", {}), "pro"), unsafe_allow_html=True)


trigger_search = start_analysis or (user_input and user_input != st.session_state.last_query)

if trigger_search:
    if not can_use_spider():
        st.error(" 您今日的抓取额度已耗尽")
    else:
        st.session_state.last_query = user_input
        st.session_state.df_result = None
        st.session_state.comp_comments = []
        for k in ['report_single', 'report_market', 'report_comp']: st.session_state[k] = None
        st.session_state.processing_comp = False

        if is_url(user_input):
            extracted_id = extract_product_id(user_input)
            if extracted_id == "未知ID":
                st.error(" 格式错误：未在链接中检测到商品 ID。请点击进入具体商品详情页后再复制！")
                st.stop()
            st.session_state.analysis_type = 'single'
            st.session_state.product_id = extracted_id

            loading_placeholder = show_breathing_loading("正在启动浏览器引擎并抓取数据，请稍候...")

            # 【核心修改 1】：用 try...finally 强行兜底单品抓取
            try:
                res, title, sales_volume = run_spider(user_input, worker_id=1)

                if "Error" in res:
                    st.error(res)
                else:
                    clean_title = re.sub(r'-(?:tmall\.com天猫|淘宝网|京东|天猫|淘宝|jd\.com|tmall\.com).*$', '', title,
                                         flags=re.IGNORECASE).strip()
                    st.session_state.product_info = clean_title
                    st.session_state.current_sales = sales_volume
                    raw_df = pd.read_csv(res, encoding='utf-8-sig')
                    if 'date' in raw_df.columns:
                        raw_df['date_clean'] = raw_df['date'].astype(str).str.strip().str.lower()
                        clean_df = raw_df[~raw_df['date_clean'].isin(['nan', 'none', '', 'nat', 'null'])]
                        clean_df = clean_df.drop(columns=['date_clean'])
                    else:
                        clean_df = raw_df

                    if clean_df.empty:
                        st.error(" 抓取终止：清洗后未发现包含有效日期的真实评论！")
                        st.stop()

                    st.session_state.df_result = clean_df
                    inc_spider()

                    try:
                        # 1. 商品主表建档
                        db_manager.insert_ecommerce_product(
                            product_id=extracted_id,
                            title=title,
                            category=None,
                            price=None,
                            province=None,
                            city=None,
                            sales=sales_volume,
                            product_url=user_input
                        )

                        # 2. 核心修改：将 DataFrame 转换为带有 date 的字典列表
                        if 'date' not in clean_df.columns:
                            clean_df['date'] = ""  # 兜底防错，万一没抓到日期
                        new_comments_data = clean_df[['content', 'date']].to_dict('records')

                        # 3. 写入评论明细库
                        saved_num = db_manager.batch_save_scraped_comments(extracted_id, new_comments_data)

                        # 如果运行到这里，说明数据库没报错！
                        st.success(f"抓取成功！有效评论数: {len(clean_df)} | 当前销量: {sales_volume}")
                        if saved_num > 0:
                            st.caption(f":material/database: 系统已在后台为您将 {saved_num} 条新评论沉淀至数据库。")

                    except Exception as db_err:
                        # 如果数据库报错，直接在界面上爆红字，不再死得不明不白！
                        st.error(f"数据入库中断！详细错误：{db_err}")

            finally:
                # 无论代码是正常跑完，还是被强制 Stop 杀死，这句都一定会被触发，销毁动画！
                loading_placeholder.empty()

        else:
            st.session_state.analysis_type = 'market'
            st.session_state.product_info = f"全网调研：{user_input}"

            loading_placeholder = show_breathing_loading("正在搜索市场热销竞品并提取数据，请稍候...")

            # 【核心修改 2】：用 try...finally 强行兜底市场调研多线程抓取
            try:
                links = get_search_links(user_input, count=3)
                if links:
                    # ==========================================
                    # 【新增】：提前提取并保存这 3 个竞品的 ID 到全局状态中
                    # ==========================================
                    extracted_ids = [extract_product_id(url) for url in links]
                    valid_ids = [pid for pid in extracted_ids if pid != "未知ID"]
                    st.session_state.market_pids = "、".join(valid_ids) if valid_ids else "未提取到明确ID"
                    all_cmts = fetch_multiple_spiders(links, show_progress=False)
                    if all_cmts:
                        st.session_state.df_result = pd.DataFrame({'content': all_cmts})
                        inc_spider()
                        st.success(f"调研完成，共采集 {len(all_cmts)} 条市场评论")
                    else:
                        st.error("抓取失败，未采集到有效评论。")
                else:
                    st.error("未找到相关竞品商品")
            finally:
                loading_placeholder.empty()


def optimize_search_keyword(raw_title):
    """
    为淘宝商品标题“瘦身”，提取核心搜索词以扩大竞品搜索范围
    """
    if not raw_title or len(raw_title) < 4:
        return raw_title

    clean_title = raw_title

    # 1. 暴力剔除常见的电商营销废话和符号
    junk_patterns = [
        r'202[0-9]年?', r'新款', r'包邮', r'正品', r'官方', r'旗舰店',
        r'专柜', r'男女[鞋装]?', r'特价', r'清仓', r'买.送.', r'【.*?】',
        r'\[.*?\]', r'\(.*?\)', r'（.*?）'
    ]
    for pattern in junk_patterns:
        clean_title = re.sub(pattern, ' ', clean_title, flags=re.IGNORECASE)

    # 2. 剔除纯英文数字的长串（通常是极其具体的 SKU 型号，会导致搜不到竞品）
    clean_title = re.sub(r'[a-zA-Z0-9-]{5,}', ' ', clean_title)

    # 3. 清除多余空格
    clean_title = " ".join(clean_title.split())

    # 4. 淘宝的商品标题通常把最核心的名词（比如"连衣裙"、"机械键盘"）放在最后面
    # 如果清理后字符串很长，我们优先取最后的 10-12 个字符作为搜索词
    if len(clean_title) > 12:
        return clean_title[-12:]

    # 5. 如果清理完几乎没东西了（说明原标题全是营销词），做个兜底，取原标题最后8个字
    if len(clean_title) < 2:
        return raw_title[-8:]

    return clean_title


if st.session_state.df_result is not None:
    df = st.session_state.df_result
    st.markdown("---")
    is_single = (st.session_state.analysis_type == 'single')
    if is_single:
        st.markdown(
            f"<div style='color: #94a3b8; font-size: 13px; margin-bottom: -10px;'>商品 ID : {st.session_state.product_id}</div>",
            unsafe_allow_html=True)
        st.subheader(f" 本品数据：{st.session_state.product_info}")
    else:
        market_ids_str = st.session_state.get('market_pids', '未知ID')
        st.markdown(
            f"<div style='color: #94a3b8; font-size: 13px; margin-bottom: -10px;'>包含竞品 ID : {market_ids_str}</div>",
            unsafe_allow_html=True)
        st.subheader(f" 市场调研数据：{st.session_state.product_info}")

    # ========= 替换为新代码 =========
    expander_title = ":material/visibility: 查看全量原始数据 & 下载" if is_single else ":material/visibility: 查看市场全量数据 (含历史沉淀) & 下载"
    with st.expander(expander_title, expanded=False):

        # 1. 对全量数据进行关键词打标
        df_tagged = auto_tag_dimensions(df)

        st.markdown("#### :material/filter_alt: 快速筛选与数据导出")

        st.markdown("""
                    <style>
                    /* 1. 产品 (薄荷绿) - 第2个按钮 */
                    button[data-testid="stPill"]:nth-child(2) {
                        border-color: rgba(52, 211, 153, 0.4) !important;
                        background-color: transparent !important;
                    }
                    button[data-testid="stPill"]:nth-child(2) p { color: #10b981 !important; }

                    button[data-testid="stPill"]:nth-child(2)[aria-pressed="true"],
                    button[data-testid="stPill"]:nth-child(2)[data-pressed="true"] {
                        background-color: #34d399 !important;
                        border-color: #34d399 !important;
                    }
                    button[data-testid="stPill"]:nth-child(2)[aria-pressed="true"] p,
                    button[data-testid="stPill"]:nth-child(2)[data-pressed="true"] p {
                        color: white !important; 
                    }

                    /* 2. 物流 (樱花粉) - 第3个按钮 */
                    button[data-testid="stPill"]:nth-child(3) {
                        border-color: rgba(244, 114, 182, 0.4) !important;
                        background-color: transparent !important;
                    }
                    button[data-testid="stPill"]:nth-child(3) p { color: #ec4899 !important; }

                    button[data-testid="stPill"]:nth-child(3)[aria-pressed="true"],
                    button[data-testid="stPill"]:nth-child(3)[data-pressed="true"] {
                        background-color: #f472b6 !important;
                        border-color: #f472b6 !important;
                    }
                    button[data-testid="stPill"]:nth-child(3)[aria-pressed="true"] p,
                    button[data-testid="stPill"]:nth-child(3)[data-pressed="true"] p {
                        color: white !important;
                    }

                    /* 3. 价格 (活力橙) - 第4个按钮 */
                    button[data-testid="stPill"]:nth-child(4) {
                        border-color: rgba(251, 146, 60, 0.4) !important;
                        background-color: transparent !important;
                    }
                    button[data-testid="stPill"]:nth-child(4) p { color: #f97316 !important; }

                    button[data-testid="stPill"]:nth-child(4)[aria-pressed="true"],
                    button[data-testid="stPill"]:nth-child(4)[data-pressed="true"] {
                        background-color: #fb923c !important;
                        border-color: #fb923c !important;
                    }
                    button[data-testid="stPill"]:nth-child(4)[aria-pressed="true"] p,
                    button[data-testid="stPill"]:nth-child(4)[data-pressed="true"] p {
                        color: white !important;
                    }

                    /* 4. 服务 (天空蓝) - 第5个按钮 */
                    button[data-testid="stPill"]:nth-child(5) {
                        border-color: rgba(96, 165, 250, 0.4) !important;
                        background-color: transparent !important;
                    }
                    button[data-testid="stPill"]:nth-child(5) p { color: #3b82f6 !important; }

                    button[data-testid="stPill"]:nth-child(5)[aria-pressed="true"],
                    button[data-testid="stPill"]:nth-child(5)[data-pressed="true"] {
                        background-color: #60a5fa !important;
                        border-color: #60a5fa !important;
                    }
                    button[data-testid="stPill"]:nth-child(5)[aria-pressed="true"] p,
                    button[data-testid="stPill"]:nth-child(5)[data-pressed="true"] p {
                        color: white !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
        # ==========================================

        # 2. 计算各个维度的数量，用于在按钮上展示
        # 注意：一条评论可能同时命中多个维度（比如包含"产品、物流"）
        counts = {
            "全部": len(df_tagged),
            "产品": df_tagged['维度标签'].str.contains("产品").sum(),
            "物流": df_tagged['维度标签'].str.contains("物流").sum(),
            "价格": df_tagged['维度标签'].str.contains("价格").sum(),
            "服务": df_tagged['维度标签'].str.contains("服务").sum(),
            "未分类": (df_tagged['维度标签'] == "未分类").sum()
        }

        # 3. 使用 st.pills (Streamlit >= 1.35 支持) 或水平 radio 构建点击过滤按钮
        filter_options = [
            f"全部 ({counts['全部']})",
            f"产品 ({counts['产品']})",
            f"物流 ({counts['物流']})",
            f"价格 ({counts['价格']})",
            f"服务 ({counts['服务']})",
            f"未分类 ({counts['未分类']})"
        ]

        # 如果你的 Streamlit 版本较新，可以使用炫酷的 pills 胶囊按钮
        try:
            selected_filter = st.pills("点击按维度过滤评论：", filter_options, default=filter_options[0])
            if not selected_filter: selected_filter = filter_options[0]  # 防止全部取消选中
        except AttributeError:
            # 兼容老版本 Streamlit，使用水平单选框
            selected_filter = st.radio("点击按维度过滤评论：", filter_options, horizontal=True)

        # 4. 根据用户的选择，动态切割 DataFrame
        target_dim = selected_filter.split(" ")[0]  # 提取 "产品", "物流" 等纯文本

        if target_dim == "全部":
            df_display = df_tagged
        elif target_dim == "未分类":
            df_display = df_tagged[df_tagged['维度标签'] == "未分类"]
        else:
            # 使用 contains 处理包含多个标签的情况 (例如 "产品、物流")
            df_display = df_tagged[df_tagged['维度标签'].str.contains(target_dim)]

        # 5. 展示过滤后的数据表格
        st.dataframe(df_display, width="stretch", height=300)

        # 6. 动态下载按钮：用户看到的是什么，下载出来的就是什么（且包含维度标签）
        col_dl1, col_dl2 = st.columns([1, 3])
        with col_dl1:
            st.download_button(
                label=f":material/download: 下载 {target_dim} 数据 (.csv)",
                data=df_display.to_csv(index=False).encode('utf-8-sig'),
                file_name=f"{target_dim}_data_{int(time.time())}.csv",
                mime='text/csv',
                disabled=not can_download(),
                on_click=inc_dl,
                type="primary"  # 高亮下载按钮
            )
        with col_dl2:
            st.caption(
                f"提示：当前表格显示 **{len(df_display)}** 条记录。下载的 CSV 文件已自动附带『维度标签』列，方便您在 Excel 中进行二次透视。")


    # ==========================================
    # 【极致流畅优化 1】：封装单品/市场的主力 AI 报告区为 Fragment
    # ==========================================
    @st.fragment
    def render_main_report_fragment(df, is_single, selected_model, user_api_key, is_using_custom_key):
        rpt_key = 'report_single' if is_single else 'report_market'
        mod_key = 'report_single_model' if is_single else 'report_market_model'

        st.markdown("### 深度分析报告")

        # 场景 A：如果已经有生成好的报告，直接渲染，并只显示局部重新生成按钮
        if st.session_state.get(rpt_key):
            st.info(f"当前展示的是 **{st.session_state.get(mod_key)}** 生成的报告")

            # 渲染图表和文字报告
            parse_and_display_report(st.session_state[rpt_key])
            if st.session_state.df_result is not None:
                render_report_visualizations(st.session_state[rpt_key],
                                             title_prefix="本品" if is_single else "市场")

            st.markdown("---")
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                # 这里的按钮不再导致整个页面回到顶部，只会重绘当前 Fragment
                st.button(":material/replay: 重新生成排版图表 (不耗AI额度)", width="stretch",
                          type="primary")
            with col_btn2:
                btn_text = f":material/replay: 重新调用 AI 生成报告" if selected_model == st.session_state.get(
                    mod_key) else f" 切换 {selected_model} 重新生成"
                if st.button(btn_text, width="stretch", type="primary",
                             disabled=not can_use_ai() or st.session_state.processing_comp):
                    st.session_state[rpt_key] = None
                    st.rerun(scope="fragment")  # 瞬间清空并刷新当前区域，回到场景 B

        # 场景 B：尚未生成报告，显示生成按钮及执行生成逻辑
        else:
            gen_btn_text = "生成单品体验报告" if is_single else "生成市场趋势调研报告"
            if st.button(f"{gen_btn_text} ({selected_model})", type="primary", disabled=not can_use_ai()):
                if not user_api_key:
                    st.error("缺少 API Key，无法调用 AI！")
                    return

                st.session_state[mod_key] = selected_model

                # 获取本次爬虫刚刚抓到的数据 (仅作为长度基准和兜底使用)
                scraped_comments = df['content'].tolist()

                # ==========================================
                # 极简、严密的底层数据提取与展示逻辑
                # ==========================================
                if is_single:
                    product_id = st.session_state.product_id
                    sales = st.session_state.get('current_sales', 0)

                    # 1. 直接从数据库拉取全量记录（此时已经包含了刚刚写入的新数据！）
                    db_comments = db_manager.get_all_comments_by_product(product_id)

                    # 2. 绝对安全的兜底逻辑
                    if not db_comments:
                        # 【兜底】：防范数据库宕机或读取失败，强行使用内存数据
                        final_comments_to_ai = scraped_comments
                        st.warning(
                            f"数据库提取异常。降级使用本次新抓取的 **{len(scraped_comments)}** 条评论送入 AI 引擎。")
                    else:
                        # 【直接接管】：数据库查出来的就是最全、最干净的数据
                        final_comments_to_ai = db_comments

                        # 计算到底有多少条是纯历史积累的老数据
                        historical_count = len(final_comments_to_ai) - len(scraped_comments)

                        if historical_count > 0:
                            st.success(
                                f"**全量数据就绪**：除了刚抓取的 **{len(scraped_comments)}** 条，系统还成功调取了 **{historical_count}** 条历史数据！共计 **{len(final_comments_to_ai)}** 条送入 AI。")
                        else:
                            st.info(
                                f"**数据就绪**：该商品暂无历史数据，共使用本次的 **{len(final_comments_to_ai)}** 条评论进行分析。")

                    # ==========================================
                    # 新增：供用户抽查的底层语料折叠面板 (DataFrame 形式)
                    # ==========================================
                    with st.expander(
                            f":material/plagiarism: 查阅送入 AI 分析的底层明细 ({len(final_comments_to_ai)}条)",
                            expanded=False):
                        # 包装成 DataFrame 展示，自带滚动条、搜索和全屏功能，体验极佳
                        import pandas as pd
                        df_show = pd.DataFrame({'最终参与分析的真实用户语料': final_comments_to_ai})
                        st.dataframe(df_show, use_container_width=True, height=200)
                        st.caption("提示：以上数据已由系统在底层完成去重与清洗。")

                    # 3. 把最终定稿的 final_comments_to_ai 喂给大模型
                    stream_gen = analyze_single_product_stream(
                        product_name=st.session_state.product_info,
                        comments_list=final_comments_to_ai,
                        sales_volume=sales,
                        api_key=user_api_key,
                        model=selected_model
                    )


                else:
                    # 市场调研暂无单独历史拼接逻辑，因为 fetch_multiple_spiders 底层已完成融合
                    final_comments_to_ai = scraped_comments

                    # 只保留一句文字提示即可

                    st.success(
                        f"**核心市场语料库已就绪**：底层爬虫已自动检索并融合数据库关联历史，共构建 **{len(final_comments_to_ai)}** 条全网竞品评测数据送入 AI。")

                    stream_gen = analyze_market_trends_stream(

                        search_query=st.session_state.product_info,

                        comments_list=final_comments_to_ai,

                        api_key=user_api_key,

                        model=selected_model

                    )

                # 启动流式打印
                with st.spinner("AI 正在深度思考并生成报告，期间你可以随意上下滚动查看数据..."):
                    full_report = st.write_stream(stream_gen)

                # 收尾与状态保存
                st.session_state[rpt_key] = full_report

                if "AI 分析中断" in full_report:
                    if "401" in full_report or "Incorrect API key" in full_report or "invalid_api_key" in full_report:
                        st.error(
                            ":material/key_off: 您提供的自定义 API Key 无效、已过期或额度不足，请检查后重新输入！")
                    else:
                        st.error(f":material/warning: AI 服务器响应异常，请稍后重试。")
                    st.session_state[rpt_key] = None
                elif "未配置" not in full_report:
                    if not is_using_custom_key: inc_ai()
                    if is_single:
                        try:
                            sales = st.session_state.get('current_sales', 0)
                            cbei_score = 50.0  # 默认兜底分

                            # 1. 尝试从 full_report 中提取 JSON 算分
                            json_match = re.search(r'\{\s*"category"[\s\S]*\}', full_report)
                            if json_match:
                                raw_json_str = re.sub(r'`{3}(?:json)?\s*$', '', json_match.group(0)).strip()
                                try:
                                    import json
                                    data = json.loads(raw_json_str)
                                    scores = data.get('scores', {})
                                    category = data.get('category', 'general').lower()

                                    df_cbei = db_manager.get_cbei_dashboard_data()
                                    w_prod, w_ser, w_log, w_pri = 70.0, 10.0, 10.0, 10.0  # 默认兜底

                                    if not df_cbei.empty:
                                        cat_df = df_cbei[df_cbei['category'] == category]
                                        if cat_df.empty:
                                            cat_df = df_cbei[df_cbei['category'] == 'general']

                                        if not cat_df.empty:
                                            row = cat_df.iloc[0]
                                            w_prod = float(row['产品关注度'])
                                            w_ser = float(row['服务关注度'])
                                            w_log = float(row['物流关注度'])
                                            w_pri = float(row['价格关注度'])

                                    cbei_score = (
                                                         scores.get('product', 50) * w_prod +
                                                         scores.get('price', 50) * w_pri +
                                                         scores.get('service', 50) * w_ser +
                                                         scores.get('logistics', 50) * w_log
                                                 ) / 100.0
                                except Exception as e:
                                    pass  # JSON解析失败则走兜底 50 分

                            # 2. 存入数据库（复用 positive_rate 字段存储 CBEI）
                            db_manager.save_daily_stats(
                                user_id=st.session_state.current_user_id,
                                product_id=st.session_state.product_id,
                                product_name=st.session_state.product_info,
                                sales_volume=sales,
                                positive_rate=round(cbei_score, 2)  # 强行把 CBEI 塞进这个坑
                            )
                            st.toast(f" 数据已存档！综合 CBEI: {round(cbei_score, 2)} 分 | 销量: {sales}")
                        except Exception as e:
                            st.error(f"数据存档失败: {e}")

                # 强制 Fragment 重绘，以便展示渲染好的词云和玫瑰图
                # st.rerun(scope="fragment")
                st.rerun()


    # 执行调用
    render_main_report_fragment(df, is_single, selected_model, user_api_key, is_using_custom_key)
    if is_single and st.session_state.current_role in ['商家', '管理员']:
        trend_df = db_manager.get_product_trend(st.session_state.current_user_id, st.session_state.product_id)
        if not trend_df.empty and len(trend_df) > 0:
            st.markdown("---")
            st.subheader(" 商品历史数据趋势监控")
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
                        st.warning(f"**销量增长预警！** 当前销量较上次记录增长率为 {growth_rate:.2f}%，低于 10% 阈值！",
                                   icon=":material/alarm:")
                    else:
                        st.success(f" 销量增长健康！当前增长率为 {growth_rate:.2f}%。", icon="")
                    st.markdown("###")  # 增加一点底部间距，让UI更好看
            plot_df = trend_df_sorted.reset_index().copy()
            plot_df['数据类型'] = '真实数据'
            combined_df = render_trend_prediction_charts(plot_df)

    if is_single and st.session_state.report_single:
        st.markdown("---")
        st.markdown("###  进阶功能：竞品比对")
        if role == '客户':
            st.info(":material/lock: 提示：您当前是客户身份。竞品多线程比对为商家和管理员专属功能。")
        else:
            has_comp_data = len(st.session_state.comp_comments) > 0
            col_act1, col_act2 = st.columns([1, 4])
            with col_act1:
                if not has_comp_data:
                    if st.button(":material/search: 自动抓取 3 个竞品", type="primary",
                                 disabled=st.session_state.processing_comp or not can_use_spider()):
                        st.session_state.processing_comp = True
                        st.rerun()
                else:
                    if st.button(":material/repeat: 重新抓取", disabled=st.session_state.processing_comp, type="primary"):
                        st.session_state.comp_comments = []
                        st.session_state.report_comp = None
                        st.rerun()
            with col_act2:
                if has_comp_data:
                    st.success(f" 已就绪：{len(st.session_state.comp_comments)} 条竞品数据")

            # ==========================================
            if has_comp_data:
                # 1. 获取本品 ID
                current_pid = st.session_state.get('product_id', '未知')

                # 2. 获取竞品 ID 列表
                comp_pids = st.session_state.get("comp_scraped_ids", [])

                # 3. 用 Columns 布局让显示更整齐
                id_col1, id_col2 = st.columns([1, 2])

                with id_col1:
                    st.markdown(f"**本品 ID:** `{current_pid}`")

                with id_col2:
                    if comp_pids:
                        id_tags = " ".join([f"`{pid}`" for pid in comp_pids])
                        st.markdown(f"**对手 ID:** {id_tags}")
                    else:
                        st.caption("尚未记录竞品 ID")

                st.divider()  # 画一条分割线，区分 ID 信息与下方的详情表格
            # ==========================================
            # ==========================================

            if st.session_state.processing_comp and not has_comp_data:
                target_product = st.session_state.product_info
                # 【新增】：从 session_state 中获取本品 ID (假设你的变量名是 product_id)
                # 如果你存的是其他名字，请替换成你实际的变量名
                current_product_id = st.session_state.get('product_id', None)

                loading_placeholder = show_breathing_loading("正在寻找并采集对手数据，这可能需要一点时间...")

                # 【修复】：用 try...except...finally 捕获隐藏的崩溃
                try:
                    optimized_keyword = optimize_search_keyword(target_product)
                    # 可以在界面上打印出来看看搜了什么词，方便调试
                    st.caption(f"正在搜索竞品核心词: {optimized_keyword}")
                    comp_links = get_search_links(
                        keyword=optimized_keyword,
                        count=3,
                        exclude_id=current_product_id  # 关键在这里
                    )

                    if comp_links:
                        # 哪怕只有 1 个或 2 个 link，也传给爬虫
                        temp_comp_comments = fetch_multiple_spiders(comp_links, show_progress=True)

                        if temp_comp_comments:
                            st.session_state.comp_comments = temp_comp_comments

                            # ==========================================
                            # 新增：提取竞品 ID 并持久化保存到 session_state
                            # ==========================================

                            extracted_ids = []
                            for link in comp_links:
                                match = re.search(r'[?&]id=(\d+)', link)
                                if match:
                                    extracted_ids.append(match.group(1))
                            st.session_state.comp_scraped_ids = extracted_ids
                            # ==========================================

                            inc_spider()
                            st.toast(f" 竞品采集完成！共抓取 {len(temp_comp_comments)} 个竞品")

                            # 成功抓取后，释放状态并刷新页面渲染数据
                            loading_placeholder.empty()
                            st.session_state.processing_comp = False
                            st.rerun()  # 只有成功才刷新！
                        else:
                            st.error("采集竞品数据失败：爬虫未返回任何有效数据（可能遭遇反爬或解析异常）。")
                    else:
                        st.error("未找到任何竞品商品。")

                except Exception as e:
                    # 捕获可能因为不足三个导致的底层代码越界崩溃
                    st.error(f"抓取过程中发生代码异常: {str(e)}")
                finally:
                    # 无论成功失败，销毁加载特效并释放锁定
                    loading_placeholder.empty()
                    st.session_state.processing_comp = False
                    # 这里绝对不要放 st.rerun()

            #
            if has_comp_data:
                # 1. 初始化竞品 DataFrame
                df_comp_display = pd.DataFrame(st.session_state.comp_comments)
                df_comp_display['source'] = '竞品'
                if 'date' not in df_comp_display.columns:
                    df_comp_display['date'] = '未知'

                # 2. 处理本品数据
                df_main_display = df.copy()
                df_main_display['source'] = '本品'
                if 'date' not in df_main_display.columns:
                    df_main_display['date'] = '未知'

                # ==========================================
                # 为竞品和本品分别打上维度标签，确保合并时列对齐
                # ==========================================
                df_comp_tagged = auto_tag_dimensions(df_comp_display)
                df_main_tagged = auto_tag_dimensions(df_main_display)

                # 3. 核心修改：合并时，明确把 '维度标签' 和 'date' 列加上！
                df_all = pd.concat([
                    df_main_tagged[['date', '维度标签', 'content', 'source']],
                    df_comp_tagged[['date', '维度标签', 'content', 'source']]
                ], ignore_index=True)

                with st.expander(":material/plagiarism: 全域对比数据下钻分析 (支持双重筛选) & 下载", expanded=True):

                    st.markdown("#### :material/tune: 数据交叉筛选器")

                    # 使用左右两列来放置两个维度的筛选按钮
                    col_filter_1, col_filter_2 = st.columns(2)

                    with col_filter_1:
                        st.markdown("**1. 按数据来源筛选**")
                        source_options = ["全部来源", "本品", "竞品"]
                        try:
                            # 增加 key 防止组件冲突
                            selected_source = st.pills("选择来源：", source_options, default="全部来源",
                                                       key="pill_source", label_visibility="collapsed")
                            if not selected_source: selected_source = "全部来源"
                        except AttributeError:
                            selected_source = st.radio("选择来源：", source_options, horizontal=True, key="radio_source",
                                                       label_visibility="collapsed")

                    with col_filter_2:
                        st.markdown("**2. 按评价维度筛选**")
                        dim_options = ["所有维度", "产品", "物流", "价格", "服务", "未分类"]
                        try:
                            selected_dim = st.pills("选择维度：", dim_options, default="所有维度", key="pill_dim",
                                                    label_visibility="collapsed")
                            if not selected_dim: selected_dim = "所有维度"
                        except AttributeError:
                            selected_dim = st.radio("选择维度：", dim_options, horizontal=True, key="radio_dim",
                                                    label_visibility="collapsed")

                    # ==========================================
                    # 动态双重过滤引擎
                    # ==========================================
                    df_filtered = df_all.copy()

                    # 第一层过滤：来源 (本品/竞品)
                    if selected_source != "全部来源":
                        df_filtered = df_filtered[df_filtered['source'] == selected_source]

                    # 第二层过滤：维度标签
                    if selected_dim != "所有维度":
                        if selected_dim == "未分类":
                            df_filtered = df_filtered[df_filtered['维度标签'] == "未分类"]
                        else:
                            # 支持多标签匹配 (例如："产品、物流" 也能被 "物流" 筛出来)
                            df_filtered = df_filtered[df_filtered['维度标签'].str.contains(selected_dim)]

                    # ==========================================
                    # 结果展示与联动下载
                    # ==========================================
                    st.markdown(
                        f"<div style='color:#64748b; font-size:14px; margin-bottom:10px;'>当前筛选结果：共计 <b>{len(df_filtered)}</b> 条评论匹配。</div>",
                        unsafe_allow_html=True)

                    # 在前端表格中明确展示 'source' 列，让用户看得清清楚楚
                    st.dataframe(df_filtered[['date', 'source', '维度标签', 'content']], width="stretch", height=300)

                    # 动态生成下载文件名 (例如: compare_本品_物流_1712345678.csv)
                    safe_filename = f"compare_{selected_source}_{selected_dim}_{int(time.time())}.csv"

                    st.download_button(
                        label=f":material/download: 导出当前表格为 CSV ({len(df_filtered)}条)",
                        data=df_filtered.to_csv(index=False).encode('utf-8-sig'),
                        file_name=safe_filename,
                        mime='text/csv',
                        type="primary"
                    )


                # ==========================================
                # 【极致流畅优化 2】：封装竞品对比 AI 报告区为 Fragment
                # ==========================================

                @st.fragment
                def render_comp_report_fragment(df, selected_model, user_api_key, is_using_custom_key):
                    st.markdown("###")

                    # 场景 A：已经存在竞品报告
                    if st.session_state.get("report_comp"):
                        st.markdown("---")
                        st.subheader(":material/balance: 竞品差异化对比报告")
                        st.info(f"由模型 **{st.session_state.get('report_comp_model', '未知模型')}** 生成")

                        parse_and_display_report(st.session_state.report_comp)
                        # 2. 【核心修改点】：不要用 render_report_visualizations！
                        # 换成我们专门为竞品双边 JSON 编写的解析和渲染函数
                        render_comp_visualizations(st.session_state.report_comp)

                        st.markdown("---")
                        col_btn_c1, col_btn_c2 = st.columns(2)
                        with col_btn_c1:
                            st.button(" 重新排版竞品图表 (不耗AI额度)", key="btn_redraw_comp", type="primary",
                                      width="stretch")
                        with col_btn_c2:
                            btn_text_comp = f" 重新调用 AI 生成竞品报告" if selected_model == st.session_state.get(
                                'report_comp_model') else f" 切换 {selected_model} 重新生成"
                            if st.button(btn_text_comp, key="btn_regen_comp", width="stretch", type="primary",
                                         disabled=not can_use_ai() or st.session_state.processing_comp):
                                st.session_state.report_comp = None
                                st.rerun(scope="fragment")

                    # 场景 B：尚未生成，提供生成按钮
                    else:
                        btn_label = f":material/balance: 生成竞品对比报告 ({selected_model})"
                        if st.button(btn_label, type="primary",
                                     disabled=not can_use_ai() or st.session_state.processing_comp,
                                     width="stretch"):
                            st.session_state.report_comp_model = selected_model
                            main_product_cmts = df['content'].tolist()

                            if st.session_state.analysis_type == 'single' and st.session_state.product_id:
                                main_product_cmts = db_manager.get_all_comments_by_product(st.session_state.product_id)

                            with st.spinner("AI 正在深度比对竞品差异，这可能需要几十秒钟..."):
                                stream_gen = analyze_competitor_comparison_stream(
                                    st.session_state.product_info,
                                    main_product_cmts,
                                    st.session_state.comp_comments,
                                    user_api_key,
                                    model=selected_model,
                                    single_ai_report=st.session_state.report_single
                                )
                                full_report = st.write_stream(stream_gen)

                            st.session_state.report_comp = full_report

                            if "AI 分析中断" in full_report:
                                st.session_state.report_comp = None
                            elif "未配置" not in full_report:
                                if not is_using_custom_key: inc_ai()

                            st.rerun(scope="fragment")


                # 执行调用
                render_comp_report_fragment(df, selected_model, user_api_key, is_using_custom_key)
