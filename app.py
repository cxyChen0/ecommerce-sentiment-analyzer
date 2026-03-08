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
# default_key_from_env = ""

st.set_page_config(page_title="基于AI的电商平台客户购买体验分析系统", page_icon="🛒", layout="wide")
db_manager.init_db()

#  CSS 样式注入：隐藏界面元素并极致压缩顶部空白 
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display: none;}

    /* 核心修改 1：强行覆盖主容器的顶部内边距 */
    [data-testid="block-container"] {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }

    /* 核心修改 2：压缩顶部 Header 的隐形占位高度，但保留小箭头 */
    [data-testid="stHeader"] {
        height: 2.5rem !important;
    }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

#  用户认证与额度管理系统 

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
        'admin': get_new_user_template('123456', '管理员')
    }
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'current_user_id' not in st.session_state: st.session_state.current_user_id = None
if 'current_role' not in st.session_state: st.session_state.current_role = None
if 'product_id' not in st.session_state: st.session_state.product_id = ""

def switch_page(page_name):
    st.session_state.auth_page = page_name
    st.rerun()


#  登录界面拦截
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.session_state.auth_page == 'login':
            st.title(":material/lock: 系统登录")
            login_user = st.text_input("用户名", value="admin")
            login_pwd = st.text_input("密码", value="123456", type="password")

            if st.button("登录", type="primary", use_container_width=True):
                # 接收三个返回值：成功标志, user_id, 角色
                success, user_id, role = db_manager.verify_login(login_user, login_pwd)
                if success:
                    st.session_state.logged_in = True
                    st.session_state.current_user = login_user
                    st.session_state.current_user_id = user_id  # 新增存储 ID
                    st.session_state.current_role = role
                    st.success("登录成功！")
                    st.rerun()
                else:
                    st.error("用户名或密码错误！")

            c1, c2 = st.columns(2)
            with c1:
                if st.button(":material/assignment_ind: 注册账号", use_container_width=True): switch_page('register')
            with c2:
                if st.button(":material/key: 修改密码", use_container_width=True): switch_page('reset_pwd')

        elif st.session_state.auth_page == 'register':
            st.title(":material/assignment_ind:  注册账号")
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
                    # 修改点写入数据库
                    success, msg = db_manager.register_user(reg_user, reg_pwd, reg_role)
                    if success:
                        st.success("注册成功，请返回登录！")
                    else:
                        st.error(msg)

            if st.button("返回登录", use_container_width=True): switch_page('login')

        elif st.session_state.auth_page == 'reset_pwd':
            st.title(":material/key: 修改密码")
            reset_user = st.text_input("用户名")
            reset_pwd = st.text_input("新密码", type="password")
            reset_pwd2 = st.text_input("确认新密码", type="password")

            if st.button("确认修改", type="primary", use_container_width=True):
                if reset_pwd != reset_pwd2:
                    st.error("两次输入密码不一致！")
                else:
                    # 修改点更新数据库
                    success, msg = db_manager.update_password(reset_user, reset_pwd)
                    if success:
                        st.success("密码修改成功，请返回登录！")
                    else:
                        st.error(msg)

            if st.button("返回登录", use_container_width=True): switch_page('login')

    st.stop()

#  登录后的额度刷新逻辑
user_data = db_manager.get_user_data_and_check_reset(st.session_state.current_user_id)

role = user_data['role']
spider_cnt = user_data['spider_count']
ai_cnt = user_data['ai_count']
dl_cnt = user_data['dl_count']

