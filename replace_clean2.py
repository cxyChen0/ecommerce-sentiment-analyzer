import pandas as pd
import os
import re

# ===================== 精准清洗：剔除无意义短评 =====================
def clean_comments_final_precise(input_csv, output_csv):
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

        # 改成你的列名：评论
        df["content"] = df["content"].astype(str).str.strip()

        # --------------------------
        # 1. 智能去问号（保留吗？么？呢？）
        # --------------------------
        def clean_question(text):
            return re.sub(r'(?<![吗么呢])\?+', '', text).strip()
        df["content"] = df["content"].apply(clean_question)

        # --------------------------
        # 2. 去标点+空格（用于判断）
        # --------------------------
        def clean_text(text):
            text = re.sub(r'[^\w\s]', '', text)  # 去标点
            text = re.sub(r'\s+', '', text)       # 去空格
            text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)  # 去特殊字符/乱码
            return text

        # --------------------------
        # 3. 终极黑名单：无意义短语（精准剔除）
        # --------------------------
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

        def need_delete(comment):
            c = str(comment).strip()
            cleaned_c = clean_text(c)

            # 规则1：空内容/纯标点/纯表情 → 删
            if not c or re.fullmatch(r'[^\w\s]+', c) or re.fullmatch(r'[😀😆😋👍☺️👌🏻]+', c):
                return True

            # 规则2：完全匹配黑名单 → 删（精准剔除无意义）
            for kw in useless_keywords:
                # 兼容带少量标点的情况（比如“不错不错！”“完美好评～”）
                if re.fullmatch(re.escape(kw) + r'[.。！!?~～]*', c):
                    return True

            # 规则3：去标点后字数＜2（完全没信息）→ 删
            if len(cleaned_c) < 2:
                return True

            # 规则4：仅含“回购/囤货/收到”无实质描述 → 删
            if re.search(r'^(多次回购|过年囤货|货已收到)[.。！!?]*$', c):
                return True

            # 其他有信息的（哪怕短）→ 保留！
            return False

        # 执行过滤
        df["to_del"] = df["content"].apply(need_delete)
        deleted_list = df[df["to_del"]]["content"].tolist()
        kept_list = df[~df["to_del"]]["content"].tolist()
        # 单独提取保留的短评论（方便你核对）
        kept_short_list = df[~df["to_del"] & (df["content"].apply(lambda x: len(clean_text(x)) < 5))]["content"].tolist()

        df_clean = df[~df["to_del"]].drop(columns=["to_del"])

        # --------------------------
        # 打印日志（精准展示删/留）
        # --------------------------
        print(f"\n🗑️  精准删除的无意义评论（共 {len(deleted_list)} 条）：")
        for i, content in enumerate(deleted_list, 1):
            print(f" {i}. {content}")

        print(f"\n✅ 保留的有效评论（共 {len(kept_list)} 条）")
        print(f"✅ 其中短而有价值的评论（共 {len(kept_short_list)} 条）：")
        for i, content in enumerate(kept_short_list[:20], 1):  # 只打印前20条，避免日志过长
            print(f" {i}. {content}")
        if len(kept_short_list) > 20:
            print(f" ... 还有 {len(kept_short_list)-20} 条有价值短评论")

        # 保存最终文件
        df_clean.to_csv(output_csv, index=False, encoding="utf-8-sig")
        print(f"\n✅ 最终清洗完成！有效评论：{len(df_clean)} 条")
        print(f"✅ 已保存：{output_csv}")

    except Exception as e:
        print(f"❌ 错误：{str(e)[:100]}")

# ===================== 批量处理4个文件 =====================
if __name__ == "__main__":
    input_files = [
        "cleaned_digital3.csv",
        "cleaned_lifestyle3.csv",
        "cleaned_snack3.csv",
        "cleaned_sports3.csv"
    ]

    for f in input_files:
        if os.path.exists(f):
            out = f.replace("3.csv", ".csv")  # 输出 cleaned_xxx.csv
            clean_comments_final_precise(f, out)
        else:
            print(f"⚠️ 文件不存在：{f}")