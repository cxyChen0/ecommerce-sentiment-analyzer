import pandas as pd
import os

# ===================== 配置 =====================
INPUT_FILES = {
    "digital": "attention_digital_cleaned1.csv",
    "lifestyle": "attention_lifestyle_cleaned1.csv",
    "snack": "attention_snack_cleaned1.csv",
    "sports": "attention_sports_cleaned1.csv"
}
DIMENSIONS = ["product", "service", "logistics", "price"]
ALLOWED_ERROR = 0.01  # 允许极小浮点误差，超出则剔除

# ===================== 二次清洗核心 =====================
def final_cleaning(input_name, output_name):
    print("========================================")
    print("正在二次清洗：" + input_name)

    # 1. 读取已初步清洗的数据
    df = pd.read_csv(input_name, encoding="utf-8-sig")
    total_before = len(df)
    print("清洗前总行数：" + str(total_before))

    # 2. 保留有效数据（product != -1）
    df = df[df["product"] != -1].copy()
    after_filter_invalid = len(df)

    # 3. 高精度计算每行维度总和
    df["row_sum"] = df[DIMENSIONS].sum(axis=1)

    # 4. 剔除维度和不符合要求的样本
    mask = abs(df["row_sum"] - 100) <= ALLOWED_ERROR
    df_clean = df[mask].copy()
    total_after = len(df_clean)

    # 5. 移除临时列，保留原始字段结构 + 加回 product_id
    df_final = df_clean[["product_id", "content"] + DIMENSIONS].copy()

    # 6. 输出最终清洗文件
    df_final.to_csv(output_name, index=False, encoding="utf-8-sig")

    # 7. 统计输出
    error_count = after_filter_invalid - total_after

    print("有效总行数：" + str(total_after))
    print("删除错误样本：" + str(error_count) + " 条")
    print("最终文件已保存：" + output_name)
    print("========================================\n")

# ===================== 执行清洗 =====================
if __name__ == "__main__":
    print("开始执行数据二次清洗，剔除AI输出错误样本\n")

    for category, input_file in INPUT_FILES.items():
        output_file = f"attention_{category}_final1.csv"
        final_cleaning(input_file, output_file)

    print("全部二次清洗完成")
    print("最终干净文件：")
    print("attention_digital_final1.csv")
    print("attention_lifestyle_final1.csv")
    print("attention_snack_final1.csv")
    print("attention_sports_final1.csv")