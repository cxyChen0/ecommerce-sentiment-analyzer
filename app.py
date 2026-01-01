import os
import time
import re
import streamlit as st
import pandas as pd
import concurrent.futures
from dotenv import load_dotenv

# 引入后端函数
from crawler import run_spider, get_search_links
# 引入新的流式函数
from analysis import (
    analyze_single_product_stream,
    analyze_market_trends_stream,
    analyze_competitor_comparison_stream
)

load_dotenv()
default_key_from_env = os.getenv("ALIYUN_API_KEY")

st.set_page_config(page_title="电商智能选品分析系统", layout="wide")
st.markdown("<style>.stAppDeployButton {display:none;}</style>", unsafe_allow_html=True)

# === 侧边栏 ===
with st.sidebar:
    st.header("⚙️ 智能配置")
    user_api_key = st.text_input("阿里云百炼 API Key", value=default_key_from_env or "", type="password")
    st.markdown("---")
    st.header("🧠 AI 模型选择")
    selected_model = st.selectbox(
        "选择分析模型",
        ("deepseek-v3.2-exp", "deepseek-r1-0528", "qwen3-vl-32b-thinking", "qwen3-max"),
        index=0
    )
    st.markdown("---")
    if st.button("🗑️ 清空所有记录"):
        st.session_state.clear()
        st.rerun()

st.title("🛒 电商评论情感分析与竞品比对系统")

# === 初始化状态 ===
if 'last_query' not in st.session_state: st.session_state.last_query = ""
if 'df_result' not in st.session_state: st.session_state.df_result = None
if 'analysis_type' not in st.session_state: st.session_state.analysis_type = None
if 'product_info' not in st.session_state: st.session_state.product_info = ""
if 'comp_comments' not in st.session_state: st.session_state.comp_comments = []

# 报告状态
if 'report_single' not in st.session_state: st.session_state.report_single = None
if 'report_market' not in st.session_state: st.session_state.report_market = None
if 'report_comp' not in st.session_state: st.session_state.report_comp = None

# 模型记录状态
if 'report_single_model' not in st.session_state: st.session_state.report_single_model = ""
if 'report_market_model' not in st.session_state: st.session_state.report_market_model = ""
if 'report_comp_model' not in st.session_state: st.session_state.report_comp_model = ""

# 标志位
if 'processing_comp' not in st.session_state: st.session_state.processing_comp = False

# === 智能输入区 (优化版：增加按钮，解决回车无效问题) ===
st.markdown("### 🔍 智能搜索")
col_input, col_btn = st.columns([5, 1], vertical_alignment="bottom")

with col_input:
    user_input = st.text_input(
        "输入框",
        placeholder="👉 粘贴天猫/淘宝链接（单品分析） 或 输入关键词（自动竞品调研）...",
        label_visibility="collapsed"
    )

with col_btn:
    # 显式的搜索按钮
    start_analysis = st.button("🚀 立即分析", type="primary", use_container_width=True)


def is_url(text): return re.search(r'(http|https|tmall\.com|taobao\.com)', text)


# === 触发逻辑 (同时支持回车和按钮点击) ===
# 逻辑：如果点击了按钮，或者输入内容发生了变化且不为空
trigger_search = start_analysis or (user_input and user_input != st.session_state.last_query)

if trigger_search:
    st.session_state.last_query = user_input

    # === 强制重置所有旧状态 (解决“无法输入”的核心) ===
    st.session_state.df_result = None
    st.session_state.comp_comments = []  # 清空之前的竞品
    st.session_state.report_single = None
    st.session_state.report_market = None
    st.session_state.report_comp = None
    st.session_state.report_comp_model = ""
    st.session_state.processing_comp = False  # 重置处理标志位

    if is_url(user_input):
        # === 模式 A：单品分析 ===
        st.session_state.analysis_type = 'single'
        st.toast("🔗 识别为链接，开始单品分析...")
        with st.spinner('🕷️ 正在爬取商品评论数据...'):
            res, title = run_spider(user_input, worker_id=1)
        if "Error" in res:
            st.error(res)
        else:
            st.session_state.product_info = title
            st.session_state.df_result = pd.read_csv(res, encoding='utf-8-sig')
            st.success("抓取成功")
    else:
        # === 模式 B：关键词自动竞品/市场调研 ===
        st.session_state.analysis_type = 'market'
        st.toast(f"🔍 识别为关键词，自动启动全网竞品调研...")
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
            st.error("未找到相关商品，请尝试更换关键词")

