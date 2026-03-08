import sqlite3
import datetime
import pandas as pd

DB_FILE = "ecommerce_app.db"
def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def init_db():
    """初始化数据库：创建新版 users 表"""
    with get_connection() as conn:
        c = conn.cursor()
        # users 表新增 id 字段作为绝对主键
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,  -- username 现在只作为唯一登录名
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                last_date TEXT,
                spider_count INTEGER DEFAULT 0,
                ai_count INTEGER DEFAULT 0,
                dl_count INTEGER DEFAULT 0
            )
        ''')
        c.execute("SELECT id FROM users WHERE username='admin'")
        if not c.fetchone():
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            c.execute('''
                INSERT INTO users (username, password, role, last_date, spider_count, ai_count, dl_count)
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
    """保存数据时，写入 user_id"""
    if not user_id or not product_id:
        return
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO product_stats 
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
            SELECT record_date as 日期, sales_volume as 销量, positive_rate as 预估好评率 
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