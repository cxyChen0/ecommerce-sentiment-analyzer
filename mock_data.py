import sqlite3
import random
import datetime

# ================= 配置区 =================
DB_FILE = "ecommerce_app.db"
TARGET_USER_ID = 1
TARGET_PRODUCT_ID = "679038219878"
TARGET_PRODUCT_NAME = "2024夏季新款透气男鞋"
DAYS_TO_SIMULATE = 30
# ==========================================

def get_taobao_scraped_volume(real_volume):
    """模拟淘宝前端的模糊下取整展示逻辑"""
    if real_volume < 100:
        return real_volume
    elif real_volume < 1000:
        return (real_volume // 100) * 100       # 几百+
    elif real_volume < 10000:
        return (real_volume // 1000) * 1000     # 几千+
    else:
        return (real_volume // 10000) * 10000   # 几万+

def generate_mock_data():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT username FROM users WHERE id=?", (TARGET_USER_ID,))
    user_record = c.fetchone()
    if not user_record:
        print(f"❌ 错误：找不到 id={TARGET_USER_ID} 的用户！")
        return
    username = user_record[0]

    c.execute("SELECT product_name FROM product_stats WHERE product_id=? AND user_id=? LIMIT 1",
              (TARGET_PRODUCT_ID, TARGET_USER_ID))
    name_record = c.fetchone()
    real_product_name = name_record[0] if name_record else TARGET_PRODUCT_NAME

    today = datetime.date.today()
    print(f"\n🚀 开始为用户【{username}】的商品【{real_product_name}】注入 30 天的打爆模拟数据...")

    # --- 初始隐藏的真实基数 ---
    # 设定起点为 1200 左右，这样初始爬取显示为 1000+
    hidden_real_sales = random.randint(1100, 1500)
    current_positive_rate = round(random.uniform(80.0, 85.0), 1)

    for i in range(DAYS_TO_SIMULATE, -1, -1):
        record_date = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")

        # --- 📈 真实销量隐藏暴增逻辑 ---
        if i > 20:
            daily_growth = random.randint(50, 100)   # 蓄水期，缓慢增长
        elif 5 < i <= 20:
            daily_growth = random.randint(350, 500)  # 直通车猛推，每日真实销量几百单
        else:
            daily_growth = random.randint(150, 250)  # 稳定在头部，向 9000+ 冲刺并维稳

        hidden_real_sales += daily_growth

        # --- 🤖 将真实销量转化为爬虫能抓到的“平台展示销量” ---
        scraped_sales = get_taobao_scraped_volume(hidden_real_sales)

        # --- ⭐ 文本好评率跌落逻辑 (目标：最终 70% 左右) ---
        if daily_growth > 300:
            rate_change = random.uniform(-2.0, -0.5)
        elif current_positive_rate > 75.0:
            rate_change = random.uniform(-1.0, 0.1)
        else:
            rate_change = random.uniform(-0.5, 0.5)

        current_positive_rate += rate_change
        current_positive_rate = max(65.0, min(current_positive_rate, 88.0))
        current_positive_rate = round(current_positive_rate, 1)

        # 注意：这里存入数据库的是 scraped_sales（下取整后的平台销量），而不是真实的 hidden_real_sales
        c.execute('''
            INSERT OR REPLACE INTO product_stats 
            (user_id, product_id, product_name, record_date, sales_volume, positive_rate)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (TARGET_USER_ID, TARGET_PRODUCT_ID, real_product_name, record_date, scraped_sales, current_positive_rate))

        print(f"✅ 日期: {record_date} | 真实销量(隐藏): {hidden_real_sales:<5} | 抓取落库销量: {scraped_sales:<5} | 有效好评率: {current_positive_rate}%")

    conn.commit()
    conn.close()
    print("\n🎉 模拟数据已更新！去历史数据看板查看，现在呈现的是非常真实的淘宝阶梯状销量，最终停留落在 9000 梯队！")


if __name__ == "__main__":
    generate_mock_data()