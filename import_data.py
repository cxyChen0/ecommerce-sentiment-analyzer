import pandas as pd
import os
import db_manager
import re

DATA_DIR = "data_product"

# 主数据 data_*.csv 的精确定位字典（这个保持不变，因为阶段一跑得很完美）
CATEGORY_PREFIX_MAP = {
    "digital": ["phone", "earphone", "keyboard"],
    "lifestyle": ["pShell", "birthday", "sweater"],
    "snack": ["pie", "snakes"],
    "sports": ["exercise"]
}

# AI 打分文件的定位字典
ATTENTION_FILES = {
    "digital": "attention_digital_final1.csv",
    "lifestyle": "attention_lifestyle_final1.csv",
    "snack": "attention_snack_final1.csv",
    "sports": "attention_sports_final1.csv"
}


def clean_product_id(pid):
    """剔除所有隐藏字符、问号、字母，只保留纯数字"""
    if pd.isna(pid): return ""
    return re.sub(r'\D', '', str(pid))


def run_import():
    print(f"🚀 开始执行【带智能溯源修复】的数据入库流程 (目录: ./{DATA_DIR})...\n")

    # 1. 安全清空旧数据，防止重复叠加
    db_manager.init_ecommerce_db()
    db_manager.clear_ecommerce_data()

    global_valid_product_ids = set()
    title_to_true_id = {}  # {标题: 真商品ID}
    old_id_to_title = {}  # {旧商品ID: 标题}

    # =======================================================
    # 阶段一：导入商品元数据 (data_*.csv)，构建【真ID字典】
    # =======================================================
    print("📦 [阶段一] 开始导入商品元数据 (data_*.csv)")
    for category, prefixes in CATEGORY_PREFIX_MAP.items():
        all_meta_df = []
        for prefix in prefixes:
            file_path = os.path.join(DATA_DIR, f"data_{prefix}.csv")
            if os.path.exists(file_path):
                try:
                    df = pd.read_csv(file_path, encoding="utf-8-sig")
                except:
                    df = pd.read_csv(file_path, encoding="gbk")

                if not df.empty and '商品ID' in df.columns and '标题' in df.columns:
                    df['商品ID'] = df['商品ID'].apply(clean_product_id)
                    df = df[df['商品ID'] != '']
                    all_meta_df.append(df)

                    for _, row in df.iterrows():
                        title = str(row['标题']).strip()
                        true_id = row['商品ID']
                        if title and title != 'nan' and title not in title_to_true_id:
                            title_to_true_id[title] = true_id

        if all_meta_df:
            final_meta_df = pd.concat(all_meta_df, ignore_index=True)
            final_meta_df = final_meta_df.drop_duplicates(subset=['商品ID'])
            global_valid_product_ids.update(final_meta_df['商品ID'].tolist())
            db_manager.import_products_from_dataframe(final_meta_df, category)

    print(f"\n✅ 阶段一完成！登记 {len(global_valid_product_ids)} 个真商品，建立 {len(title_to_true_id)} 个标题映射。\n")

    # =======================================================
    # 阶段二：通吃所有 content_ 文件，构建【旧ID找标题字典】
    # =======================================================
    print("🕵️ [阶段二] 构建历史血缘字典 (通吃所有 content_*.csv/xlsx)...")
    for filename in os.listdir(DATA_DIR):
        if filename.startswith("content_") and filename.endswith((".csv", ".xlsx")):
            file_path = os.path.join(DATA_DIR, filename)
            try:
                # 兼容 Excel 和 CSV 双格式
                if filename.endswith(".xlsx"):
                    df_c = pd.read_excel(file_path)
                else:
                    try:
                        df_c = pd.read_csv(file_path, encoding="utf-8-sig")
                    except:
                        df_c = pd.read_csv(file_path, encoding="gbk")

                # 智能识别列名（兼容不同爬虫的命名习惯）
                id_col = next((col for col in df_c.columns if col in ['商品ID', '商品id', 'product_id']), None)
                title_col = next((col for col in df_c.columns if col in ['商品名称', '标题', 'title']), None)

                if id_col and title_col:
                    df_c[id_col] = df_c[id_col].apply(clean_product_id)
                    for _, row in df_c.iterrows():
                        old_id = row[id_col]
                        title = str(row[title_col]).strip()
                        if old_id and title and title != 'nan':
                            old_id_to_title[old_id] = title

                print(f"  读取内容字典: {filename} ({len(df_c)} 行)")
            except Exception as e:
                print(f"  ❌ 读取 {filename} 失败: {e}")

    print(f"✅ 历史字典构建完成，疯狂收集到 {len(old_id_to_title)} 个旧ID特征。\n")

    # =======================================================
    # 阶段三：导入 AI 评论，执行【智能孤儿救回】
    # =======================================================
    print("💬 [阶段三] 导入评论数据并执行孤儿救赎 (attention_*_final1.csv)")
    for category, file_name in ATTENTION_FILES.items():
        file_path = os.path.join(DATA_DIR, file_name)

        if os.path.exists(file_path):
            df_comments = pd.read_csv(file_path, encoding="utf-8-sig")

            if not df_comments.empty:
                df_comments['product_id'] = df_comments['product_id'].apply(clean_product_id)
                df_comments = df_comments[df_comments['product_id'] != '']

                valid_mask = df_comments['product_id'].isin(global_valid_product_ids)
                df_valid = df_comments[valid_mask].copy()
                df_orphans = df_comments[~valid_mask].copy()

                initial_orphans = len(df_orphans)
                recovered_count = 0

                if initial_orphans > 0:
                    for idx, row in df_orphans.iterrows():
                        old_id = row['product_id']
                        if old_id in old_id_to_title:
                            title = old_id_to_title[old_id]
                            if title in title_to_true_id:
                                true_id = title_to_true_id[title]
                                df_orphans.at[idx, 'product_id'] = true_id
                                recovered_count += 1

                    successfully_recovered = df_orphans[df_orphans['product_id'].isin(global_valid_product_ids)]
                    df_valid = pd.concat([df_valid, successfully_recovered], ignore_index=True)

                df_valid = df_valid.drop_duplicates(subset=['product_id', 'content'])
                still_lost = initial_orphans - recovered_count
                print(
                    f"  👉 [{category}] 初始孤儿: {initial_orphans} | 成功救回: {recovered_count} | 彻底抛弃: {still_lost}")

                db_manager.import_attention_comments_from_dataframe(df_valid)
                print(f"  ✅ 最终导入 {len(df_valid)} 条 {category} 的关联评论\n")

    print("🎉 全部数据入库及修复流程圆满完成！")


if __name__ == "__main__":
    run_import()