#  侧边栏 
with st.sidebar:
    st.info(f":material/account_circle: 当前用户: {st.session_state.current_user}\n\n"
            f":material/identity_platform: 角色: {role}")

    # 额度展示面板
    if role == '客户':
        st.markdown(f"**今日额度 (3次/日):**\n- 今日爬虫额度: {spider_cnt}/3\n- 今日 AI 额度: {ai_cnt}/3\n-  下载: {dl_cnt}/3")
    elif role == '商家':
        st.markdown(f"**今日免费额度 (10次/日):**\n- 今日爬虫额度: {spider_cnt}/10\n- 今日 AI 额度: {ai_cnt}/10")

    if st.button(":material/logout: 退出登录"):
        # 1. 彻底清空当前会话的所有缓存数据，防止不同账号数据串线
        for key in list(st.session_state.keys()):
            del st.session_state[key]

        # 2. 重新初始化最基础的未登录状态
        st.session_state.logged_in = False
        st.session_state.auth_page = 'login'
        st.session_state.current_page = 'main'

        # 3. 刷新页面
        st.rerun()


    #  管理员专属：全局后台入口 
    if role == '管理员':
        st.markdown("---")
        st.header(":material/manage_accounts: 系统全局管理")
        admin_btn_label = ":material/home: 返回分析大厅" if st.session_state.current_page == 'admin' else ":material/manage_search: 进入后台"

        if st.button(admin_btn_label, use_container_width=True, type="primary"):
            st.session_state.current_page = 'admin' if st.session_state.current_page != 'admin' else 'main'
            st.rerun()

    st.markdown("---")


    #  历史记录入口按钮 
    if role in ['商家', '管理员']:
        st.header(":material/History: 历史数据")
        # 根据当前页面，动态改变按钮文字
        btn_label = ":material/home: 返回分析大厅" if st.session_state.current_page == 'history' else ":material/deployed_code_history: 查看历史记录"

        if st.button(btn_label, use_container_width=True, type="primary"):
            # 切换状态并刷新页面
            st.session_state.current_page = 'main' if st.session_state.current_page == 'history' else 'history'
            st.rerun()

    if role != '客户': st.markdown("---")

    #  2. 模型选择
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

    #  3. API Key 隔离逻辑
    user_api_key = default_key_from_env
    is_using_custom_key = False
    if role != '管理员':
        if role == '商家':
            st.header(":material/settings: 配置API-key")
            if ai_cnt >= 10:
                st.warning(":material/warning: 今日免费额度已用尽，需配置自有 Key")
                user_api_key = st.text_input("API Key", value="", type="password", placeholder="请输入您的 API Key")
                if user_api_key:
                    is_using_custom_key = True  # 标记使用了自有 Key
            else:
                st.caption("正在使用系统自带的 API Key，您可配置自己的 API Key 解除 AI 额度限制")
                custom_key = st.text_input("自定义 API Key (选填)", value="", type="password")
                if custom_key: user_api_key = custom_key
                if custom_key:
                    user_api_key = custom_key
                    is_using_custom_key = True  # 标记使用了自有 Key

    else:
        # 极客细节：管理员平时什么都看不到，直接静默使用 default_key_from_env。
        # 但如果你的 .env 文件里忘记配 ALIYUN_API_KEY 了，才会弹出这个兜底输入框防止程序崩溃。
        if not default_key_from_env:
            st.error("系统环境变量缺失 API Key！")
            user_api_key = st.text_input("系统 API Key 兜底配置 (仅管理员可见)", type="password")

    st.markdown("---")
    # 1. 注入“相邻兄弟选择器 CSS 魔法
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

    # 2. 埋下隐形地雷 (Marker)，它在页面上看不见，但必须紧挨着目标按钮的上方！
    st.markdown('<span class="red-marker"></span>', unsafe_allow_html=True)

    # 3. 目标按钮 (注意：不再需要写 type="primary" 了，它会被上面的雷达强制锁定)
    if st.button(":material/delete: 清空当前页面记录", use_container_width=True):
        for k in list(st.session_state.keys()):
            # 保留关键的用户状态
            if k not in ['current_user', 'current_user_id', 'current_role', 'current_page', 'auth_status', 'logged_in',
                         'spider_cnt', 'ai_cnt', 'dl_cnt']:
                del st.session_state[k]
        st.rerun()

