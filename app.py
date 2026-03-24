import os
import time
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
import matplotlib.pyplot as plt
import json
import numpy as np
from datetime import timedelta
from crawler import run_spider, get_search_links
from analysis import (
    analyze_single_product_stream,
    analyze_market_trends_stream,
    analyze_competitor_comparison_stream
)
load_dotenv()
db_manager.init_stats_db()
default_key_from_env = os.getenv("ALIYUN_API_KEY")
st.set_page_config(page_title="基于AI的电商平台客户购买体验分析系统", page_icon="/app/static/logo4.png", layout="wide")
db_manager.init_db()
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
if 'theme_color' not in st.session_state: st.session_state.theme_color = "#00f2fe"
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
                                       placeholder="👤 请输入用户名")
            login_pwd = st.text_input("密码", value="123456", type="password", label_visibility="collapsed",
                                      placeholder="🔒 请输入密码")

            loading_placeholder = st.empty()

            if st.button("登 录 ➔", type="primary", use_container_width=True):
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
                if st.button("还没有账号？ 立即注册", use_container_width=True): switch_page('register')
            with c2:
                if st.button("忘记密码？ 修改密码", use_container_width=True): switch_page('reset_pwd')

        elif st.session_state.auth_page == 'register':
            st.markdown(
                "<h1 style='background: linear-gradient(90deg, #8ec5fc 0%, #e0c3fc 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; text-align: center; margin-bottom: 30px; font-size: 36px; letter-spacing: 2px;'>注册账号</h1>",
                unsafe_allow_html=True)
            reg_user = st.text_input("用户名", placeholder="👤 请输入用户名", label_visibility="collapsed")
            reg_pwd = st.text_input("密码", type="password", placeholder="🔒 请输入密码", label_visibility="collapsed")
            reg_pwd2 = st.text_input("确认密码", type="password", placeholder="🔒 请确认密码",
                                     label_visibility="collapsed")
            reg_role = st.selectbox("选择角色", ["商家", "客户"], label_visibility="collapsed")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("提交注册", type="primary", use_container_width=True):
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
            if st.button("返回登录", use_container_width=True): switch_page('login')

        elif st.session_state.auth_page == 'reset_pwd':
            st.markdown(
                "<h1 style='background: linear-gradient(90deg, #8ec5fc 0%, #e0c3fc 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; text-align: center; margin-bottom: 30px; font-size: 36px; letter-spacing: 2px;'>修改密码</h1>",
                unsafe_allow_html=True)
            reset_user = st.text_input("用户名", placeholder="👤 请输入用户名", label_visibility="collapsed")
            reset_pwd = st.text_input("新密码", type="password", placeholder="🔒 请输入新密码",
                                      label_visibility="collapsed")
            reset_pwd2 = st.text_input("确认新密码", type="password", placeholder="🔒 请确认新密码",
                                       label_visibility="collapsed")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("确认修改", type="primary", use_container_width=True):
                if reset_pwd != reset_pwd2:
                    st.error("两次输入密码不一致！")
                else:
                    success, msg = db_manager.update_password(reset_user, reset_pwd)
                    if success:
                        st.success("密码修改成功，请返回登录！")
                    else:
                        st.error(msg)
            if st.button("返回登录", use_container_width=True): switch_page('login')

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

