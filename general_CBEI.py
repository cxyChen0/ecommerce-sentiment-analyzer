import pandas as pd

# ===================== 1. 数据准备（与论文手动计算完全一致） =====================
# 各品类的维度权重（百分比形式）和对应有效样本量
category_data = {
    "digital": {
        "product": 75.3,  # 论文中digital产品权重（修正后补齐值）
        "service": 3.39,
        "logistics": 7.07,
        "price": 14.24,
        "sample_size": 4999  # 该品类最终可用样本量
    },
    "lifestyle": {
        "product": 76.76,
        "service": 5.23,
        "logistics": 7.14,
        "price": 10.87,
        "sample_size": 3763
    },
    "snack": {
        "product": 75.96,
        "service": 1.9,
        "logistics": 9.07,
        "price": 13.07,
        "sample_size": 3758
    },
    "sports": {
        "product": 78.81,
        "service": 3.44,
        "logistics": 5.8,
        "price": 11.95,
        "sample_size": 702
    }
}

DIMENSIONS = ["product", "service", "logistics", "price"]


# ===================== 2. 核心计算（加权平均，中间保留4位小数，与论文完全一致） =====================
def calculate_general_cbei():
    # 计算总可用样本量（论文值：13222）
    total_sample = sum([data["sample_size"] for data in category_data.values()])
    print("总可用样本量：" + str(total_sample))
    print("=" * 80)

    general_weights = {}
    # 遍历每个维度，按加权平均公式计算通用权重
    for dim in DIMENSIONS:
        # 分子：各品类该维度权重 × 该品类样本量 之和（保留4位小数）
        numerator = sum([category_data[cat][dim] * category_data[cat]["sample_size"] for cat in category_data.keys()])
        numerator = round(numerator, 4)
        # 分母：总样本量
        denominator = total_sample
        # 通用权重计算（中间保留4位小数，与论文手动计算一致）
        general_weight = round(numerator / denominator, 4)
        general_weights[dim] = general_weight

        # 输出中间计算过程，方便核对与论文一致性
        print(f"{dim.upper()} 维度计算：")
        print(f"  分子（各品类权重×样本量之和）：{numerator}")
        print(f"  分母（总样本量）：{denominator}")
        print(f"  中间保留4位小数权重：{general_weight}%")
        print("-" * 60)

    # 3. 最终结果（四舍五入保留2位小数，与论文结论一致）
    print("=" * 80)
    print("通用CBEI权重（最终结果，保留2位小数）：")
    final_weights = {}
    total_final = 0.0
    for dim in DIMENSIONS:
        final_weight = round(general_weights[dim], 2)
        final_weights[dim] = final_weight
        total_final += final_weight
        print(f"  {dim}（{dim.upper()}）：{final_weight}%")

    print(f"  权重总和：{round(total_final, 2)}%")
    print("=" * 80)

    # 4. 输出通用权重表格（贴合论文结论）
    print("\n通用CBEI权重表（行业标准，用于未知品类）：")
    print("维度\t英文标识\t通用权重 (行业标准)")
    print("-" * 50)
    print(f"产品\tproduct\t\t{final_weights['product']}%")
    print(f"价格\tprice\t\t{final_weights['price']}%")
    print(f"物流\tlogistics\t{final_weights['logistics']}%")
    print(f"服务\tservice\t\t{final_weights['service']}%")
    print(f"总和\t-\t\t{round(total_final, 2)}%")


# 执行计算，查看与论文手动计算的一致性
if __name__ == "__main__":
    calculate_general_cbei()