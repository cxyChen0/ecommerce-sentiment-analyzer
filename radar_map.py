import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

# 1. 基础设置
plt.rcParams['font.sans-serif'] = ['SimHei']  # Windows用黑体，Mac用户请改为 'Arial Unicode MS'
plt.rcParams['axes.unicode_minus'] = False

# 2. 准备数据
labels = np.array(['产品 (Product)', '服务 (Service)', '物流 (Logistics)', '价格 (Price)'])
categories = ['DIGITAL', 'LIFESTYLE', 'SNACK', 'SPORTS', '通用标准']

# 按照 [产品, 服务, 物流, 价格] 的顺序排列数据
data = [
    [75.30, 3.39, 7.07, 14.24],  # DIGITAL
    [76.76, 5.23, 7.14, 10.87],  # LIFESTYLE
    [75.96, 1.90, 9.07, 13.07],  # SNACK
    [78.81, 3.44, 5.80, 11.95],  # SPORTS
    [76.09, 3.49, 7.59, 12.83]   # 通用标准
]

# 3. 计算雷达图的角度并闭合多边形
angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
# 为了让雷达图线条闭合，需要把第一个角度和数据追加到最后
angles += angles[:1]
data_closed = [d + [d[0]] for d in data]

# 4. 绘制雷达图
fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

# 调整雷达图的起始角度（让“产品”在正上方）
ax.set_theta_offset(np.pi / 2)
ax.set_theta_direction(-1)

# 绘制每一条线
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'] # 设定颜色
markers = ['o', 's', '^', 'D', '*'] # 设定标记点形状

for i in range(len(categories)):
    ax.plot(angles, data_closed[i], color=colors[i], linewidth=2, label=categories[i], marker=markers[i])
    # 如果想填充颜色，可以取消下面这行的注释，但5个品类重叠可能会显得杂乱
    # ax.fill(angles, data_closed[i], color=colors[i], alpha=0.1)

# 5. 图表修饰
ax.set_thetagrids(np.degrees(angles[:-1]), labels, fontsize=12)
ax.set_ylim(0, 85) # 设置网格最大值为 85%，包容产品的最高值
plt.title('各品类 CBEI 权重特征雷达图', fontsize=16, fontweight='bold', pad=30)
plt.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10)

plt.tight_layout()
plt.show()