/* 原 primary 按钮样式覆盖 */
.stButton > button[kind="primary"] {{
    background: {st.session_state.theme_color} !important;
    color: white !important;
    border: none !important;
    box-shadow: 0 4px 15px {st.session_state.theme_color}40 !important;
}}
.stButton > button[kind="primary"]:hover {{
    box-shadow: 0 6px 20px {st.session_state.theme_color}60 !important;
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
[data-testid="stVerticalBlockBorderWrapper"], 
[data-testid="stExpander"] {{
    background-color: rgba(255, 255, 255, 0.85) !important; 
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid {st.session_state.theme_color}30 !important; /* 边框透明度提高到 30% */
    box-shadow: 0 8px 30px {st.session_state.theme_color}15 !important; /* 阴影也带上 15% 的主题色 */
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

/* 顺便修复一下表格内部表头的颜色，让它更搭暖色系 */
[data-testid="stDataFrame"] th {{
    background-color: rgba(245, 241, 234, 0.8) !important; 
    color: #475569 !important;
}}
</style>
"""
st.markdown(dynamic_theme_css, unsafe_allow_html=True)

user_data = db_manager.get_user_data_and_check_reset(st.session_state.current_user_id)
role = user_data['role']
spider_cnt = user_data['spider_count']
ai_cnt = user_data['ai_count']
dl_cnt = user_data['dl_count']
with st.sidebar:
    # 动态判断当前处于哪个页面，切换按钮文案和逻辑
    if st.session_state.current_page == 'profile':
        avatar_btn_label = "← 返回分析大厅"
        avatar_help = "点击返回主控台"
    else:
        avatar_btn_label = f"👤 {st.session_state.current_user}  ({role})"
        avatar_help = "点击进入个人中心"

    st.markdown('<span class="profile-marker"></span>', unsafe_allow_html=True)
    if st.button(avatar_btn_label, use_container_width=True, help=avatar_help):
        # 如果在个人中心就回主页，否则进个人中心
        st.session_state.current_page = 'main' if st.session_state.current_page == 'profile' else 'profile'
        st.rerun()
    st.markdown("---")

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
        if st.button(admin_btn_label, use_container_width=True, type="primary"):
            st.session_state.current_page = 'admin' if st.session_state.current_page != 'admin' else 'main'
            st.rerun()
    st.markdown("---")
    if role in ['商家', '管理员']:
        st.header(":material/History: 历史数据")
        btn_label = ":material/home: 返回分析大厅" if st.session_state.current_page == 'history' else ":material/deployed_code_history: 查看历史记录"
        if st.button(btn_label, use_container_width=True, type="primary"):
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
                color: white !important;
            }
            div[data-testid="stElementContainer"]:has(.red-marker) + div[data-testid="stElementContainer"] button:hover,
            div[data-testid="element-container"]:has(.red-marker) + div[data-testid="element-container"] button:hover {
                background-color: #FF3333 !important;
                border-color: #FF3333 !important;
            }
            </style>
        """, unsafe_allow_html=True)
    st.markdown('<span class="red-marker"></span>', unsafe_allow_html=True)
    if st.button(":material/delete: 清空当前页面记录", use_container_width=True):
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
            st.markdown(f"**👤 用户名：** {st.session_state.current_user}")
            st.markdown(f"**🛡️ 角色权限：** {st.session_state.current_role}")
            st.markdown(f"**📅 上次活跃：** {user_data.get('last_date', today_str)}")

        st.subheader(":material/donut_small: 今日额度详情")
        with st.container(border=True):
            if role == '客户':
                st.write(f"- 🕷️ 爬虫抓取: **{spider_cnt}** / 3 次")
                st.write(f"- 🧠 AI 分析: **{ai_cnt}** / 3 次")
                st.write(f"- ⬇️ 数据下载: **{dl_cnt}** / 3 次")
            elif role == '商家':
                st.write(f"- 🕷️ 爬虫抓取: **{spider_cnt}** / 10 次")
                st.write(f"- 🧠 AI 分析: **{ai_cnt}** / 10 次")
                st.write("- ⬇️ 数据下载: 不限次数")
            else:
                st.success("👑 管理员权限：系统全功能无限制")

    with col_theme:
        st.subheader(":material/palette: 个性化主题设置")
        with st.container(border=True):
            st.write("自定义您的专属科技高亮色：")
            # 核心：颜色拾取器
            new_color = st.color_picker("拾取霓虹高亮色", st.session_state.theme_color)
            if new_color != st.session_state.theme_color:
                st.session_state.theme_color = new_color
                st.rerun()

            st.caption("提示：更改颜色将实时接管全站的输入框、数字看板、选项卡和悬浮光效。")

            st.markdown("<br>或者快速应用预设方案：", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("深海蓝", use_container_width=True):
                st.session_state.theme_color = "#0284c7"  # 沉稳专业，极佳的数据分析基调色
                st.rerun()
            if c2.button("暮色紫", use_container_width=True):
                st.session_state.theme_color = "#7c3aed"  # 优雅高级，不会像霓虹紫那样扎眼
                st.rerun()
            if c3.button("抹茶绿", use_container_width=True):
                st.session_state.theme_color = "#65a30d"  # 清新自然，搭配暖白底色非常护眼
                st.rerun()
            if c4.button("琥珀橘", use_container_width=True):
                st.session_state.theme_color = "#ea580c"  # 温暖活力，非常适合作为警示或高亮指标
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
                " 选择要查阅的商品",
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
                                    f":material/warning: **销量增长预警！** 最近一期销量较上期增长仅为 {growth_rate:.2f}%，低于 10% 阈值！",
                                    icon=":material/alarm:")
                            else:
                                st.success(f"销量增长健康！近期增长率为 {growth_rate:.2f}%。", icon="")
                            st.markdown("---")
                    plot_df = trend_df_sorted.reset_index().copy()
                    plot_df['数据类型'] = '真实数据'
                    combined_df = plot_df.copy()
                    if len(plot_df) >= 3:
                        try:
                            plot_df['date_obj'] = pd.to_datetime(plot_df['日期'])
                            plot_df['date_num'] = plot_df['date_obj'].map(lambda x: x.toordinal())
                            z_sales = np.polyfit(plot_df['date_num'], plot_df['销量'], 1)
                            p_sales = np.poly1d(z_sales)
                            z_rate = np.polyfit(plot_df['date_num'], plot_df['预估好评率'], 1)
                            p_rate = np.poly1d(z_rate)
                            last_date = plot_df['date_obj'].iloc[-1]
                            future_dates = [last_date + timedelta(days=i) for i in range(1, 6)]
                            pred_data = []
                            for d in future_dates:
                                d_num = d.toordinal()
                                pred_sales = max(0, int(p_sales(d_num)))
                                pred_rate = max(0.0, min(100.0, round(p_rate(d_num), 2)))
                                pred_data.append({
                                    '日期': d.strftime('%Y-%m-%d'),
                                    '销量': pred_sales,
                                    '预估好评率': pred_rate,
                                    '数据类型': '预测数据'
                                })
                            pred_df = pd.DataFrame(pred_data)
                            connection_point = plot_df.iloc[-1:].copy()
                            connection_point['数据类型'] = '预测数据'
                            combined_df = pd.concat([plot_df.drop(columns=['date_obj', 'date_num']),
                                                     connection_point.drop(columns=['date_obj', 'date_num']),
                                                     pred_df], ignore_index=True)
                        except Exception as e:
                            st.warning(f"数据波动异常，暂时无法生成预测折线：{e}")
                    st.markdown("### :material/area_chart:  数据走势与未来预测")
                    st.caption("实线为真实历史数据；虚线为 AI 根据历史线性拟合推演的未来 5 天趋势。")
                    pan_only = alt.selection_interval(bind='scales', encodings=['x'], zoom=False)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption(":material/trending_up: 销量走势 (含未来5天推演数据)")
                        c1_base = alt.Chart(combined_df).mark_line(point=True).encode(
                            x=alt.X('日期:N', title="", axis=alt.Axis(labelOverlap=True, labelAngle=-45)),
                            y=alt.Y('销量:Q', title="", scale=alt.Scale(zero=False)),
                            color=alt.Color('数据类型:N',
                                            scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                            range=['#4c78a8', '#f58518']),  # 还原蓝色
                                            legend=alt.Legend(title="", orient="bottom")),
                            strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                                    range=[[1, 0], [5, 5]]),
                                                      legend=None),
                            tooltip=['日期', '销量', '数据类型']
                        ).properties(background='transparent')  # 【新增】强行让图表本身背景透明

                        c1 = c1_base.add_params(pan_only) if hasattr(c1_base, 'add_params') else c1_base.add_selection(
                            pan_only)
                        # 【新增】 theme=None 阻断系统默认白底
                        st.altair_chart(c1, use_container_width=True, theme=None)

                    with col2:
                        st.caption(":material/thumb_up: 好评率走势 (%)")
                        c2_base = alt.Chart(combined_df).mark_line(point=True).encode(
                            x=alt.X('日期:N', title="", axis=alt.Axis(labelOverlap=True, labelAngle=-45)),
                            y=alt.Y('预估好评率:Q', title="", scale=alt.Scale(zero=False)),
                            color=alt.Color('数据类型:N',
                                            scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                            range=['#FF4B4B', '#f58518']),  # 还原红色
                                            legend=alt.Legend(title="", orient="bottom")),
                            strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                                    range=[[1, 0], [5, 5]]),
                                                      legend=None),
                            tooltip=['日期', '预估好评率', '数据类型']
                        ).properties(background='transparent')  # 【新增】强行让图表本身背景透明

                        c2 = c2_base.add_params(pan_only) if hasattr(c2_base, 'add_params') else c2_base.add_selection(
                            pan_only)
                        # 【新增】 theme=None 阻断系统默认白底
                        st.altair_chart(c2, use_container_width=True, theme=None)

                    st.markdown("### :material/database:  详细数据明细 (含预测数据)")
                    st.dataframe(combined_df, use_container_width=True)
                    st.download_button(
                        label=":material/download:  下载该商品历史及预测数据 (.csv)",
                        data=combined_df.to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"{selected_item}_trend_prediction.csv",
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
                placeholder=" 筛选商品 ID (支持模糊查询)",
                label_visibility="collapsed",
                key="search_merchant_pid"
            )
        with col_search_btn:
            st.button(":material/search: 搜索", type="primary", use_container_width=True)
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
            use_container_width=True,
            key="merchant_stat_editor",
            column_config={
                "id": "记录ID",
                "user_id": "我的个人 ID",
                "product_id": "商品 ID",
                "product_name": "商品名称",
                "record_date": "记录日期",
                "sales_volume": "销量记录",
                "positive_rate": "预估好评率 (%)"
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
    tab_users, tab_stats = st.tabs([":material/manage_accounts: 账号权限管控", ":material/database: 数据调控大盘"])
    with tab_users:
        st.subheader("全局用户表")
        df_users = db_manager.get_all_users_admin()
        col_u_search1, col_u_search2, col_u_btn = st.columns([4, 4, 1])
        with col_u_search1:
            search_u_id = st.text_input("搜索用户ID", placeholder=" 筛选用户 ID (模糊查询)",
                                        label_visibility="collapsed", key="search_u_id_input")
        with col_u_search2:
            search_u_name = st.text_input("搜索用户名", placeholder=" 搜索用户名 (模糊查询)",
                                          label_visibility="collapsed", key="search_u_name_input")
        with col_u_btn:
            st.button(":material/search: 搜索", key="btn_u_search", type="primary", use_container_width=True)
        filtered_users_df = df_users.copy()
        if search_u_id:
            filtered_users_df = filtered_users_df[
                filtered_users_df['id'].astype(str).str.contains(search_u_id.strip(), case=False, na=False)
            ]
        if search_u_name:
            filtered_users_df = filtered_users_df[
                filtered_users_df['username'].astype(str).str.contains(search_u_name.strip(), case=False, na=False)
            ]
        with st.form("user_edit_form", clear_on_submit=False):
            edited_users = st.data_editor(
                filtered_users_df,
                num_rows="dynamic",
                disabled=["id"],
                use_container_width=True,
                column_config={
                    "username": "用户名",
                    "role": "角色权限",
                    "last_date": "最后活跃/重置日期",
                    "spider_count": "爬虫已用次数",
                    "ai_count": "AI已用次数",
                    "dl_count": "下载已用次数"
                }
            )
            submit_users = st.form_submit_button(":material/check_circle: 确认并覆盖显示的用户数据", type="primary",
                                                 use_container_width=True)
            if submit_users:
                db_manager.sync_users_admin(edited_users, filtered_users_df)
                st.toast("用户数据同步完成！")
                import time
                time.sleep(1.2)
                st.rerun()
    with tab_stats:
        st.subheader("全局商品追踪记录")
        df_stats = db_manager.get_all_product_stats_admin()
        col_search1, col_search2, col_btn = st.columns([4, 4, 1])
        with col_search1:
            search_uid = st.text_input("筛选用户ID", placeholder=" 筛选用户 ID (模糊查询)",
                                       label_visibility="collapsed", key="search_stats_uid_input")
        with col_search2:
            search_pid = st.text_input("筛选商品ID", placeholder=" 筛选商品 ID (模糊查询)",
                                       label_visibility="collapsed", key="search_stats_pid_input")
        with col_btn:
            st.button(":material/search: 搜索", key="btn_stats_search", type="primary", use_container_width=True)
        filtered_df = df_stats.copy()
        if search_uid:
            filtered_df = filtered_df[
                filtered_df['user_id'].astype(str).str.contains(search_uid.strip(), case=False, na=False)
            ]
        if search_pid:
            filtered_df = filtered_df[
                filtered_df['product_id'].astype(str).str.contains(search_pid.strip(), case=False, na=False)
            ]
        edited_stats = st.data_editor(
            filtered_df,
            num_rows="dynamic",
            disabled=["id"],
            use_container_width=True,
            key="admin_stat_editor",
            column_config={
                "user_id": "所属用户 ID",
                "product_id": "商品 ID",
                "product_name": "商品名称",
                "record_date": "记录日期",
                "sales_volume": "销量记录",
                "positive_rate": "预估好评率 (%)"
            }
        )
        if st.button(" 确认并覆盖当前显示的商品数据", type="primary"):
            db_manager.sync_product_stats_admin(edited_stats, filtered_df)
            st.toast(" 商品历史数据同步完成！")
            import time
            time.sleep(1.2)
            st.rerun()
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
    start_analysis = st.button(":material/search_check_2: 立即分析", type="primary", use_container_width=True, disabled=not can_use_spider())
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
def generate_wordcloud_image(word_freq_dict, theme='positive'):
    """直接接收 AI 提取的词频字典画图，支持权重越高，颜色越深的动态映射"""
    sys_type = platform.system()
    if sys_type == "Windows":
        font_path = "C:/Windows/Fonts/simhei.ttf"
    elif sys_type == "Darwin":
        font_path = "/System/Library/Fonts/PingFang.ttc"
    else:
        font_path = None
    wc = WordCloud(
        font_path=font_path,
        width=800, height=400,
        background_color='white',
        max_words=80
    ).generate_from_frequencies(word_freq_dict)
    current_font_sizes = [v[1] for v in wc.layout_]
    if current_font_sizes:
        max_font = max(current_font_sizes)
        min_font = min(current_font_sizes)
    else:
        max_font = 100
        min_font = 10
    def dynamic_deep_color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        """
        根据字体大小（权重）动态计算颜色深浅。
        权重越大 (font_size 大) -> 亮度 (Lightness) 越低 -> 颜色越深。
        """
        if max_font == min_font:
            normalized_size = 1.0
        else:
            normalized_size = (font_size - min_font) / (max_font - min_font)
        lightness = 40 - (normalized_size ** 2) * 25
        saturation = 90
        if theme == 'positive':
            hue = 120
        else:
            hue = 0
        return f"hsl({hue}, {saturation}%, {int(lightness)}%)"
    wc.recolor(color_func=dynamic_deep_color_func)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    plt.margins(0, 0)
    return fig
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
                st.error(
                    " 格式错误：未在链接中检测到商品 ID。您上传的可能是搜索聚合页或无效链接，请点击进入具体商品详情页后再复制！")
                st.stop()
            st.session_state.analysis_type = 'single'
            st.session_state.product_id = extract_product_id(user_input)
            with st.spinner(' 正在爬取商品数据与销量...'):
                res, title, sales_volume = run_spider(user_input, worker_id=1)
            if "Error" in res:
                st.error(res)
            else:
                st.session_state.product_info = title
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
                st.success(f"抓取成功！有效评论数: {len(clean_df)} | 当前销量: {sales_volume}")
        else:
            st.session_state.analysis_type = 'market'
            with st.spinner(' 正在搜索市场热销竞品...'):
                links = get_search_links(user_input, count=3)
            if links:
                all_cmts = []
                st.session_state.product_info = f"全网调研：{user_input}"
                with st.spinner(' 多线程采集竞品数据中...'):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [executor.submit(run_spider, link, i + 1) for i, link in enumerate(links)]
                        for f in concurrent.futures.as_completed(futures):
                            res, title, _ = f.result()
                            if res and "Error" not in res:
                                try:
                                    t_df = pd.read_csv(res, encoding='utf-8-sig')
                                    if 'content' in t_df.columns: all_cmts.extend(t_df['content'].tolist())
                                except:
                                    pass
                if all_cmts:
                    st.session_state.df_result = pd.DataFrame({'content': all_cmts})
                    inc_spider()
                    st.success(f"调研完成，共采集 {len(all_cmts)} 条市场评论")
            else:
                st.error("未找到相关商品")
if st.session_state.df_result is not None:
    df = st.session_state.df_result
    st.markdown("---")
    is_single = (st.session_state.analysis_type == 'single')
    if is_single:
        st.subheader(f" 本品数据：{st.session_state.product_info}")
    else:
        st.subheader(f" 市场调研数据：{st.session_state.product_info}")
    with st.expander(":material/visibility: 查看原始数据 & 下载", expanded=False):
        st.dataframe(df, use_container_width=True)
        st.download_button(
            label=":material/download:  下载当前分析数据 (.csv)",
            data=df.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"data_{int(time.time())}.csv",
            mime='text/csv',
            disabled=not can_download(),
            on_click=inc_dl
        )
    rpt_key = 'report_single' if is_single else 'report_market'
    mod_key = 'report_single_model' if is_single else 'report_market_model'
    saved_rpt = st.session_state[rpt_key]
    saved_mod = st.session_state[mod_key]
    st.markdown("###  深度分析报告")
    if saved_rpt:
        st.info(f"当前展示的是 **{saved_mod}** 生成的报告")
        clean_report = saved_rpt
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
        clean_report = re.sub(r'\s*(?:`{3}(?:json)?\s*)?\{\s*".*?"\s*:\s*\d+[\s\S]*', '', clean_report,
                              flags=re.IGNORECASE)
        if think_content:
            with st.expander(" 查看 AI 深度思考逻辑", expanded=False):
                st.caption("以下是 AI 总结报告前的数据梳理与推演过程：")
                st.markdown(think_content)
        st.markdown(clean_report.strip())
        if st.session_state.df_result is not None:
            st.markdown("---")
            st.markdown("### :material/cloud: AI 提纯核心情感词云")
            st.caption("基于 AI 深度理解提取的产品特征与情感关键词，上方为正面好评，下方为负面差评。")
            with st.spinner("正在绘制词云图..."):
                try:
                    pos_data, neg_data = extract_dual_wordclouds(saved_rpt)
                    st.markdown("<h5 style='text-align: center; color: #2e7d32;'> 正面特征词云</h5>",
                                unsafe_allow_html=True)
                    if pos_data:
                        st.pyplot(generate_wordcloud_image(pos_data, theme='positive'))
                    else:
                        st.warning("未提取到正面数据")
                    st.write("")
                    st.markdown("<h5 style='text-align: center; color: #c62828;'> 负面特征词云</h5>",
                                unsafe_allow_html=True)
                    if neg_data:
                        st.pyplot(generate_wordcloud_image(neg_data, theme='negative'))
                    else:
                        st.warning("未提取到负面数据")
                except Exception as e:
                    st.error(f"词云渲染解析失败: {e}")
        if st.session_state.df_result is not None and (pos_data or neg_data):
            st.markdown("---")
            st.markdown("###  核心特征情感占比监控大屏")
            st.caption("比例逆时针降序排列，颜色越深代表权重/频率越高。")
            df_pos = pd.DataFrame(list(pos_data.items()), columns=['特征', '权重']).nlargest(10,
                                                                                             '权重') if pos_data else pd.DataFrame()
            df_neg = pd.DataFrame(list(neg_data.items()), columns=['特征', '权重']).nlargest(10,
                                                                                             '权重') if neg_data else pd.DataFrame()
            col_pie1, col_pie2 = st.columns(2)
            with col_pie1:
                st.markdown("<h5 style='text-align: center; color: #2e7d32;'> Top 10 正面好评占比 (饼图)</h5>",
                            unsafe_allow_html=True)
                if not df_pos.empty:
                    pie_chart = alt.Chart(df_pos).mark_arc(innerRadius=0, stroke="#fff").encode(
                        theta=alt.Theta(field="权重", type="quantitative"),
                        order=alt.Order(field="权重", type="quantitative", sort="ascending"),
                        color=alt.Color(field="特征", type="nominal",
                                        sort=alt.SortField(field="权重", order="descending"),
                                        scale=alt.Scale(scheme='greens', reverse=True),
                                        legend=alt.Legend(title="好评特征")),
                        tooltip=['特征', '权重']
                    ).properties(height=350)
                    st.altair_chart(pie_chart, use_container_width=True)
            with col_pie2:
                st.markdown("<h5 style='text-align: center; color: #c62828;'> Top 10 负面痛点占比 (环形图)</h5>",
                            unsafe_allow_html=True)
                if not df_neg.empty:
                    donut_chart = alt.Chart(df_neg).mark_arc(innerRadius=70, stroke="#fff").encode(
                        theta=alt.Theta(field="权重", type="quantitative"),
                        order=alt.Order(field="权重", type="quantitative", sort="ascending"),
                        color=alt.Color(field="特征", type="nominal",
                                        sort=alt.SortField(field="权重", order="descending"),
                                        scale=alt.Scale(scheme='reds', reverse=True),
                                        legend=alt.Legend(title="痛点特征")),
                        tooltip=['特征', '权重']
                    ).properties(height=350)
                    st.altair_chart(donut_chart, use_container_width=True)
            st.write("")
            col_rose, col_empty = st.columns([1, 1])
            with col_rose:
                st.markdown("<h5 style='text-align: center;'>核心痛点分布 (南丁格尔玫瑰图)</h5>",
                            unsafe_allow_html=True)
                st.caption("视觉重点：颜色最深、半径最长的扇形即为第一大痛点，一眼看穿严重程度。")
                if not df_neg.empty:
                    rose_chart = alt.Chart(df_neg).mark_arc(innerRadius=20, stroke="#fff").encode(
                        theta=alt.Theta(field="特征", type="nominal",
                                        sort=alt.SortField(field="权重", order="ascending")),
                        radius=alt.Radius(field="权重", type="quantitative",
                                          scale=alt.Scale(type="sqrt", zero=True, rangeMin=20)),
                        color=alt.Color(field="特征", type="nominal",
                                        sort=alt.SortField(field="权重", order="descending"),
                                        scale=alt.Scale(scheme='redpurple', reverse=True),
                                        legend=alt.Legend(title="痛点特征")),
                        tooltip=['特征', '权重']
                    ).properties(height=400)
                    st.altair_chart(rose_chart, use_container_width=True)
                else:
                    st.info(" 暂无负面痛点数据。")
        st.markdown("---")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button(":material/replay: 重新生成排版图表 (不耗AI额度)", use_container_width=True, type="primary"):
                pass
        with col_btn2:
            btn_text = f":material/replay: 重新调用 AI 生成报告" if selected_model == saved_mod else f" 切换 {selected_model} 重新生成"
            if st.button(btn_text, use_container_width=True, type="primary",
                         disabled=not can_use_ai() or st.session_state.processing_comp):
                st.session_state[rpt_key] = None
                st.rerun()
    else:
        gen_btn_text = "生成单品体验报告" if is_single else "生成市场趋势调研报告"
        if st.button(f"{gen_btn_text} ({selected_model})", type="primary", disabled=not can_use_ai()):
            if not user_api_key:
                st.error("缺少 API Key，无法调用 AI！")
            else:
                comments = df['content'].tolist()
                st.session_state[mod_key] = selected_model
                if is_single:
                    sales = st.session_state.get('current_sales', 0)
                    stream_gen = analyze_single_product_stream(
                        product_name=st.session_state.product_info,
                        comments_list=comments,
                        sales_volume=sales,
                        api_key=user_api_key,
                        model=selected_model
                    )
                    full_report = st.write_stream(stream_gen)
                    st.session_state[rpt_key] = full_report
                    if "AI 分析中断" in full_report:
                        if "401" in full_report or "Incorrect API key" in full_report or "invalid_api_key" in full_report:
                            st.error(
                                ":material/key_off: 您提供的自定义 API Key 无效、已过期或额度不足，请检查后重新输入！")
                        else:
                            st.error(f":material/warning: AI 服务器响应异常，请稍后重试。")
                        st.session_state[rpt_key] = None
                    elif "未配置" not in full_report:
                        if not is_using_custom_key:
                            inc_ai()
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
                            st.toast(f" 数据已存档！好评率: {positive_rate}% | 销量: {sales}")
                        except Exception as e:
                            st.error(f"数据存档失败: {e}")
                        st.rerun()
                else:
                    stream_gen = analyze_market_trends_stream(
                        search_query=st.session_state.product_info,
                        comments_list=comments,
                        api_key=user_api_key,
                        model=selected_model
                    )
                    full_report = st.write_stream(stream_gen)
                    st.session_state[rpt_key] = full_report
                    if "AI 分析中断" in full_report:
                        if "401" in full_report or "Incorrect API key" in full_report or "invalid_api_key" in full_report:
                            st.error(
                                ":material/key_off: 您提供的自定义 API Key 无效、已过期或额度不足，请检查后重新输入！")
                        else:
                            st.error(f":material/warning: AI 服务器响应异常，请稍后重试。")
                        st.session_state[rpt_key] = None
                    elif "未配置" not in full_report:
                        if not is_using_custom_key:
                            inc_ai()
                        st.rerun()
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
                        st.warning(f":material/warning: **销量增长预警！** 当前销量较上次记录增长率为 {growth_rate:.2f}%，低于 10% 阈值！",
                                   icon=":material/alarm:")
                    else:
                        st.success(f" 销量增长健康！当前增长率为 {growth_rate:.2f}%。", icon="")
                    st.markdown("###")  # 增加一点底部间距，让UI更好看
            plot_df = trend_df_sorted.reset_index().copy()
            plot_df['数据类型'] = '真实数据'
            combined_df = plot_df.copy()
            if len(plot_df) >= 3:
                try:
                    plot_df['date_obj'] = pd.to_datetime(plot_df['日期'])
                    plot_df['date_num'] = plot_df['date_obj'].map(lambda x: x.toordinal())
                    z_sales = np.polyfit(plot_df['date_num'], plot_df['销量'], 1)
                    p_sales = np.poly1d(z_sales)
                    z_rate = np.polyfit(plot_df['date_num'], plot_df['预估好评率'], 1)
                    p_rate = np.poly1d(z_rate)
                    last_date = plot_df['date_obj'].iloc[-1]
                    future_dates = [last_date + timedelta(days=i) for i in range(1, 6)]
                    pred_data = []
                    for d in future_dates:
                        d_num = d.toordinal()
                        pred_sales = max(0, int(p_sales(d_num)))
                        pred_rate = max(0.0, min(100.0, round(p_rate(d_num), 2)))
                        pred_data.append({
                            '日期': d.strftime('%Y-%m-%d'),
                            '销量': pred_sales,
                            '预估好评率': pred_rate,
                            '数据类型': '预测数据'
                        })
                    pred_df = pd.DataFrame(pred_data)
                    connection_point = plot_df.iloc[-1:].copy()
                    connection_point['数据类型'] = '预测数据'
                    combined_df = pd.concat([plot_df.drop(columns=['date_obj', 'date_num']),
                                             connection_point.drop(columns=['date_obj', 'date_num']),
                                             pred_df], ignore_index=True)
                except Exception as e:
                    st.warning(f"数据波动异常，暂时无法生成预测折线：{e}")
            pan_only = alt.selection_interval(bind='scales', encodings=['x'], zoom=False)
            col1, col2 = st.columns(2)
            with col1:
                st.caption(":material/trending_up: 销量走势 (含未来5天推演数据)")
                c1_base = alt.Chart(combined_df).mark_line(point=True).encode(
                    x=alt.X('日期:N', title="", axis=alt.Axis(labelOverlap=True, labelAngle=-45)),
                    y=alt.Y('销量:Q', title="", scale=alt.Scale(zero=False)),
                    color=alt.Color('数据类型:N',
                                    scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                    range=['#4c78a8', '#f58518']),  # 还原蓝色
                                    legend=alt.Legend(title="", orient="bottom")),
                    strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                            range=[[1, 0], [5, 5]]),
                                              legend=None),
                    tooltip=['日期', '销量', '数据类型']
                ).properties(background='transparent')  # 【新增】强行让图表本身背景透明

                c1 = c1_base.add_params(pan_only) if hasattr(c1_base, 'add_params') else c1_base.add_selection(
                    pan_only)
                # 【新增】 theme=None 阻断系统默认白底
                st.altair_chart(c1, use_container_width=True, theme=None)

            with col2:
                st.caption(":material/thumb_up: 好评率走势 (%)")
                c2_base = alt.Chart(combined_df).mark_line(point=True).encode(
                    x=alt.X('日期:N', title="", axis=alt.Axis(labelOverlap=True, labelAngle=-45)),
                    y=alt.Y('预估好评率:Q', title="", scale=alt.Scale(zero=False)),
                    color=alt.Color('数据类型:N',
                                    scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                    range=['#FF4B4B', '#f58518']),  # 还原红色
                                    legend=alt.Legend(title="", orient="bottom")),
                    strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                            range=[[1, 0], [5, 5]]),
                                              legend=None),
                    tooltip=['日期', '预估好评率', '数据类型']
                ).properties(background='transparent')  # 【新增】强行让图表本身背景透明

                c2 = c2_base.add_params(pan_only) if hasattr(c2_base, 'add_params') else c2_base.add_selection(
                    pan_only)
                # 【新增】 theme=None 阻断系统默认白底
                st.altair_chart(c2, use_container_width=True, theme=None)
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
                if has_comp_data: st.success(f" 已就绪：{len(st.session_state.comp_comments)} 条竞品数据")
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
                        for i, (res_file, _, _) in enumerate(results):
                            progress_bar.progress((i + 1) / len(comp_links))
                            if res_file and "Error" not in res_file:
                                try:
                                    c_df = pd.read_csv(res_file, encoding='utf-8-sig')
                                    if 'date' in c_df.columns:
                                        c_df['date_clean'] = c_df['date'].astype(str).str.strip().str.lower()
                                        c_df = c_df[~c_df['date_clean'].isin(['nan', 'none', '', 'nat', 'null'])]
                                    if 'content' in c_df.columns:
                                        temp_comp_comments.extend(c_df['content'].tolist())
                                except:
                                    pass
                        if len(temp_comp_comments) > 0:
                            st.session_state.comp_comments = temp_comp_comments
                            inc_spider()
                            status.update(label=" 采集完成！", state="complete")
                        else:
                            status.update(label=" 采集失败", state="error")
                    else:
                        status.update(label=" 未找到竞品", state="error")
                st.session_state.processing_comp = False
                st.rerun()
            if has_comp_data:
                df_comp_display = pd.DataFrame({'content': st.session_state.comp_comments, 'source': '竞品'})
                df_main_display = df.copy()
                df_main_display['source'] = '本品'
                df_all = pd.concat([df_main_display[['content', 'source']], df_comp_display[['content', 'source']]],
                                   ignore_index=True)
                with st.expander(":material/plagiarism: 查看竞品详情 & 下载对比数据", expanded=True):
                    st.dataframe(df_comp_display.head(50), use_container_width=True, height=200)
                    st.download_button(
                        label=":material/download: 下载完整对比数据",
                        data=df_all.to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"compare_data_{int(time.time())}.csv",
                        mime='text/csv'
                    )
                st.markdown("###")
                btn_label = " 重新生成对比报告" if st.session_state.report_comp else f":material/balance: 生成竞品对比报告 ({selected_model})"
                if st.button(btn_label, type="primary", disabled=not can_use_ai() or st.session_state.processing_comp,
                             use_container_width=True):
                    st.session_state.report_comp_model = selected_model
                    stream_gen = analyze_competitor_comparison_stream(
                        st.session_state.product_info,
                        df['content'].tolist(),
                        st.session_state.comp_comments,
                        user_api_key,
                        model=selected_model
                    )
                    full_report = st.write_stream(stream_gen)
                    st.session_state.report_comp = full_report
                    if "AI 分析中断" in full_report:
                        if "401" in full_report or "Incorrect API key" in full_report or "invalid_api_key" in full_report:
                            st.error(
                                ":material/key_off: 您提供的自定义 API Key 无效、已过期或额度不足，请检查后重新输入！")
                        else:
                            st.error(f":material/warning: AI 服务器响应异常，请稍后重试。")
                        st.session_state.report_comp = None
                    elif "未配置" not in full_report:
                        if not is_using_custom_key:
                            inc_ai()
                        st.rerun()
            if st.session_state.report_comp:
                st.markdown("---")
                st.subheader(":material/balance: 竞品差异化对比报告")
                st.info(f"由模型 **{st.session_state.report_comp_model}** 生成")
                clean_comp_report = st.session_state.report_comp
                think_content_comp = ""
                think_match_comp = re.search(r'<think>(.*?)</think>', clean_comp_report,
                                             flags=re.DOTALL | re.IGNORECASE)
                if think_match_comp:
                    think_content_comp = think_match_comp.group(1).strip()
                    clean_comp_report = re.sub(r'<think>.*?</think>\n*', '', clean_comp_report,
                                               flags=re.DOTALL | re.IGNORECASE)
                else:
                    alt_match_comp = re.search(r'(.*?)(?=\n#|\n---)', clean_comp_report, flags=re.DOTALL)
                    if alt_match_comp:
                        think_content_comp = alt_match_comp.group(1).strip()
                        clean_comp_report = clean_comp_report.replace(alt_match_comp.group(0), "").strip()
                clean_comp_report = re.sub(r'\s*(?:`{3}(?:json)?\s*)?\{\s*".*?"\s*:\s*\d+[\s\S]*', '', clean_comp_report, flags=re.IGNORECASE)
                if think_content_comp:
                    with st.expander(" 查看 AI 深度思考逻辑", expanded=False):
                        st.caption("以下是 AI 总结报告前的数据梳理与推演过程：")
                        st.markdown(think_content_comp)
                st.markdown(clean_comp_report.strip())
                pos_data_c, neg_data_c = {}, {}
                try:
                    pos_data_c, neg_data_c = extract_dual_wordclouds(st.session_state.report_comp)
                    st.markdown("<h5 style='text-align: center; color: #2e7d32;'> 本品核心优势词云</h5>",
                                unsafe_allow_html=True)
                    if pos_data_c:
                        st.pyplot(generate_wordcloud_image(pos_data_c, theme='positive'))
                    else:
                        st.warning("未提取到优势数据")
                    st.write("")
                    st.markdown("<h5 style='text-align: center; color: #c62828;'> 本品核心劣势词云</h5>",
                                unsafe_allow_html=True)
                    if neg_data_c:
                        st.pyplot(generate_wordcloud_image(neg_data_c, theme='negative'))
                    else:
                        st.warning("未提取到劣势数据")
                except Exception as e:
                    st.error(f"竞品词云渲染失败: {e}")
                if 'pos_data_c' in locals() or 'neg_data_c' in locals():
                    if pos_data_c or neg_data_c:
                        st.markdown("---")
                        st.markdown("###  竞品差异化多维占比分析")
                        st.caption("基于本品与竞品对比提取的核心优势与劣势权重数据分布。")
                        df_pos_c = pd.DataFrame(list(pos_data_c.items()), columns=['特征', '权重']).nlargest(10,
                                                                                                             '权重') if pos_data_c else pd.DataFrame()
                        df_neg_c = pd.DataFrame(list(neg_data_c.items()), columns=['特征', '权重']).nlargest(10,
                                                                                                             '权重') if neg_data_c else pd.DataFrame()
                        col_pie1_c, col_pie2_c = st.columns(2)
                        with col_pie1_c:
                            st.markdown("<h5 style='text-align: center; color: #2e7d32;'> Top 10 核心优势占比</h5>",
                                        unsafe_allow_html=True)
                            if not df_pos_c.empty:
                                pie_chart_c = alt.Chart(df_pos_c).mark_arc(innerRadius=0, stroke="#fff").encode(
                                    theta=alt.Theta(field="权重", type="quantitative"),
                                    order=alt.Order(field="权重", type="quantitative", sort="ascending"),
                                    color=alt.Color(field="特征", type="nominal",
                                                    sort=alt.SortField(field="权重", order="descending"),
                                                    scale=alt.Scale(scheme='greens', reverse=True),
                                                    legend=alt.Legend(title="优势特征")),
                                    tooltip=['特征', '权重']
                                ).properties(height=350)
                                st.altair_chart(pie_chart_c, use_container_width=True)
                        with col_pie2_c:
                            st.markdown("<h5 style='text-align: center; color: #c62828;'> Top 10 核心劣势占比</h5>",
                                        unsafe_allow_html=True)
                            if not df_neg_c.empty:
                                donut_chart_c = alt.Chart(df_neg_c).mark_arc(innerRadius=70, stroke="#fff").encode(
                                    theta=alt.Theta(field="权重", type="quantitative"),
                                    order=alt.Order(field="权重", type="quantitative", sort="ascending"),
                                    color=alt.Color(field="特征", type="nominal",
                                                    sort=alt.SortField(field="权重", order="descending"),
                                                    scale=alt.Scale(scheme='reds', reverse=True),
                                                    legend=alt.Legend(title="劣势特征")),
                                    tooltip=['特征', '权重']
                                ).properties(height=350)
                                st.altair_chart(donut_chart_c, use_container_width=True)
                        st.write("")
                        col_rose_c, col_empty_c = st.columns([1, 1])
                        with col_rose_c:
                            st.markdown("<h5 style='text-align: center;'>核心痛点分布 (南丁格尔玫瑰图)</h5>",
                                        unsafe_allow_html=True)
                            st.caption("视觉重点：颜色最深、半径最长的扇形即为第一大痛点，一眼看穿严重程度。")
                            if not df_neg_c.empty:
                                rose_chart_c = alt.Chart(df_neg_c).mark_arc(innerRadius=20, stroke="#fff").encode(
                                    theta=alt.Theta(field="特征", type="nominal",
                                                    sort=alt.SortField(field="权重", order="ascending")),
                                    radius=alt.Radius(field="权重", type="quantitative",
                                                      scale=alt.Scale(type="sqrt", zero=True, rangeMin=20)),
                                    color=alt.Color(field="特征", type="nominal",
                                                    sort=alt.SortField(field="权重", order="descending"),
                                                    scale=alt.Scale(scheme='redpurple', reverse=True),
                                                    legend=alt.Legend(title="痛点特征")),
                                    tooltip=['特征', '权重']
                                ).properties(height=400)
                                st.altair_chart(rose_chart_c, use_container_width=True)
                            else:
                                st.info(" 暂无负面痛点数据。")
                st.markdown("---")
                col_btn_c1, col_btn_c2 = st.columns(2)
                with col_btn_c1:
                    if st.button(" 重新排版竞品图表 (不耗AI额度)", key="btn_redraw_comp", type="primary", use_container_width=True):
                        pass
                with col_btn_c2:
                    btn_text_comp = f" 重新调用 AI 生成竞品报告" if selected_model == st.session_state.report_comp_model else f" 切换 {selected_model} 重新生成"
                    if st.button(btn_text_comp, key="btn_regen_comp", use_container_width=True, type="primary",
                                 disabled=not can_use_ai() or st.session_state.processing_comp):
                        st.session_state.report_comp = None
                        st.rerun()