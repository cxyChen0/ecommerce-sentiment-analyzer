import pandas as pd
import os

# ===================== 配置 =====================
CATEGORY_FILES = {
    "digital": "attention_digital_final.csv",
    "lifestyle": "attention_lifestyle_final.csv",
    "snack": "attention_snack_final.csv",
    "sports": "attention_sports_final.csv"
}
DIMENSIONS = ["product", "service", "logistics", "price"]
ALLOWED_ERROR = 0.01

# ===================== 计算 =====================
def calc_weights(csv_path, category_name):
    if not os.path.exists(csv_path):
        print(category_name + "文件不存在")
        return

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df["sum_four"] = df[DIMENSIONS].sum(axis=1)
    df = df[df["product"] != -1].copy()
    df_clean = df[abs(df["sum_four"] - 100) <= ALLOWED_ERROR].copy()

    avg = df_clean[DIMENSIONS].mean()
    weights = avg / 100
    weights = weights.round(4)
    total = weights.sum()

    # ===================== 最终误差补齐 =====================
    # 把误差补在权重最大的维度（学术标准做法）
    diff = round(1.0 - total, 4)
    print("误差: " + str(diff))
    max_dim = weights.idxmax()  # 自动找到最大项（一般是product）
    weights[max_dim] += diff

    print("品类：" + category_name.upper())
    print("最终可用样本：" + str(len(df_clean)))
    print("CBEI权重分布（严格等于100%）：")
    print("   product  产品：" + str(round(weights["product"]*100,2)) + "%")
    print("   service  服务：" + str(round(weights["service"]*100,2)) + "%")
    print("   logistics物流：" + str(round(weights["logistics"]*100,2)) + "%")
    print("   price    价格：" + str(round(weights["price"]*100,2)) + "%")
    print("权重总和：" + str(round(weights.sum()*100,2)) + "%")
    print("======================================================================\n")

# ===================== 执行 =====================
if __name__ == "__main__":
    print("开始计算CBEI权重\n")
    for cat, path in CATEGORY_FILES.items():
        calc_weights(path, cat)
    print("计算完成")