import pandas as pd
import os
from collections import Counter

DATA_DIR = "data_product"
ATTENTION_FILES = {
    "digital": "attention_digital_final1.csv",
    "lifestyle": "attention_lifestyle_final1.csv",
    "snack": "attention_snack_final1.csv",
    "sports": "attention_sports_final1.csv"
}

print("🔍 开始验证 AI 打分后评论内容的唯一性...\n")

total_comments_all = 0
global_comments_list = []

for category, file_name in ATTENTION_FILES.items():
    file_path = os.path.join(DATA_DIR, file_name)
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        if 'content' in df.columns:
            # 提取当前品类的所有评论（转换为字符串并去除前后空格）
            comments = df['content'].astype(str).str.strip().tolist()

            total = len(comments)
            unique = len(set(comments))
            dups = total - unique

            total_comments_all += total
            global_comments_list.extend(comments)

            print(f"📦 [{category.upper()}] 总评论: {total} | 唯一: {unique} | 本品类重复: {dups}")
    else:
        print(f"⚠️ 找不到文件: {file_path}")

# ================= 全局去重统计 =================
global_unique = len(set(global_comments_list))
global_dups = total_comments_all - global_unique

print(f"\n📊 全局大盘统计结果：")
print(f"   所有品类总评论数: {total_comments_all}")
print(f"   全局绝对唯一条数: {global_unique}")
print(f"   全局绝对重复条数: {global_dups}")

if global_dups > 0:
    print("\n⚠️ 发现重复评论！(可能是刷单水军的通用话术跨商品出现)")
    print("   --- 以下是出现频率最高的 5 条重复评论 ---")

    # 找出重复的具体是哪些文本
    counter = Counter(global_comments_list)
    top_duplicates = counter.most_common(5)
    for text, count in top_duplicates:
        if count > 1:
            short_text = text[:50] + "..." if len(text) > 50 else text
            print(f"   重复 {count} 次 -> {short_text}")

    print("\n💡 处理策略：不用担心！在我们的 db_manager.py 中，")
    print("   有一句 df = df.drop_duplicates(subset=['product_id', 'content'])，")
    print("   它在入库前会自动拦截同一个商品下的重复评论。")
else:
    print("\n✅ 完美！经过你之前的清洗，所有打分评论 100% 绝对唯一。")