# === 展示与分析区 ===
if st.session_state.df_result is not None:
    df = st.session_state.df_result
    st.markdown("---")

    # 根据模式显示不同的标题
    is_single = (st.session_state.analysis_type == 'single')
    if is_single:
        st.subheader(f"📦 本品数据：{st.session_state.product_info}")
        expander_title = "📝 查看本品原始评论 & 下载"
        download_name = "single_product_data.csv"
    else:
        st.subheader(f"📊 市场调研数据：{st.session_state.product_info}")
        expander_title = "📝 查看采集到的竞品/市场评论 & 下载"
        download_name = "market_research_data.csv"

    with st.expander(expander_title, expanded=False):
        st.dataframe(df, use_container_width=True)
        st.download_button(
            label="📥 下载当前分析数据 (.csv)",
            data=df.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"{download_name}_{int(time.time())}.csv",
            mime='text/csv'
        )

    # 确定当前页面对应的 Key
    rpt_key = 'report_single' if is_single else 'report_market'
    mod_key = 'report_single_model' if is_single else 'report_market_model'

    saved_rpt = st.session_state[rpt_key]
    saved_mod = st.session_state[mod_key]

    # === AI 分析区 ===
    st.markdown("### 🧠 深度分析报告")

    ai_btn_disabled = False
    if not user_api_key:
        st.warning("⚠️ 请先在侧边栏配置阿里云 API Key")
        ai_btn_disabled = True

    # 如果已有报告
    if saved_rpt:
        st.info(f"当前展示的是 **{saved_mod}** 生成的报告")
        st.markdown(saved_rpt)
        st.markdown("---")

        btn_text = f"🔄 切换到 {selected_model} 并重新生成" if selected_model != saved_mod else "🔄 重新生成"

        if st.button(btn_text, disabled=ai_btn_disabled or st.session_state.processing_comp):
            st.session_state[rpt_key] = None
            st.session_state[mod_key] = ""
            st.rerun()

    # 如果没有报告
    else:
        # 按钮文案区分
        gen_btn_text = "✨ 生成单品体验报告" if is_single else "✨ 生成市场趋势/竞品调研报告"

        if st.button(f"{gen_btn_text} ({selected_model})", type="primary", disabled=ai_btn_disabled):
            comments = df['content'].tolist()
            st.session_state[mod_key] = selected_model

            if is_single:
                stream_gen = analyze_single_product_stream(comments, user_api_key, model=selected_model)
            else:
                stream_gen = analyze_market_trends_stream(comments, user_api_key, model=selected_model)

            full_text = st.write_stream(stream_gen)
            st.session_state[rpt_key] = full_text
            st.rerun()

    # === 竞品比对区 (仅在单品分析模式下出现) ===
    # 逻辑：如果是关键词搜索（市场模式），本身就是竞品分析，不需要再显示这个区域
    if is_single and st.session_state.report_single:
        st.markdown("---")
        st.markdown("### ⚔️ 进阶功能：竞品比对")
        st.caption("已完成本品分析，现在可以采集竞品数据进行差异化比对。")

        has_comp_data = len(st.session_state.comp_comments) > 0

        # 1. 顶部操作栏
        col_act1, col_act2 = st.columns([1, 4])
        with col_act1:
            if not has_comp_data:
                # 抓取按钮
                if st.button("🔍 自动抓取 3 个竞品", disabled=st.session_state.processing_comp or ai_btn_disabled):
                    st.session_state.processing_comp = True
                    st.rerun()
            else:
                # 清空按钮
                if st.button("🔄 清空竞品重抓", disabled=st.session_state.processing_comp):
                    st.session_state.comp_comments = []
                    st.session_state.report_comp = None
                    st.session_state.report_comp_model = ""
                    st.rerun()

        with col_act2:
            if has_comp_data:
                st.success(f"✅ 已就绪：{len(st.session_state.comp_comments)} 条竞品数据")
            elif st.session_state.processing_comp:
                st.info("🏃‍♂️ 正在努力抓取中，请稍候...")

        # 2. 抓取逻辑
        if st.session_state.processing_comp and not has_comp_data:
            target_product = st.session_state.product_info
            if not target_product or target_product == "未知商品":
                st.warning("未能获取商品标题。")
                st.session_state.processing_comp = False
                st.rerun()
            else:
                st.toast(f"搜索竞品：{target_product[:15]}...")
                with st.status("正在寻找并采集最强对手数据...", expanded=True) as status:
                    st.write("🔍 正在搜索竞品链接...")
                    comp_links = get_search_links(target_product, count=3)

                    if comp_links:
                        st.write(f"✅ 找到 {len(comp_links)} 个竞品，启动多线程采集...")
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
                                    temp_comp_comments.extend(c_df['content'].tolist())
                                except:
                                    pass

                        if len(temp_comp_comments) == 0:
                            status.update(label="❌ 采集失败", state="error")
                            st.error("未采集到有效评论。")
                        else:
                            st.session_state.comp_comments = temp_comp_comments
                            status.update(label="✅ 采集完成！", state="complete")
                            time.sleep(1)
                    else:
                        status.update(label="❌ 未找到竞品链接", state="error")
                        st.error("未找到相关竞品链接。")

                st.session_state.processing_comp = False
                st.rerun()

        # 3. 数据展示与下载
        if has_comp_data:
            df_comp_display = pd.DataFrame({'content': st.session_state.comp_comments})
            df_comp_display['source'] = '竞品'
            df_main_display = df.copy()
            df_main_display['source'] = '本品'
            df_all = pd.concat([df_main_display[['content', 'source']], df_comp_display[['content', 'source']]],
                               ignore_index=True)

            with st.expander("📊 展开查看竞品详情 & 下载合并数据集", expanded=True):
                st.markdown(f"**数据概览：** 本品 `{len(df)}` 条 vs 竞品 `{len(df_comp_display)}` 条")
                st.dataframe(df_comp_display.head(50), use_container_width=True, height=200)

                st.download_button(
                    label="📥 下载完整对比数据集 (本品+竞品 .csv)",
                    data=df_all.to_csv(index=False).encode('utf-8-sig'),
                    file_name=f"compare_data_full_{int(time.time())}.csv",
                    mime='text/csv',
                    key='dl_comp_all'
                )

            # 4. 生成报告按钮
            st.markdown("###")
            btn_label = f"⚖️ 开始生成竞品对比报告 ({selected_model})"
            if st.session_state.report_comp:
                btn_label = "🔄 重新生成对比报告"

            if st.button(btn_label, type="primary", disabled=ai_btn_disabled or st.session_state.processing_comp,
                         use_container_width=True):
                main_comments = df['content'].tolist()
                comp_comments = st.session_state.comp_comments
                st.session_state.report_comp_model = selected_model

                stream_gen = analyze_competitor_comparison_stream(
                    st.session_state.product_info,
                    main_comments,
                    comp_comments,
                    user_api_key,
                    model=selected_model
                )

                st.session_state.report_comp = st.write_stream(stream_gen)
                st.rerun()

        # 5. 报告展示
        if st.session_state.report_comp:
            st.markdown("---")
            st.subheader("⚖️ 竞品差异化对比报告")
            st.info(f"由模型 **{st.session_state.report_comp_model}** 生成")
            st.markdown(st.session_state.report_comp)