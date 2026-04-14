import pandas as pd
import os

# ===================== 自动替换不匹配评论：直接用cleaned版本覆盖 =====================
def build_attention_cleaned_auto_fix():
    categories = ["digital", "lifestyle", "snack", "sports"]

    for cat in categories:
        file_clean = f"cleaned_{cat}.csv"
        file_attn = f"attention_{cat}_cleaned.csv"
        out_file = f"attention_{cat}_cleaned1.csv"

        # 文件存在检查
        if not os.path.exists(file_clean):
            print(f"⚠️ {cat} 缺失：{file_clean}")
            continue
        if not os.path.exists(file_attn):
            print(f"⚠️ {cat} 缺失：{file_attn}")
            continue

        # 读取数据
        df_clean = pd.read_csv(file_clean, encoding="utf-8-sig")
        df_attn = pd.read_csv(file_attn, encoding="utf-8-sig")

        # 行数校验
        if len(df_clean) != len(df_attn):
            print(f"❌ {cat} 行数不匹配！跳过！")
            continue

        # ===================== 核心：逐行校验 + 自动替换 =====================
        content_clean = df_clean["content"].astype(str).str.strip()
        content_attn = df_attn["content"].astype(str).str.strip()
        match_mask = (content_clean == content_attn)
        match_rate = match_mask.mean()

        if match_rate < 1.0:
            print(f"⚠️ {cat} 发现 {len(match_mask) - match_mask.sum()} 条不匹配评论，将自动替换为cleaned版本")
            print(f"   匹配率：{match_rate:.2%}")
            # 直接用cleaned的content覆盖attention的content
            df_attn["content"] = df_clean["content"].values
        else:
            print(f"✅ {cat} 评论内容 100% 匹配，无需修改！")

        # 拼接成 6 列（现在content已经和cleaned完全一致）
        result = pd.DataFrame({
            "product_id": df_clean["product_id"].values,
            "content": df_clean["content"].values,
            "product": df_attn["product"].values,
            "service": df_attn["service"].values,
            "logistics": df_attn["logistics"].values,
            "price": df_attn["price"].values
        })

        # 保存
        result.to_csv(out_file, index=False, encoding="utf-8-sig")
        print(f"📦 已生成：{out_file} | 共 {len(result)} 行\n")

if __name__ == "__main__":
    build_attention_cleaned_auto_fix()