#  独立页面：历史记录看板
if st.session_state.current_page == 'history':
    st.title(f":material/data_table: {st.session_state.current_role}历史数据看板")

    import db_manager

    # 新增：将页面拆分为“可视化分析和“数据大盘管理两个标签页
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

                    # 只有当历史数据 >= 3 条时，才进行有意义的预测
                    if len(plot_df) >= 3:
                        try:
                            # 将日期字符串转为时间对象，再转为连续的数字序号（用于线性拟合）
                            plot_df['date_obj'] = pd.to_datetime(plot_df['日期'])
                            plot_df['date_num'] = plot_df['date_obj'].map(lambda x: x.toordinal())

                            # 1. 拟合销量趋势 (1维多项式 = 直线)
                            z_sales = np.polyfit(plot_df['date_num'], plot_df['销量'], 1)
                            p_sales = np.poly1d(z_sales)

                            # 2. 拟合好评率趋势
                            z_rate = np.polyfit(plot_df['date_num'], plot_df['预估好评率'], 1)
                            p_rate = np.poly1d(z_rate)

                            # 3. 生成未来 5 天的虚拟日期
                            last_date = plot_df['date_obj'].iloc[-1]
                            future_dates = [last_date + timedelta(days=i) for i in range(1, 6)]

                            pred_data = []
                            for d in future_dates:
                                d_num = d.toordinal()
                                # 预测销量并兜底（不能跌穿 0）
                                pred_sales = max(0, int(p_sales(d_num)))
                                # 预测好评率并卡死在 0% ~ 100% 之间
                                pred_rate = max(0.0, min(100.0, round(p_rate(d_num), 2)))

                                pred_data.append({
                                    '日期': d.strftime('%Y-%m-%d'),
                                    '销量': pred_sales,
                                    '预估好评率': pred_rate,
                                    '数据类型': '预测数据'
                                })

                            pred_df = pd.DataFrame(pred_data)

                            # 视觉优化：把历史最后一天的数据复制一份标记为"预测起点"
                            # 这样在图表上，历史实线和预测虚线就能无缝连接起来！
                            connection_point = plot_df.iloc[-1:].copy()
                            connection_point['数据类型'] = '预测数据'

                            combined_df = pd.concat([plot_df.drop(columns=['date_obj', 'date_num']),
                                                     connection_point.drop(columns=['date_obj', 'date_num']),
                                                     pred_df], ignore_index=True)
                        except Exception as e:
                            st.warning(f"数据波动异常，暂时无法生成预测折线：{e}")


                    st.markdown("### :material/area_chart:  数据走势与未来预测")
                    st.caption("实线为真实历史数据；虚线为 AI 根据历史线性拟合推演的未来 5 天趋势。")


                    #  新增交互规则：仅允许 X 轴(左右)平移，彻底禁用鼠标滚轮缩放

                    pan_only = alt.selection_interval(bind='scales', encodings=['x'], zoom=False)

                    col1, col2 = st.columns(2)

                    with col1:
                        # 新增：加上和单品分析一样的顶部描述
                        st.caption(":material/trending_up: 销量走势 (含未来5天推演数据)")
                        c1_base = alt.Chart(combined_df).mark_line(point=True).encode(
                            x=alt.X('日期:N', title=""),
                            y=alt.Y('销量:Q', title="", scale=alt.Scale(zero=False)),
                            # 核心修改：加上 legend=alt.Legend(title="", orient="bottom") 召唤出底部的节点类型图例
                            color=alt.Color('数据类型:N',
                                            scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                            range=['#4c78a8', '#f58518']),
                                            legend=alt.Legend(title="", orient="bottom")),
                            strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                                    range=[[1, 0], [5, 5]]),
                                                      legend=None),
                            tooltip=['日期', '销量', '数据类型']
                        )
                        # 兼容不同版本的 Altair 语法
                        c1 = c1_base.add_params(pan_only) if hasattr(c1_base, 'add_params') else c1_base.add_selection(
                            pan_only)
                        st.altair_chart(c1, use_container_width=True)

                    with col2:
                        # 新增：加上和单品分析一样的顶部描述
                        st.caption(":material/thumb_up: 好评率走势 (%)")
                        c2_base = alt.Chart(combined_df).mark_line(point=True).encode(
                            x=alt.X('日期:N', title=""),
                            y=alt.Y('预估好评率:Q', title="", scale=alt.Scale(zero=False)),
                            # 核心修改：加上 legend=alt.Legend(title="", orient="bottom") 召唤出底部的节点类型图例
                            color=alt.Color('数据类型:N',
                                            scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                            range=['#FF4B4B', '#f58518']),
                                            legend=alt.Legend(title="", orient="bottom")),
                            strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                                    range=[[1, 0], [5, 5]]),
                                                      legend=None),
                            tooltip=['日期', '预估好评率', '数据类型']
                        )
                        # 同上，注入防缩放的交互规则
                        c2 = c2_base.add_params(pan_only) if hasattr(c2_base, 'add_params') else c2_base.add_selection(
                            pan_only)
                        st.altair_chart(c2, use_container_width=True)

                    st.markdown("### :material/database:  详细数据明细 (含预测数据)")
                    # 表格展示预测合并后的数据
                    st.dataframe(combined_df, use_container_width=True)

                    st.download_button(
                        label=":material/download:  下载该商品历史及预测数据 (.csv)",
                        data=combined_df.to_csv(index=False).encode('utf-8-sig'),
                        file_name=f"{selected_item}_trend_prediction.csv",
                        mime='text/csv'
                    )

    # 新增：管理员/商家的增删改查后台
    with tab_edit:
        st.subheader(":material/edit_document: 管理我的所有追踪记录")
        st.caption("提示：双击单元格即可修改数据。选中行按 Delete 键可删除。点击底部加号可新增记录。")

        # 获取当前商家独有的全部数据
        df_my_stats = db_manager.get_merchant_product_stats(st.session_state.current_user_id)

        # --- 修改点：增加左右分栏结构，右侧放置蓝色的搜索按钮 ---
        col_search_input, col_search_btn = st.columns([5, 1])

        with col_search_input:
            search_my_pid = st.text_input(
                "搜索商品ID",  # 这个是必填项，但下面一行会把它隐藏掉
                placeholder=" 筛选商品 ID (支持模糊查询)",  # 提示文字放到了这里
                label_visibility="collapsed",  # 彻底隐藏上方的文字标签和留白
                key="search_merchant_pid"
            )

        with col_search_btn:
            st.button(":material/search: 搜索", type="primary", use_container_width=True)

        filtered_my_stats = df_my_stats.copy()
        if search_my_pid:
            # 采用模糊匹配，输入几个数字就能搜出来
            filtered_my_stats = filtered_my_stats[
                filtered_my_stats['product_id'].astype(str).str.contains(search_my_pid.strip(), case=False,
                                                                         na=False)
            ]
        

        edited_my_stats = st.data_editor(
            filtered_my_stats,  # 传入过滤后的表格
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
            # 关键修改：同时传入编辑后的数据和过滤前的原始数据，用于精准比对防止误删
            db_manager.sync_merchant_product_stats(edited_my_stats, filtered_my_stats,
                                                   st.session_state.current_user_id)
            st.toast(":material/check_circle: 您的历史数据更新成功！")

            import time
            time.sleep(1.2)
            st.rerun()

    # 执行到这里直接停止，不再向下渲染分析大厅的代码
    st.stop()

if st.session_state.current_page == 'admin':
    # 强制安全校验
    if st.session_state.current_role != '管理员':
        st.error(":material/gpp_maybe: 越权访问拦截：您不是管理员！")
        st.stop()

    st.title(":material/manage_search: 系统管理员全局控制台")
    st.caption("提示：在表格中双击单元格即可修改数据。选中行按 Delete 键可删除。点击底部加号可新增。")

    tab_users, tab_stats = st.tabs([":material/manage_accounts: 账号权限管控", ":material/database: 数据调控大盘"])

    with tab_users:
        st.subheader("全局用户表")
        df_users = db_manager.get_all_users_admin()

        #  新增：用户表的搜索过滤功能 (UI优化 + 模糊查询)
        col_u_search1, col_u_search2, col_u_btn = st.columns([4, 4, 1])
        with col_u_search1:
            search_u_id = st.text_input("搜索用户ID", placeholder=" 筛选用户 ID (模糊查询)",
                                        label_visibility="collapsed", key="search_u_id_input")
        with col_u_search2:
            search_u_name = st.text_input("搜索用户名", placeholder=" 搜索用户名 (模糊查询)",
                                          label_visibility="collapsed", key="search_u_name_input")
        with col_u_btn:
            st.button(":material/search: 搜索", key="btn_u_search", type="primary", use_container_width=True)

        # 复制一份 DataFrame 用于过滤
        filtered_users_df = df_users.copy()

        # 1. 按 ID 过滤 (模糊匹配)
        if search_u_id:
            filtered_users_df = filtered_users_df[
                filtered_users_df['id'].astype(str).str.contains(search_u_id.strip(), case=False, na=False)
            ]

        # 2. 按用户名过滤 (模糊匹配，大小写不敏感)
        if search_u_name:
            filtered_users_df = filtered_users_df[
                filtered_users_df['username'].astype(str).str.contains(search_u_name.strip(), case=False, na=False)
            ]

        # 使用 st.data_editor 开启交互式表格，传入过滤后的 DataFrame
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

            # 按钮必须换成 st.form_submit_button
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

        #  增加：联合查询过滤功能 (UI优化 + 模糊查询)
        col_search1, col_search2, col_btn = st.columns([4, 4, 1])
        with col_search1:
            search_uid = st.text_input("筛选用户ID", placeholder=" 筛选用户 ID (模糊查询)",
                                       label_visibility="collapsed", key="search_stats_uid_input")
        with col_search2:
            search_pid = st.text_input("筛选商品ID", placeholder=" 筛选商品 ID (模糊查询)",
                                       label_visibility="collapsed", key="search_stats_pid_input")
        with col_btn:
            st.button(":material/search: 搜索", key="btn_stats_search", type="primary", use_container_width=True)

        # 根据搜索框内容过滤 DataFrame
        filtered_df = df_stats.copy()

        # 1. 筛选用户 ID
        if search_uid:
            filtered_df = filtered_df[
                filtered_df['user_id'].astype(str).str.contains(search_uid.strip(), case=False, na=False)
            ]

        # 2. 筛选商品 ID
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
            # 传入编辑后的表格 edited_stats，以及过滤后的原始表格 filtered_df
            db_manager.sync_product_stats_admin(edited_stats, filtered_df)
            st.toast(" 商品历史数据同步完成！")
            import time
            time.sleep(1.2)
            st.rerun()

    # 执行到这里停止，阻止渲染主页内容
    st.stop()


st.title("基于AI的电商平台客户购买体验分析系统")

# 初始化状态
for key in ['last_query', 'product_info', 'report_single_model', 'report_market_model', 'report_comp_model']:
    if key not in st.session_state: st.session_state[key] = ""
if 'df_result' not in st.session_state: st.session_state.df_result = None
if 'analysis_type' not in st.session_state: st.session_state.analysis_type = None
if 'comp_comments' not in st.session_state: st.session_state.comp_comments = []
for key in ['report_single', 'report_market', 'report_comp']:
    if key not in st.session_state: st.session_state[key] = None
if 'processing_comp' not in st.session_state: st.session_state.processing_comp = False

#  权限校验函数 
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

# 

st.markdown("### :material/search: 目标商品搜索")
col_input, col_btn = st.columns([5, 1], vertical_alignment="bottom")

with col_input:
    user_input = st.text_input("输入框", placeholder="粘贴天猫/淘宝链接 或 输入关键词...",
                               label_visibility="collapsed")

with col_btn:
    start_analysis = st.button(":material/search_check_2: 立即分析", type="primary", use_container_width=True, disabled=not can_use_spider())


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



#  优化后的深色系映射画图函数 

def generate_wordcloud_image(word_freq_dict, theme='positive'):
    """直接接收 AI 提取的词频字典画图，支持权重越高，颜色越深的动态映射"""
    sys_type = platform.system()
    if sys_type == "Windows":
        font_path = "C:/Windows/Fonts/simhei.ttf"
    elif sys_type == "Darwin":
        font_path = "/System/Library/Fonts/PingFang.ttc"
    else:
        font_path = None

    # 1. 先使用默认配置创建 WordCloud 对象，让其计算出合理的字体大小
    wc = WordCloud(
        font_path=font_path,
        width=800, height=400,
        background_color='white',
        max_words=80
    ).generate_from_frequencies(word_freq_dict)

    # 2. 从计算好的 wc 对象中获取最大和最小字体大小，用于后续映射
    current_font_sizes = [v[1] for v in wc.layout_]
    if current_font_sizes:
        max_font = max(current_font_sizes)
        min_font = min(current_font_sizes)
    else:
        # 兜底方案
        max_font = 100
        min_font = 10

    # 3. 核心创新：定义动态颜色映射函数
    # 利用闭包特性，将 max_font 和 min_font 传入函数内部
    def dynamic_deep_color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        """
        根据字体大小（权重）动态计算颜色深浅。
        权重越大 (font_size 大) -> 亮度 (Lightness) 越低 -> 颜色越深。
        """
        # 防止分母为 0
        if max_font == min_font:
            normalized_size = 1.0
        else:
            # 将当前字体大小标准化到 0.0 - 1.0 的区间
            normalized_size = (font_size - min_font) / (max_font - min_font)

        # 定义亮度的映射区间 (HSL 中的 L)
        # 我们需要亮度在 [深色] 和 [中等深色] 之间变化，绝对不出现看不清的浅色
        # 这里使用标准化的二次方 (normalized_size ** 2) 来增加权重的对比度
        # 权重最大时 normalized_size=1 -> 亮度 L=15% (极深)
        # 权重最小时 normalized_size=0 -> 亮度 L=40% (可见的中等深色)
        lightness = 40 - (normalized_size ** 2) * 25  # 亮度区间在 15% - 40% 之间

        # 饱和度 (Saturation) 保持高饱和，确保色彩浓郁
        saturation = 90  # 90%

        # 色相 (Hue) 根据主题确定
        if theme == 'positive':
            hue = 120  # 标准绿色
        else:
            hue = 0  # 标准红色 (或者 360)

        # 返回 HSL 格式颜色字符串
        return f"hsl({hue}, {saturation}%, {int(lightness)}%)"

    # 4. 极其关键：将计算好的动态颜色函数应用到 wc 对象上
    # 这一步必须在 generate_from_frequencies 之后进行，因为需要用到 layout_ 数据
    wc.recolor(color_func=dynamic_deep_color_func)

    # 5. 渲染成图
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

        # 1. 极致模糊匹配键名 (涵盖了中英文的各种可能)
        target = None
        if any(w in k_lower for w in ["positive", "好评", "正面", "优点", "优势", "亮点", "满意", "好词"]):
            target = pos_data
        elif any(w in k_lower for w in
                 ["negative", "差评", "痛点", "缺点", "劣势", "不足", "抱怨", "吐槽", "负面", "坏词"]):
            target = neg_data

        if target is not None:
            # 2. 找到了目标，开始强行提取里面的特征和权重
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
            # 3. 如果当前 key 不是目标，但它的值是个字典或列表，可能是被 AI 嵌套在深层了，继续递归往下找！
            if isinstance(v, (dict, list)):
                _update_wordclouds(v, pos_data, neg_data)


def extract_dual_wordclouds(text):
    """终极鲁棒提取器 4.1：增加对 AI '平铺输出' 的兜底识别"""
    pos_data, neg_data = {}, {}
    blocks_to_try = []

    # 策略 1：标准的 Markdown JSON 提取
    blocks_to_try.extend(re.findall(r'`{3}(?:json)?\s*(.*?)\s*`{3}', text, re.DOTALL | re.IGNORECASE))

    # 策略 2：基于括号深度的精准剥离法
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

    # 新增：用于收集没有外层包裹的纯特征字典
    flat_dicts = []

    for block in blocks_to_try:
        block = block.strip()
        if not block: continue
        try:
            data = json.loads(block)
            # 1. 先尝试原有的嵌套识别逻辑
            _update_wordclouds(data, pos_data, neg_data)

            # 2. 兜底识别：如果它是一个纯粹的 "词汇: 数字" 字典
            if isinstance(data, dict) and len(data) > 0:
                # 检查是否所有 value 都是数字（说明这就是我们要的词云底层数据）
                is_flat = True
                for v in data.values():
                    # 允许整型、浮点型，或者能转成数字的字符串
                    if not (isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.', '', 1).isdigit())):
                        is_flat = False
                        break

                if is_flat:
                    # 强制转为浮点数存入平铺列表
                    flat_dicts.append({str(k): float(v) for k, v in data.items()})

        except json.JSONDecodeError:
            # 兼容残缺 JSON
            try:
                fixed_block = "{" + block + "}" if not block.startswith("{") else block
                data = json.loads(fixed_block)
                _update_wordclouds(data, pos_data, neg_data)
            except:
                pass

    # 触发兜底机制：如果没找到带标签的字典，就强行分配
    if not pos_data and not neg_data and len(flat_dicts) > 0:
        if len(flat_dicts) >= 1:
            pos_data.update(flat_dicts[0])  # 默认第一个字典是正面
        if len(flat_dicts) >= 2:
            neg_data.update(flat_dicts[1])  # 默认第二个字典是负面

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

        # inc_spider()  # 扣除抓取次数

        # 1. 适配爬虫的新返回值 (增加 sales_volume)
        if is_url(user_input):
            # 基于 ID 判断的拦截逻辑
            extracted_id = extract_product_id(user_input)
            if extracted_id == "未知ID":
                st.error(
                    " 格式错误：未在链接中检测到商品 ID。您上传的可能是搜索聚合页或无效链接，请点击进入具体商品详情页后再复制！")
                st.stop()  # 瞬间终止程序
            st.session_state.analysis_type = 'single'
            st.session_state.product_id = extract_product_id(user_input)
            with st.spinner(' 正在爬取商品数据与销量...'):
                res, title, sales_volume = run_spider(user_input, worker_id=1)

            if "Error" in res:
                st.error(res)
            else:
                st.session_state.product_info = title
                st.session_state.current_sales = sales_volume  # 暂存销量

                #  全局源头清洗：读取后立刻干掉无日期的数据 
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

#  展示与分析区 
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
            on_click=inc_dl  # 下载后触发次数累加
        )

    rpt_key = 'report_single' if is_single else 'report_market'
    mod_key = 'report_single_model' if is_single else 'report_market_model'
    saved_rpt = st.session_state[rpt_key]
    saved_mod = st.session_state[mod_key]

    st.markdown("###  深度分析报告")

    if saved_rpt:
        st.info(f"当前展示的是 **{saved_mod}** 生成的报告")

        # 1. 强力截断：找到第一个词云JSON的起点（包含可能存在的前置反引号），直接截断到全文末尾
        clean_report = saved_rpt

        think_content = ""

        # 策略 1：寻找标准的 <think> 标签 (DeepSeek 等原生支持)
        think_match = re.search(r'<think>(.*?)</think>', clean_report, flags=re.DOTALL | re.IGNORECASE)

        if think_match:
            think_content = think_match.group(1).strip()
            # 从正文中剔除
            clean_report = re.sub(r'<think>.*?</think>\n*', '', clean_report, flags=re.DOTALL | re.IGNORECASE)
        else:
            # 策略 2：兼容豆包等模型的自定义前缀文本
            # 匹配逻辑：从 "" 开始，一直抓取，直到遇到正式报告的标题（通常是换行后的 #）
            alt_match = re.search(r'(.*?)(?=\n#|\n---)', clean_report, flags=re.DOTALL)
            if alt_match:
                think_content = alt_match.group(1).strip()
                # 从正文中精确剔除这段思考文本
                clean_report = clean_report.replace(alt_match.group(0), "").strip()

        # 放宽约束：只要报告后半部分出现连续包含数字权重的 JSON 字典，就直接截断抹除
        clean_report = re.sub(r'\s*(?:`{3}(?:json)?\s*)?\{\s*".*?"\s*:\s*\d+[\s\S]*', '', clean_report,
                              flags=re.IGNORECASE)


        # 如果成功抓到了思考内容，就把它装进折叠面板
        if think_content:
            with st.expander(" 查看 AI 深度思考逻辑", expanded=False):
                st.caption("以下是 AI 总结报告前的数据梳理与推演过程：")
                st.markdown(think_content)

        # 2. 展示极其干净的报告干货
        st.markdown(clean_report.strip())

        # 从 session 的报告中解析 AI 词云字典并画图
        if st.session_state.df_result is not None:
            st.markdown("---")
            st.markdown("### :material/cloud: AI 提纯核心情感词云")
            st.caption("基于 AI 深度理解提取的产品特征与情感关键词，上方为正面好评，下方为负面差评。")
            with st.spinner("正在绘制词云图..."):
                try:
                    # 调用刚才写的强力提取器
                    pos_data, neg_data = extract_dual_wordclouds(saved_rpt)

                    # 1. 先渲染正面词云 (在上)
                    st.markdown("<h5 style='text-align: center; color: #2e7d32;'> 正面特征词云</h5>",
                                unsafe_allow_html=True)
                    if pos_data:
                        st.pyplot(generate_wordcloud_image(pos_data, theme='positive'))
                    else:
                        st.warning("未提取到正面数据")

                    st.write("")  # 增加一点上下间距

                    # 2. 再渲染负面词云 (在下)
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

            # 将字典转换为 DataFrame，只取 Top 10
            df_pos = pd.DataFrame(list(pos_data.items()), columns=['特征', '权重']).nlargest(10,
                                                                                             '权重') if pos_data else pd.DataFrame()
            df_neg = pd.DataFrame(list(neg_data.items()), columns=['特征', '权重']).nlargest(10,
                                                                                             '权重') if neg_data else pd.DataFrame()

            #  第一排：左饼图，右环形图 
            col_pie1, col_pie2 = st.columns(2)

            with col_pie1:
                st.markdown("<h5 style='text-align: center; color: #2e7d32;'> Top 10 正面好评占比 (饼图)</h5>",
                            unsafe_allow_html=True)
                if not df_pos.empty:
                    pie_chart = alt.Chart(df_pos).mark_arc(innerRadius=0, stroke="#fff").encode(
                        theta=alt.Theta(field="权重", type="quantitative"),
                        # 关键1强制按升序绘制，实现逆时针递减的视觉效果
                        order=alt.Order(field="权重", type="quantitative", sort="ascending"),
                        # 关键2Color绑定"特征"(显示文字图例)，同时按权重降序分色，reverse=True让权重最高的颜色最深
                        color=alt.Color(field="特征", type="nominal",
                                        sort=alt.SortField(field="权重", order="descending"),
                                        scale=alt.Scale(scheme='greens', reverse=True),
                                        legend=alt.Legend(title="好评特征")),  # 图例标题
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
                                        legend=alt.Legend(title="痛点特征")),  # 图例标题
                        tooltip=['特征', '权重']
                    ).properties(height=350)
                    st.altair_chart(donut_chart, use_container_width=True)

            #  第二排：南丁格尔玫瑰图 
            st.write("")  # 增加一些垂直间距
            col_rose, col_empty = st.columns([1, 1])  # 玫瑰图放左侧，右侧留白

            with col_rose:
                st.markdown("<h5 style='text-align: center;'>核心痛点分布 (南丁格尔玫瑰图)</h5>",
                            unsafe_allow_html=True)
                st.caption("视觉重点：颜色最深、半径最长的扇形即为第一大痛点，一眼看穿严重程度。")
                if not df_neg.empty:
                    rose_chart = alt.Chart(df_neg).mark_arc(innerRadius=20, stroke="#fff").encode(
                        # 角度：使用升序排列，让最大的扇形靠左（逆时针展开）
                        theta=alt.Theta(field="特征", type="nominal",
                                        sort=alt.SortField(field="权重", order="ascending")),

                        # 半径：代表权重大小
                        radius=alt.Radius(field="权重", type="quantitative",
                                          scale=alt.Scale(type="sqrt", zero=True, rangeMin=20)),

                        # 核心修改：将Color映射给特征召唤出文字图例，并按权重降序+反转色带，实现深色绑定大权重
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
            # 仅触发页面重绘，保留 AI 原始数据，每次词云排版都会有一点随机的改变
            if st.button(":material/replay: 重新生成排版图表 (不耗AI额度)", use_container_width=True, type="primary"):
                pass

        with col_btn2:
            btn_text = f":material/replay: 重新调用 AI 生成报告" if selected_model == saved_mod else f" 切换 {selected_model} 重新生成"
            # 这里会清空历史数据，强制重新调用 AI 接口
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
                # inc_ai()
                comments = df['content'].tolist()
                st.session_state[mod_key] = selected_model

                if is_single:
                    sales = st.session_state.get('current_sales', 0)
                    stream_gen = analyze_single_product_stream(
                        product_name=st.session_state.product_info,  # 传入商品标题
                        comments_list=comments,
                        sales_volume=sales,  # 传入抓取到的销量
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
                        # 发生错误时，强制清空缓存的坏报告，避免刷新后依然显示乱码
                        st.session_state[rpt_key] = None

                    elif "未配置" not in full_report:
                        # 确认成功生成，且用的是系统的免费额度，才真正扣减次数
                        if not is_using_custom_key:
                            inc_ai()

                        #  正则提取好评率并存入数据库
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
                            # 画图动作会交由上方的 saved_rpt 逻辑处理，保证刷新后也不消失
                        except Exception as e:
                            st.error(f"数据存档失败: {e}")
                        st.rerun()
                else:
                    stream_gen = analyze_market_trends_stream(
                        search_query=st.session_state.product_info,  # 传入搜索词
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



    # 只有商家或管理员，在单品分析模式下，且数据库中有数据时展示
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

            # 同样：满3条历史数据才触发预测
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

                    # 无缝连接点
                    connection_point = plot_df.iloc[-1:].copy()
                    connection_point['数据类型'] = '预测数据'

                    combined_df = pd.concat([plot_df.drop(columns=['date_obj', 'date_num']),
                                             connection_point.drop(columns=['date_obj', 'date_num']),
                                             pred_df], ignore_index=True)
                except Exception as e:
                    st.warning(f"数据波动异常，暂时无法生成预测折线：{e}")

            # 禁用缩放，仅允许 X 轴平移
            pan_only = alt.selection_interval(bind='scales', encodings=['x'], zoom=False)

            col1, col2 = st.columns(2)

            with col1:
                st.caption(":material/trending_up: 销量走势 (含未来5天推演数据)")
                c1_base = alt.Chart(combined_df).mark_line(point=True).encode(
                    x=alt.X('日期:N', title=""),
                    y=alt.Y('销量:Q', title="", scale=alt.Scale(zero=False)),
                    color=alt.Color('数据类型:N',
                                    scale=alt.Scale(domain=['真实数据', '预测数据'], range=['#4c78a8', '#f58518']),
                                    legend=alt.Legend(title="", orient="bottom")),
                    strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                            range=[[1, 0], [5, 5]]), legend=None),
                    tooltip=['日期', '销量', '数据类型']
                )
                c1 = c1_base.add_params(pan_only) if hasattr(c1_base, 'add_params') else c1_base.add_selection(pan_only)
                st.altair_chart(c1, use_container_width=True)

            with col2:
                st.caption(":material/thumb_up: 好评率走势 (%)")
                c2_base = alt.Chart(combined_df).mark_line(point=True).encode(
                    x=alt.X('日期:N', title=""),
                    y=alt.Y('预估好评率:Q', title="", scale=alt.Scale(zero=False)),
                    color=alt.Color('数据类型:N',
                                    scale=alt.Scale(domain=['真实数据', '预测数据'], range=['#FF4B4B', '#f58518']),
                                    legend=alt.Legend(title="", orient="bottom")),
                    strokeDash=alt.StrokeDash('数据类型:N', scale=alt.Scale(domain=['真实数据', '预测数据'],
                                                                            range=[[1, 0], [5, 5]]), legend=None),
                    tooltip=['日期', '预估好评率', '数据类型']
                )
                c2 = c2_base.add_params(pan_only) if hasattr(c2_base, 'add_params') else c2_base.add_selection(pan_only)
                st.altair_chart(c2, use_container_width=True)

    #  竞品比对区 
    if is_single and st.session_state.report_single:
        st.markdown("---")
        st.markdown("###  进阶功能：竞品比对")

        # 如果是客户，不让用这个功能
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
                        # inc_spider()
                        st.rerun()
                else:
                    if st.button(":material/repeat: 重新抓取", disabled=st.session_state.processing_comp, type="primary"):
                        st.session_state.comp_comments = []
                        st.session_state.report_comp = None
                        st.rerun()
            with col_act2:
                if has_comp_data: st.success(f" 已就绪：{len(st.session_state.comp_comments)} 条竞品数据")

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

                        for i, (res_file, _, _) in enumerate(results):
                            progress_bar.progress((i + 1) / len(comp_links))
                            if res_file and "Error" not in res_file:
                                try:
                                    c_df = pd.read_csv(res_file, encoding='utf-8-sig')
                                    #  竞品数据也同样清洗无日期的废话
                                    if 'date' in c_df.columns:
                                        c_df['date_clean'] = c_df['date'].astype(str).str.strip().str.lower()
                                        c_df = c_df[~c_df['date_clean'].isin(['nan', 'none', '', 'nat', 'null'])]
                                    #
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

            # 数据展示与生成报告
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
                    # inc_ai()
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
                        # 发生错误时清空，避免残留
                        st.session_state.report_comp = None

                    elif "未配置" not in full_report:
                        if not is_using_custom_key:
                            inc_ai()
                        st.rerun()



            if st.session_state.report_comp:
                st.markdown("---")
                st.subheader(":material/balance: 竞品差异化对比报告")
                st.info(f"由模型 **{st.session_state.report_comp_model}** 生成")

                # 强力抹除竞品报告正文里的 JSON 乱码 (完美解决 undefined 未闭合代码块问题)
                clean_comp_report = st.session_state.report_comp

                #  新增：提取并折叠深度思考过程
                think_content_comp = ""

                # 策略 1：寻找标准的 <think> 标签 (DeepSeek 等原生支持)
                think_match_comp = re.search(r'<think>(.*?)</think>', clean_comp_report,
                                             flags=re.DOTALL | re.IGNORECASE)

                if think_match_comp:
                    think_content_comp = think_match_comp.group(1).strip()
                    # 从正文中剔除
                    clean_comp_report = re.sub(r'<think>.*?</think>\n*', '', clean_comp_report,
                                               flags=re.DOTALL | re.IGNORECASE)
                else:
                    # 策略 2：兼容豆包等模型的自定义前缀文本
                    alt_match_comp = re.search(r'(.*?)(?=\n#|\n---)', clean_comp_report, flags=re.DOTALL)
                    if alt_match_comp:
                        think_content_comp = alt_match_comp.group(1).strip()
                        # 从正文中精确剔除这段思考文本
                        clean_comp_report = clean_comp_report.replace(alt_match_comp.group(0), "").strip()

                clean_comp_report = re.sub(r'\s*(?:`{3}(?:json)?\s*)?\{\s*".*?"\s*:\s*\d+[\s\S]*', '', clean_comp_report, flags=re.IGNORECASE)


                # 如果成功抓到了思考内容，就把它装进折叠面板
                if think_content_comp:
                    with st.expander(" 查看 AI 深度思考逻辑", expanded=False):
                        st.caption("以下是 AI 总结报告前的数据梳理与推演过程：")
                        st.markdown(think_content_comp)

                # 展示极其干净的报告干货正文
                st.markdown(clean_comp_report.strip())

                pos_data_c, neg_data_c = {}, {}

                # 解析竞品的双词云
                try:
                    # 调用强力提取器
                    pos_data_c, neg_data_c = extract_dual_wordclouds(st.session_state.report_comp)

                    # 1. 先渲染优势词云 (在上)
                    st.markdown("<h5 style='text-align: center; color: #2e7d32;'> 本品核心优势词云</h5>",
                                unsafe_allow_html=True)
                    if pos_data_c:
                        st.pyplot(generate_wordcloud_image(pos_data_c, theme='positive'))
                    else:
                        st.warning("未提取到优势数据")

                    st.write("")  # 增加一点上下间距

                    # 2. 再渲染劣势词云 (在下)
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

                        # 将竞品字典转换为 DataFrame，取 Top 10
                        df_pos_c = pd.DataFrame(list(pos_data_c.items()), columns=['特征', '权重']).nlargest(10,
                                                                                                             '权重') if pos_data_c else pd.DataFrame()
                        df_neg_c = pd.DataFrame(list(neg_data_c.items()), columns=['特征', '权重']).nlargest(10,
                                                                                                             '权重') if neg_data_c else pd.DataFrame()

                        #  第一排：左饼图，右环形图 
                        col_pie1_c, col_pie2_c = st.columns(2)

                        with col_pie1_c:
                            st.markdown("<h5 style='text-align: center; color: #2e7d32;'> Top 10 核心优势占比</h5>",
                                        unsafe_allow_html=True)
                            if not df_pos_c.empty:
                                pie_chart_c = alt.Chart(df_pos_c).mark_arc(innerRadius=0, stroke="#fff").encode(
                                    theta=alt.Theta(field="权重", type="quantitative"),
                                    # 关键 1：逆时针排布强制令其按升序绘制，使得最大的色块被挤压到左侧（12点钟逆时针方向）
                                    order=alt.Order(field="权重", type="quantitative", sort="ascending"),
                                    # 关键 2：文字图例 + 权重颜色深度Color绑定到特征(保留文字图例)，但根据权重降序排列颜色分配，并开启 reverse=True (最重=最深)
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

                        #  第二排：右下角南丁格尔玫瑰图 
                        st.write("")
                        # 左侧给玫瑰图，右侧留空
                        col_rose_c, col_empty_c = st.columns([1, 1])

                        with col_rose_c:
                            st.markdown("<h5 style='text-align: center;'>核心痛点分布 (南丁格尔玫瑰图)</h5>",
                                        unsafe_allow_html=True)
                            st.caption("视觉重点：颜色最深、半径最长的扇形即为第一大痛点，一眼看穿严重程度。")
                            if not df_neg_c.empty:
                                rose_chart_c = alt.Chart(df_neg_c).mark_arc(innerRadius=20, stroke="#fff").encode(
                                    # 角度排布
                                    theta=alt.Theta(field="特征", type="nominal",
                                                    sort=alt.SortField(field="权重", order="ascending")),

                                    # 半径排布
                                    radius=alt.Radius(field="权重", type="quantitative",
                                                      scale=alt.Scale(type="sqrt", zero=True, rangeMin=20)),

                                    # 核心修改：同上，映射名义变量召唤图例，并严格挂钩权重深度
                                    color=alt.Color(field="特征", type="nominal",
                                                    sort=alt.SortField(field="权重", order="descending"),
                                                    scale=alt.Scale(scheme='redpurple', reverse=True),
                                                    legend=alt.Legend(title="痛点特征")),
                                    tooltip=['特征', '权重']
                                ).properties(height=400)
                                st.altair_chart(rose_chart_c, use_container_width=True)
                            else:
                                st.info(" 暂无负面痛点数据。")
                # 竞品比对报告的重新生成按钮
                st.markdown("---")
                col_btn_c1, col_btn_c2 = st.columns(2)

                with col_btn_c1:
                    # 添加 key 防止与上面的按钮冲突
                    if st.button(" 重新排版竞品图表 (不耗AI额度)", key="btn_redraw_comp", type="primary", use_container_width=True):
                        pass

                with col_btn_c2:
                    btn_text_comp = f" 重新调用 AI 生成竞品报告" if selected_model == st.session_state.report_comp_model else f" 切换 {selected_model} 重新生成"
                    if st.button(btn_text_comp, key="btn_regen_comp", use_container_width=True, type="primary",
                                 disabled=not can_use_ai() or st.session_state.processing_comp):
                        st.session_state.report_comp = None
                        st.rerun()