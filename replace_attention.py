import pandas as pd
import os
import re

# ===================== 终极评论清洗 + 打印删除内容 =====================
def clean_comments(input_csv, output_csv):
    try:
        # 自动编码兼容
        try:
            df = pd.read_csv(input_csv, encoding="utf-8-sig")
        except:
            df = pd.read_csv(input_csv, encoding="gbk")

        total_before = len(df)
        print(f"\n==================================================")
        print(f"📂 处理文件：{input_csv} | 总数：{total_before}")
        print(f"==================================================")

        # 统一转字符串
        df["content"] = df["content"].astype(str).str.strip()

        # ==============================================
        # 🔥 核心：只保留【吗？/么？/呢？】，其余所有?全部删除
        # ==============================================
        def clean_question_smart(text):
            text = re.sub(r'(?<![吗么呢])\?+', '', text)
            return text.strip()

        df["content"] = df["content"].apply(clean_question_smart)

        # ==============================================
        # 🔥 文本清洗工具函数
        # ==============================================
        def clean_text(text):
            text = re.sub(r'[^\w\s]', '', text)  # 去标点
            text = re.sub(r'\s+', '', text)       # 去空格
            text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)  # 去乱码
            return text

        # ==============================================
        # 🔥 最终版无意义评论判断（最精准规则）
        # ==============================================
        def is_useless(comment):
            c = str(comment).strip()
            cleaned_c = clean_text(c)

            # 空内容 / 纯标点
            if not c or re.fullmatch(r'[.。,，！!?\s]+', c):
                return True

            useless_keywords = [
                # 基础敷衍词
                "挺好", "不错", "还行", "一般", "挺好的", "还不错", "还可以",
                "很好", "满意", "非常满意", "五星好评", "好评", "默认好评",
                "先给个五星好评吧", "该用户未填写评价内容", "该用户觉得商品非常好，给出5星好评",
                # 新增无意义短短语
                "不错不错", "好的好的", "可以可以", "挺好挺好", "还可以吧", "还行吧",
                "完美好评", "满星好评", "货已收到", "过年囤货", "多次回购", "多次回购。",
                # 乱码/无效
                "好不错"
            ]

            # 匹配就删除
            for word in useless_keywords:
                if re.fullmatch(re.escape(word) + r'[.。！!?~～]*', c):
                    return True

            # 字数 < 2 删除
            if len(cleaned_c) < 2:
                return True

            return False

        # 执行过滤
        df["to_delete"] = df["content"].apply(is_useless)
        deleted_comments = df[df["to_delete"]]["content"].tolist()
        df_clean = df[~df["to_delete"]].copy().drop(columns=["to_delete"])

        # ==============================================
        # 📝 打印【被删除的评论】
        # ==============================================
        print(f"\n🗑️  本次删除的评论内容（共 {len(deleted_comments)} 条）：")
        if deleted_comments:
            for idx, content in enumerate(deleted_comments, 1):
                print(f"  {idx}. {content}")
        else:
            print(f"  无删除内容")

        # 保存
        df_clean.to_csv(output_csv, index=False, encoding="utf-8-sig")
        print(f"\n✅ 清洗完成！剩余有效评论：{len(df_clean)} 条")
        print(f"✅ 文件已保存：{output_csv}\n")

    except Exception as e:
        print(f"❌ 处理失败：{str(e)[:100]}")

# ===================== 批量处理 4 个 attention 文件 =====================
if __name__ == "__main__":
    files = [
        "attention_digital.csv",
        "attention_lifestyle.csv",
        "attention_snack.csv",
        "attention_sports.csv"
    ]

    for f in files:
        if os.path.exists(f):
            out = f.replace(".csv", "_cleaned1.csv")
            clean_comments(f, out)
        else:
            print(f"\n⚠️ 文件不存在：{f}")