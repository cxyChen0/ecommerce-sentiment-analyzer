import sqlite3

DB_FILE = "ecommerce_app.db"


def migrate_products_master_table():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    try:
        print("开始执行无损数据迁移手术...")
        # 开启严格事务，中间有任何报错直接回滚，绝不损坏原数据
        conn.execute("BEGIN TRANSACTION;")

        # 1. 将现有的旧表（带 NOT NULL 约束的）改名隐藏
        c.execute("ALTER TABLE products_master RENAME TO old_products_master;")
        print("1. 旧表重命名完成...")

        # 2. 建立完美的全新表（去除了 category 的约束）
        c.execute('''
            CREATE TABLE products_master (
                product_id TEXT PRIMARY KEY,
                category TEXT,               -- 【核心目标】：去除了 NOT NULL 约束
                title TEXT,                  
                shop_name TEXT,              
                price REAL,                  
                province TEXT,               
                city TEXT,                   
                sales INTEGER,               
                product_url TEXT,            
                last_updated TEXT            
            )
        ''')
        print("2. 全新表结构建立完成...")

        # 3. 极其快速的底层数据对拷（几万条数据瞬间转移）
        c.execute("INSERT INTO products_master SELECT * FROM old_products_master;")
        print("3. 数据大搬家完成...")

        # 4. 销毁已经空了的老表
        c.execute("DROP TABLE old_products_master;")
        print("4. 历史包袱清理完成...")

        # 确认无误，提交所有操作！
        conn.commit()
        print("✅ 恭喜！几万条数据无缝迁移成功！表结构已完美解除枷锁！")

    except Exception as e:
        # 如果中途发生任何意外，立刻回退到执行前的状态
        conn.rollback()
        print(f"❌ 迁移失败，已触发安全回滚，您的数据完好无损！报错原因: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_products_master_table()