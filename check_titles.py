import pandas as pd
import os

DATA_DIR = "data_product"
PREFIXES = ["phone", "earphone", "keyboard", "pShell", "birthday", "sweater", "pie", "snakes", "exercise"]

print("🔍 开始验证商品标题的唯一性...")
all_titles = []

for prefix in PREFIXES:
    file_path = os.path.join(DATA_DIR, f"data_{prefix}.csv")
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
        except:
            df = pd.read_csv(file_path, encoding="gbk")
        if '标题' in df.columns:
            all_titles.extend(df['标题'].dropna().astype(str).tolist())

total_titles = len(all_titles)
unique_titles = len(set(all_titles))
duplicates = total_titles - unique_titles

print(f"📊 统计结果：")
print(f"   总标题数量: {total_titles}")
print(f"   唯一标题数: {unique_titles}")
print(f"   重复标题数: {duplicates}")

if duplicates > 0:
    print("\n⚠️ 发现重复标题！处理策略：在入库关联时，将统一保留第一个匹配到的真商品 ID。")
else:
    print("\n✅ 完美！所有标题都是唯一的。")