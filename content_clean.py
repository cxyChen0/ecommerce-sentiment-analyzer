import pandas as pd
import os
import re

# ===================== 清洗规则 =====================
def is_invalid_comment(text):
    if not isinstance(text, str):
        return True
    text = text.strip()

    if len(text) < 4:
        return True

    default_keywords = [
        "系统默认好评", "自动好评", "此用户没有填写", "评价方未及时做出评价",
        "未及时主动评价", "默认好评", "系统自动评价", "暂无评价"
    ]
    for kw in default_keywords:
        if kw in text:
            return True

    ad_patterns = [
        r"\d+元红包", r"红包\d{1,2}:\d{2}", r"满\d+减\d+",
        r"点击领取", r"加微信", r"扫码", r"复制口令", r"淘宝客"
    ]
    for pat in ad_patterns:
        if re.search(pat, text):
            return True

    if re.search(r"1[3-9]\d{9}", text):
        return True
    if re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
        return True

    return False

# ===================== 万能读取 =====================
def read_file_safely(file_path):
    try:
        if file_path.endswith(".csv"):
            encodings = ["utf-8-sig", "gbk", "gb2312", "utf-8"]
            for enc in encodings:
                try:
                    return pd.read_csv(file_path, encoding=enc)
                except:
                    continue
        elif file_path.endswith(".xlsx"):
            return pd.read_excel(file_path)
    except:
        pass
    return pd.DataFrame()

# ===================== 单文件清洗 =====================
def clean_single_file(file_path):
    df = read_file_safely(file_path)
    if df.empty:
        return pd.DataFrame()

    content_col = None
    for col in df.columns:
        if col == "content" or col == "评论":
            content_col = col
            break
    if not content_col:
        return pd.DataFrame()

    df = df.dropna(subset=[content_col])
    df[content_col] = df[content_col].astype(str).str.strip()
    df = df[~df[content_col].apply(is_invalid_comment)]
    df = df.drop_duplicates(subset=[content_col], keep="first")

    clean_df = df[[content_col]].rename(columns={content_col: "content"})
    return clean_df

# ===================== 【精准匹配：绝不混淆】 =====================
def get_category_files(prefix):
    """
    精准匹配：
    content_prefix.csv
    content_prefix1.csv
    content_prefix2.csv
    content_prefix.xlsx
    绝对不会匹配到 prefixShell
    """
    pattern = re.compile(rf'^content_{prefix}(\d+)?\.(csv|xlsx)$', re.I)
    files = []
    for f in os.listdir('.'):
        if pattern.match(f):
            files.append(f)
    return sorted(files)

CATEGORY_PREFIX_MAP = {
    "digital":   ["phone", "earphone", "keyboard"],
    "lifestyle": ["phoneShell", "birthday", "sweater"],
    "snack":     ["pie", "snack"],
    "sports":    ["exercise"]
}

# ===================== 主执行 =====================
def clean_and_group_all():
    for category, prefixes in CATEGORY_PREFIX_MAP.items():
        print(f"\n===== Cleaning: {category} =====")
        all_clean = []

        for prefix in prefixes:
            files = get_category_files(prefix)

            if not files:
                print(f"  ⚠️ No file for: content_{prefix}*")
                continue

            for fname in files:
                cleaned = clean_single_file(fname)
                if not cleaned.empty:
                    all_clean.append(cleaned)
                    print(f"  ✅ {fname} → {len(cleaned)}")

        if all_clean:
            final = pd.concat(all_clean, ignore_index=True)
            final = final.drop_duplicates(subset=["content"])
            out_path = f"cleaned_{category}3.csv"
            final.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"  📦 Saved: {out_path} | Total: {len(final)}")
        else:
            print(f"  ❌ No valid data")

    print("\n🎉 All finished!")
    print("cleaned_digital3.csv")
    print("cleaned_lifestyle3.csv")
    print("cleaned_snack3.csv")
    print("cleaned_sports3.csv")

if __name__ == "__main__":
    clean_and_group_all()