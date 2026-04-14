import sqlite3
import datetime
import pandas as pd
import re
import threading
import streamlit as st

DB_FILE = "ecommerce_app.db"

# 使用线程局部存储来管理连接，确保每个线程复用自己的连接
_local = threading.local()


def get_connection():
    """获取当前线程专属的复用数据库连接，并启用超强并发特性"""
    if not hasattr(_local, "conn"):
        # 建立连接，并允许跨线程共享（Streamlit 内部有时会跨线程传递对象）
        conn = sqlite3.connect(DB_FILE, check_same_thread=False, isolation_level=None)

        # 启用 WAL 模式 (Write-Ahead Logging)：允许读写并发，极大减少 Database is locked 错误
        conn.execute('PRAGMA journal_mode=WAL;')
        # 启用外键约束，保证数据一致性
        conn.execute('PRAGMA foreign_keys=ON;')
        # 调整同步模式，提升写入速度
        conn.execute('PRAGMA synchronous=NORMAL;')

        _local.conn = conn
    return _local.conn


def init_db():
    """初始化数据库：创建新版 users 表"""
    import datetime
    with get_connection() as conn:
        c = conn.cursor()
        # users 表新增 id 字段作为绝对主键
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,  
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                last_date TEXT,
                spider_count INTEGER DEFAULT 0,
                ai_count INTEGER DEFAULT 0,
                dl_count INTEGER DEFAULT 0
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_login ON users(username, password)')

        # ==========================================
        # 核心修复：直接使用 INSERT OR IGNORE 优雅注入默认管理员
        # 抛弃原来那个错误的 if not c.fetchone() 逻辑
        # ==========================================
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        c.execute('''
            INSERT OR IGNORE INTO users (username, password, role, last_date, spider_count, ai_count, dl_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('admin', 'admin123', '管理员', today_str, 0, 0, 0))

        conn.commit()


def init_stats_db():
    """初始化数据库：创建新版 product_stats 表"""
    with get_connection() as conn:
        c = conn.cursor()
        # 废弃 merchant_user，改用 user_id 外键关联
        c.execute('''
            CREATE TABLE IF NOT EXISTS product_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,     -- 核心改动：只存整数 ID
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                record_date TEXT NOT NULL,
                sales_volume INTEGER DEFAULT 0,
                positive_rate REAL DEFAULT 0.0,
                UNIQUE(user_id, product_id, record_date),
                FOREIGN KEY (user_id) REFERENCES users (id) -- 建立真正的外键级联
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_stats_user_product ON product_stats(user_id, product_id)')
        conn.commit()


def register_user(username, password, role):
    try:
        with get_connection() as conn:
            c = conn.cursor()
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            c.execute('''
                INSERT INTO users (username, password, role, last_date, spider_count, ai_count, dl_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, password, role, today_str, 0, 0, 0))
            conn.commit()
        return True, "注册成功"
    except sqlite3.IntegrityError:
        return False, "用户名已存在！"


def verify_login(username, password):
    """ 登录成功后，必须把底层的 id 查出来返回给前端"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, role FROM users WHERE username=? AND password=?", (username, password))
        result = c.fetchone()
        if result:
            return True, result[0], result[1]  # 返回 (True, user_id, role)
        return False, None, None


def update_password(username, new_password):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (new_password, username))
        if c.rowcount > 0:
            conn.commit()
            return True, "密码修改成功"
        return False, "用户不存在！"


def get_user_data_and_check_reset(user_id):
    """ 所有额度查询，全部改用 user_id 检索，速度极快"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT role, last_date, spider_count, ai_count, dl_count FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        if not row: return None

        role, last_date, spider_count, ai_count, dl_count = row
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        if last_date != today_str:
            c.execute("UPDATE users SET last_date=?, spider_count=0, ai_count=0, dl_count=0 WHERE id=?",
                      (today_str, user_id))
            conn.commit()
            return {'role': role, 'spider_count': 0, 'ai_count': 0, 'dl_count': 0}

        return {'role': role, 'spider_count': spider_count, 'ai_count': ai_count, 'dl_count': dl_count}


def increment_quota(user_id, field_name):
    """更新额度也改用 user_id"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE users SET {field_name} = {field_name} + 1 WHERE id=?", (user_id,))
        conn.commit()


def save_daily_stats(user_id, product_id, product_name, sales_volume, positive_rate):
    """保存数据时，强制使用北京时间，并进行绝对安全的查重覆盖"""
    import datetime
    from datetime import timezone, timedelta

    if not user_id or not product_id:
        return

    # 修复 1：强制获取北京时间 (UTC+8)，消除时区差Bug
    bj_tz = timezone(timedelta(hours=8))
    today_str = datetime.datetime.now(bj_tz).strftime("%Y-%m-%d")

    with get_connection() as conn:
        c = conn.cursor()

        # 修复 2：绝对安全的防重复覆盖逻辑 (不依赖底层 UNIQUE 索引)
        c.execute('''
            SELECT id FROM product_stats 
            WHERE user_id=? AND product_id=? AND record_date=?
        ''', (user_id, product_id, today_str))

        row = c.fetchone()

        if row:
            # 今天已经有记录，执行更新
            c.execute('''
                UPDATE product_stats 
                SET sales_volume=?, positive_rate=? 
                WHERE id=?
            ''', (sales_volume, positive_rate, row[0]))
        else:
            # 今天没有记录，执行插入
            c.execute('''
                INSERT INTO product_stats 
                (user_id, product_id, product_name, record_date, sales_volume, positive_rate)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, product_id, product_name, today_str, sales_volume, positive_rate))

        conn.commit()


def get_merchant_products(user_id):
    """拉取历史记录菜单时，根据 user_id 检索"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT product_id, product_name FROM product_stats WHERE user_id = ? GROUP BY product_id",
                  (user_id,))
        rows = c.fetchall()
    return rows


def get_product_trend(user_id, product_id):
    """画图表时，同时根据 user_id 和 product_id 双重锁定（修复 SQL 注入风险）"""
    import pandas as pd
    with get_connection() as conn:
        # 使用 ? 作为占位符，绝对不要用 f-string 拼接变量
        query = """
            SELECT record_date as 日期, sales_volume as 销量, positive_rate as 综合CBEI指数 
            FROM product_stats 
            WHERE user_id = ? AND product_id = ?
            ORDER BY record_date ASC
        """
        # 利用 params 参数传入变量，底层会自动进行转义和安全处理
        df = pd.read_sql_query(query, conn, params=(user_id, product_id))
    return df

# 管理员专属：全量数据读取与同步操作
def get_all_users_admin():
    """读取所有用户信息（隐藏密码列以防手滑修改导致用户无法登录）"""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT id, username, role, last_date, spider_count, ai_count, dl_count FROM users",
            conn
        )


def sync_users_admin(edited_df, original_df):
    """同步前端编辑器传回的用户 DataFrame 到数据库"""
    import pandas as pd
    import datetime

    edited_df = edited_df.fillna({'spider_count': 0, 'ai_count': 0, 'dl_count': 0})
    with get_connection() as conn:
        c = conn.cursor()
        # 1. 处理新增和更新
        for _, row in edited_df.iterrows():
            if pd.isna(row.get('id')):
                pwd = 'default123'  # 给新增用户一个默认密码
                c.execute('''
                    INSERT INTO users (username, password, role, last_date, spider_count, ai_count, dl_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (row['username'], pwd, row.get('role', '客户'),
                      row.get('last_date', datetime.date.today().strftime("%Y-%m-%d")),
                      row.get('spider_count', 0), row.get('ai_count', 0), row.get('dl_count', 0)))
            else:
                c.execute('''
                    UPDATE users 
                    SET username=?, role=?, last_date=?, spider_count=?, ai_count=?, dl_count=? 
                    WHERE id=?
                ''', (row['username'], row['role'], row['last_date'],
                      row['spider_count'], row['ai_count'], row['dl_count'], row['id']))

        # 2. 精准处理删除（差集法，且绝对保护 admin 账号不被误删）
        if not original_df.empty:
            original_ids = set(original_df['id'].dropna().astype(int))
            edited_ids = set(edited_df['id'].dropna().astype(int))
            deleted_ids = list(original_ids - edited_ids)

            if deleted_ids:
                placeholders = ','.join('?' * len(deleted_ids))
                c.execute(f"DELETE FROM users WHERE id IN ({placeholders}) AND username != 'admin'", deleted_ids)
        conn.commit()


def get_all_product_stats_admin():
    """读取所有历史分析数据"""
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM product_stats", conn)


def sync_product_stats_admin(edited_df, original_df):
    """同步前端编辑器传回的商品历史数据 DataFrame 到数据库"""
    import pandas as pd

    edited_df = edited_df.fillna({'sales_volume': 0, 'positive_rate': 0.0})
    with get_connection() as conn:
        c = conn.cursor()
        # 1. 处理新增和更新
        for _, row in edited_df.iterrows():
            if pd.isna(row.get('id')):
                c.execute('''
                    INSERT INTO product_stats (user_id, product_id, product_name, record_date, sales_volume, positive_rate)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (row['user_id'], row['product_id'], row['product_name'],
                      row['record_date'], row['sales_volume'], row['positive_rate']))
            else:
                c.execute('''
                    UPDATE product_stats 
                    SET user_id=?, product_id=?, product_name=?, record_date=?, sales_volume=?, positive_rate=?
                    WHERE id=?
                ''', (row['user_id'], row['product_id'], row['product_name'],
                      row['record_date'], row['sales_volume'], row['positive_rate'], row['id']))

        # 2. 精准处理删除（差集法）
        if not original_df.empty:
            original_ids = set(original_df['id'].dropna().astype(int))
            edited_ids = set(edited_df['id'].dropna().astype(int))
            deleted_ids = list(original_ids - edited_ids)

            if deleted_ids:
                placeholders = ','.join('?' * len(deleted_ids))
                c.execute(f"DELETE FROM product_stats WHERE id IN ({placeholders})", deleted_ids)
        conn.commit()

# 商家专属：个人历史数据读取与严格隔离同步
def get_merchant_product_stats(user_id):
    """读取当前商家的所有历史分析数据（修复 SQL 注入风险）"""
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM product_stats WHERE user_id=?", conn, params=(user_id,))

def sync_merchant_product_stats(edited_df, original_df, user_id):
    """商家同步自己的数据（修复过滤删除Bug，采用精准差异对比）"""
    edited_df = edited_df.fillna({'sales_volume': 0, 'positive_rate': 0.0})
    with get_connection() as conn:
        c = conn.cursor()
        # 1. 处理新增和更新
        for _, row in edited_df.iterrows():
            if pd.isna(row.get('id')):
                # 新增行
                c.execute('''
                    INSERT INTO product_stats (user_id, product_id, product_name, record_date, sales_volume, positive_rate)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, row['product_id'], row['product_name'],
                      row['record_date'], row['sales_volume'], row['positive_rate']))
            else:
                # 更新行
                c.execute('''
                    UPDATE product_stats 
                    SET product_id=?, product_name=?, record_date=?, sales_volume=?, positive_rate=?
                    WHERE id=? AND user_id=?
                ''', (row['product_id'], row['product_name'],
                      row['record_date'], row['sales_volume'], row['positive_rate'], row['id'], user_id))

        # 2. 精准处理删除（对比原显示表格和编辑后表格的 ID 差异，只删差集）
        if not original_df.empty:
            original_ids = set(original_df['id'].dropna().astype(int))
            edited_ids = set(edited_df['id'].dropna().astype(int))
            deleted_ids = list(original_ids - edited_ids) # 算出哪些 ID 被用户在前端按 Delete 删了

            if deleted_ids:
                placeholders = ','.join('?' * len(deleted_ids))
                c.execute(f"DELETE FROM product_stats WHERE user_id=? AND id IN ({placeholders})", [user_id] + deleted_ids)
        conn.commit()


# =====================================================================
# 新增：全局商品库与评论明细库管理 (支持多品类、多维度 CBEI 分析)
# =====================================================================

def init_ecommerce_db():
    """初始化商品主表和评论明细表"""
    import sqlite3  # 确保顶部有引入，如果没有这里兜底

    with get_connection() as conn:
        c = conn.cursor()

        # 1. 商品主表 (Products Master)
        c.execute('''
            CREATE TABLE IF NOT EXISTS products_master (
                product_id TEXT PRIMARY KEY,
                category TEXT,               -- 品类：digital, lifestyle, snack, sports
                title TEXT,                  -- 商品名称
                shop_name TEXT,              -- 店铺
                price REAL,                  -- 价格
                province TEXT,               -- 省份
                city TEXT,                   -- 城市
                sales INTEGER,               -- 销量
                product_url TEXT,            -- 商品链接
                last_updated TEXT            -- 数据入库/更新时间
            )
        ''')

        # 2. 评论明细表 (Product Comments)
        # 注意：这里保留了你原来的 score_ 系列字段，用于存放【关注度权重】
        c.execute('''
            CREATE TABLE IF NOT EXISTS product_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                content TEXT NOT NULL,
                score_product REAL,          -- 产品维度关注度权重 (你的小模型结果)
                score_service REAL,          -- 服务维度关注度权重
                score_logistics REAL,        -- 物流维度关注度权重
                score_price REAL,            -- 价格维度关注度权重
                batch_date TEXT,             -- 抓取批次日期
                FOREIGN KEY (product_id) REFERENCES products_master (product_id)
            )
        ''')

        c.execute('CREATE INDEX IF NOT EXISTS idx_master_category ON products_master(category)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_comments_pid ON product_comments(product_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_comments_score_pid ON product_comments(score_product, product_id)')

        # =====================================================================
        # 核心扩展：Lambda 架构服务层字段 (满意度精确打分)
        # 采用无损静默升级法：如果列已存在直接跳过，保护老数据
        # =====================================================================
        new_columns = [
            "senti_product REAL",  # 产品维度 真实满意度得分
            "senti_service REAL",  # 服务维度 真实满意度得分
            "senti_logistics REAL",  # 物流维度 真实满意度得分
            "senti_price REAL",  # 价格维度 真实满意度得分
            "comment_date TEXT", # 新增：存放评论真实的发表日期
        ]

        for col_def in new_columns:
            try:
                c.execute(f"ALTER TABLE product_comments ADD COLUMN {col_def};")
            except sqlite3.OperationalError:
                # 捕获 OperationalError (例如：duplicate column name)
                # 意味着数据库已经升级过了，直接放行
                pass

        conn.commit()


# ===================== 批量数据导入函数 (供数据清洗脚本调用) =====================

# ----------------- 新增：智能销量解析器 -----------------
def parse_sales_volume(sales_str):
    """将淘宝/天猫的 '1万+人付款', '500+人收货', '1.5万+' 转换为纯整数"""
    if pd.isna(sales_str) or not sales_str:
        return 0

    s = str(sales_str).strip()

    # 用正则提取数字部分（支持提取 1.5 这种小数）
    match = re.search(r'(\d+(\.\d+)?)', s)
    if not match:
        return 0

    num = float(match.group(1))

    # 如果字符串里带有'万'字，数字乘以 10000
    if '万' in s:
        num *= 10000

    return int(num)


# --------------------------------------------------------
def import_products_from_dataframe(df, category):
    """
    将 data_* 清洗后的 DataFrame 批量导入商品主表
    df 需包含: 商品ID, 标题, 店铺, 价格, 省份, 城市, 销量, 商品链接
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    # 统一重命名列以匹配数据库字段
    col_mapping = {
        "商品ID": "product_id", "标题": "title", "店铺": "shop_name",
        "价格": "price", "省份": "province", "城市": "city",
        "销量": "sales", "商品链接": "product_url"
    }
    df_mapped = df.rename(columns=col_mapping)

    records = []
    for _, row in df_mapped.iterrows():
        # 【关键修复】：调用 parse_sales_volume 解析销量字符串
        clean_sales = parse_sales_volume(row.get('sales', 0))

        records.append((
            str(row.get('product_id', '')), category, str(row.get('title', '')),
            str(row.get('shop_name', '')), float(row.get('price', 0.0) if pd.notna(row.get('price')) else 0.0),
            str(row.get('province', '')), str(row.get('city', '')),
            clean_sales,  # 传入清洗好的纯数字销量
            str(row.get('product_url', '')), today_str
        ))

    with get_connection() as conn:
        c = conn.cursor()
        c.executemany('''
            INSERT OR REPLACE INTO products_master 
            (product_id, category, title, shop_name, price, province, city, sales, product_url, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', records)
        conn.commit()
    print(f"成功导入/更新 {len(records)} 条 [{category}] 商品元数据")


def import_attention_comments_from_dataframe(df):
    """
    将 attention_*_final.csv 的 DataFrame 批量导入评论库
    df 包含: product_id, content, product, service, logistics, price
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    records = []

    # 去重：防止同一条评论被重复导入
    df = df.drop_duplicates(subset=['product_id', 'content'])

    for _, row in df.iterrows():
        records.append((
            str(row['product_id']),
            str(row['content']),
            float(row.get('product', -1)),
            float(row.get('service', -1)),
            float(row.get('logistics', -1)),
            float(row.get('price', -1)),
            today_str
        ))

    with get_connection() as conn:
        c = conn.cursor()
        # 由于评论没有绝对唯一ID，为了防止脚本重复运行导致数据翻倍
        # 这里先尝试删除当天该商品的评论，再重新插入（可选策略）
        # c.execute("DELETE FROM product_comments WHERE batch_date=?", (today_str,))

        c.executemany('''
            INSERT INTO product_comments 
            (product_id, content, score_product, score_service, score_logistics, score_price, batch_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', records)
        conn.commit()
    print(f"成功导入 {len(records)} 条 AI Attention 评论数据")


# ===================== 数据分析提取函数 (供 Streamlit 前端画图调用) =====================

def get_category_average_scores(category):
    """获取某个品类下，所有商品在四个维度上的平均分 (用于雷达图/柱状图)"""
    with get_connection() as conn:
        query = """
            SELECT 
                AVG(c.score_product) as avg_product,
                AVG(c.score_service) as avg_service,
                AVG(c.score_logistics) as avg_logistics,
                AVG(c.score_price) as avg_price
            FROM product_comments c
            JOIN products_master p ON c.product_id = p.product_id
            WHERE p.category = ? AND c.score_product != -1
        """
        df = pd.read_sql_query(query, conn, params=(category,))
        return df.iloc[0].to_dict() if not df.empty else None


def get_product_comments_with_scores(product_id):
    """获取某个具体商品的所有评论及其得分 (用于单品分析和前端 RAG 聊天上下文)"""
    with get_connection() as conn:
        query = """
            SELECT content, score_product, score_service, score_logistics, score_price, batch_date
            FROM product_comments
            WHERE product_id = ?
        """
        return pd.read_sql_query(query, conn, params=(product_id,))


def clear_ecommerce_data():
    """安全清空商品库和评论库，绝对不影响 users 和 product_stats 表"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM product_comments")
        c.execute("DELETE FROM products_master")
        conn.commit()
    print("旧的商品和评论数据已安全清空，用户账号与历史分析记录完好无损！")


# =====================================================================
# 新增：大屏可视化接口与商品/评论库管理员 CRUD 接口
# =====================================================================

def get_cbei_dashboard_data():
    """获取所有品类的四个维度平均关注度（包含全局通用标准，并严格应用误差补齐算法）"""
    with get_connection() as conn:
        # 1. 获取各个细分品类的平均分
        query_cat = """
            SELECT 
                p.category, 
                AVG(c.score_product) as 产品关注度,
                AVG(c.score_service) as 服务关注度,
                AVG(c.score_logistics) as 物流关注度,
                AVG(c.score_price) as 价格关注度
            FROM product_comments c
            JOIN products_master p ON c.product_id = p.product_id
            WHERE c.score_product != -1
            GROUP BY p.category
        """
        df_cat = pd.read_sql_query(query_cat, conn)

        # 2. 获取全局通用标准平均分 (等价于按样本量加权平均)
        query_gen = """
            SELECT 
                'general' as category, 
                AVG(score_product) as 产品关注度,
                AVG(score_service) as 服务关注度,
                AVG(score_logistics) as 物流关注度,
                AVG(score_price) as 价格关注度
            FROM product_comments
            WHERE score_product != -1
        """
        df_gen = pd.read_sql_query(query_gen, conn)

        df = pd.concat([df_cat, df_gen], ignore_index=True)

        # 剔除空库查询时产生的 NULL/NaN 幽灵行
        df = df.dropna(subset=['产品关注度', '服务关注度', '物流关注度', '价格关注度'])
        if df.empty:
            return df

        # 3. 【核心】：执行 CBEI 微小误差补齐法 (差值补齐)
        score_cols = ['产品关注度', '服务关注度', '物流关注度', '价格关注度']
        for idx, row in df.iterrows():
            scores = {col: row[col] for col in score_cols}
            current_sum = sum(scores.values())
            diff = 100.0 - current_sum
            max_dim = max(scores, key=scores.get)
            df.at[idx, max_dim] += diff

        return df


def get_all_ecommerce_products():
    """获取所有商品主表数据"""
    with get_connection() as conn:
        import pandas as pd
        return pd.read_sql_query("SELECT * FROM products_master", conn)


def sync_ecommerce_products(edited_df, original_df):
    """同步商品主表的修改"""
    import pandas as pd
    edited_df = edited_df.fillna({'price': 0.0, 'sales': 0})
    with get_connection() as conn:
        c = conn.cursor()
        # 1. 插入或更新
        for _, row in edited_df.iterrows():
            c.execute('''
                INSERT OR REPLACE INTO products_master 
                (product_id, category, title, shop_name, price, province, city, sales, product_url, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
            str(row['product_id']), str(row['category']), str(row.get('title', '')), str(row.get('shop_name', '')),
            float(row['price']), str(row.get('province', '')), str(row.get('city', '')),
            int(row['sales']), str(row.get('product_url', '')), str(row.get('last_updated', ''))))

        # 2. 删除
        if not original_df.empty:
            orig_ids = set(original_df['product_id'].dropna().astype(str))
            edit_ids = set(edited_df['product_id'].dropna().astype(str))
            deleted_ids = list(orig_ids - edit_ids)
            if deleted_ids:
                placeholders = ','.join('?' * len(deleted_ids))
                c.execute(f"DELETE FROM products_master WHERE product_id IN ({placeholders})", deleted_ids)
                # 级联删除相关的评论，防止出现孤儿
                c.execute(f"DELETE FROM product_comments WHERE product_id IN ({placeholders})", deleted_ids)
        conn.commit()


def get_all_ecommerce_comments():
    """获取所有评论库数据"""
    with get_connection() as conn:
        import pandas as pd
        return pd.read_sql_query("SELECT * FROM product_comments", conn)


def sync_ecommerce_comments(edited_df, original_df):
    """同步评论库的修改"""
    import pandas as pd
    edited_df = edited_df.fillna(
        {'score_product': -1.0, 'score_service': -1.0, 'score_logistics': -1.0, 'score_price': -1.0})
    with get_connection() as conn:
        c = conn.cursor()
        # 1. 插入或更新
        for _, row in edited_df.iterrows():
            if pd.isna(row.get('id')):  # 新增的行没有 id
                c.execute('''
                    INSERT INTO product_comments 
                    (product_id, content, score_product, score_service, score_logistics, score_price, batch_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                str(row['product_id']), str(row['content']), float(row['score_product']), float(row['score_service']),
                float(row['score_logistics']), float(row['score_price']), str(row.get('batch_date', ''))))
            else:  # 更新旧行
                c.execute('''
                    UPDATE product_comments 
                    SET product_id=?, content=?, score_product=?, score_service=?, score_logistics=?, score_price=?, batch_date=?
                    WHERE id=?
                ''', (
                str(row['product_id']), str(row['content']), float(row['score_product']), float(row['score_service']),
                float(row['score_logistics']), float(row['score_price']), str(row.get('batch_date', '')),
                int(row['id'])))

        # 2. 删除
        if not original_df.empty:
            orig_ids = set(original_df['id'].dropna().astype(int))
            edit_ids = set(edited_df['id'].dropna().astype(int))
            deleted_ids = list(orig_ids - edit_ids)
            if deleted_ids:
                placeholders = ','.join('?' * len(deleted_ids))
                c.execute(f"DELETE FROM product_comments WHERE id IN ({placeholders})", deleted_ids)
        conn.commit()


def batch_save_scraped_comments(product_id, comments_data_list):
    """
    修改后的函数：支持保存评论内容 + 真实日期
    comments_data_list: 结构为 [{'content': '...', 'date': '2026-01-01'}, ...]
    """
    import datetime
    if not comments_data_list:
        return 0

    conn = get_connection()
    c = conn.cursor()
    saved_count = 0
    batch_today = datetime.date.today().strftime("%Y-%m-%d")

    try:
        for item in comments_data_list:
            # 这里的 item 是爬虫传过来的字典
            content = str(item.get('content', '')).strip()
            # 拿到爬虫辛苦抓到的日期！
            real_date = str(item.get('date', '')).strip()

            if len(content) < 2: continue

            # 查重逻辑：同商品同内容不再重复插入
            c.execute("SELECT id FROM product_comments WHERE product_id=? AND content=?", (product_id, content))

            if not c.fetchone():
                c.execute("""
                    INSERT INTO product_comments 
                    (product_id, content, comment_date, batch_date) 
                    VALUES (?, ?, ?, ?)
                """, (product_id, content, real_date, batch_today))
                saved_count += 1
        conn.commit()
    except Exception as e:
        conn.rollback()  # 出错回滚
        raise Exception(f"数据库写入失败: {e}")

    return saved_count


def insert_ecommerce_product(product_id, title, category, price, province, city, sales, product_url):
    import datetime
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    with get_connection() as conn:
        c = conn.cursor()
        try:
            c.execute('''
                INSERT OR IGNORE INTO products_master 
                (product_id, category, title, shop_name, price, province, city, sales, product_url, last_updated)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
            ''', (product_id, category, title, price, province, city, sales, product_url, today_str))

            c.execute('''
                UPDATE products_master 
                SET title=COALESCE(?, title), sales=COALESCE(?, sales), last_updated=?
                WHERE product_id=?
            ''', (title, sales, today_str, product_id))
            conn.commit()
        except Exception as e:
            raise Exception(f"崩溃了！商品主表建档失败，原因：{e}")


def get_all_comments_by_product(product_id):
    """
    极速查询：直接从底层数据库拉取该商品的所有历史+最新评论。
    将数据库底层的 comment_date 映射为前端统一使用的 date 字段。
    """
    if not product_id:
        return []

    with get_connection() as conn:
        c = conn.cursor()

        try:
            # 1. SQL 语句里，用你数据库真实的字段名：comment_date
            c.execute("SELECT content, comment_date FROM product_comments WHERE product_id=?", (product_id,))
            rows = c.fetchall()

            # 2. 组装成字典时，把查出来的 row[1] 赋值给统一的键名 "date"
            return [{"content": row[0], "date": row[1] if row[1] else "未知"} for row in rows]

        except Exception:
            # 兜底：万一遇到没有这个字段的老表
            c.execute("SELECT content FROM product_comments WHERE product_id=?", (product_id,))
            rows = c.fetchall()
            return [{"content": row[0], "date": "未知"} for row in rows]