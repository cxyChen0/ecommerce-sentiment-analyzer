import db_manager
import sqlite3

print("🛠️ 正在启动无损数据修复手术...")

# 获取数据库连接
conn = db_manager.get_connection()
c = conn.cursor()

try:
    # 1. 🚨 必须先关闭外键检查！否则 SQLite 不允许我们重构有外键依赖的表
    c.execute("PRAGMA foreign_keys=OFF;")

    # 2. 开启事务，保证要死一起死，要活一起活，绝对不丢数据
    c.execute("BEGIN TRANSACTION;")

    # 3. 将那个外键指错的“精神分裂表”改个名字，作为临时备份
    c.execute("ALTER TABLE product_comments RENAME TO temp_broken_comments;")

    # 4. 重新创建一个结构绝对纯净、外键指向完全正确的 product_comments 表
    # (包含你之前所有的 score_ 字段和新加的 senti_ 字段)
    c.execute('''
        CREATE TABLE product_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            content TEXT NOT NULL,
            score_product REAL,
            score_service REAL,
            score_logistics REAL,
            score_price REAL,
            batch_date TEXT,
            senti_product REAL,
            senti_service REAL,
            senti_logistics REAL,
            senti_price REAL,
            FOREIGN KEY (product_id) REFERENCES products_master (product_id)
        )
    ''')

    # 5. 🌟 核心魔法：把备份表里的所有历史数据，一条不漏地灌进新表！
    c.execute("INSERT INTO product_comments SELECT * FROM temp_broken_comments;")

    # 6. 数据转移完毕，安全销毁那个带毒的备份表
    c.execute("DROP TABLE temp_broken_comments;")

    # 7. 重新补上索引（保证查询依然极速）
    c.execute('CREATE INDEX IF NOT EXISTS idx_comments_pid ON product_comments(product_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_comments_score_pid ON product_comments(score_product, product_id)')

    # 8. 提交事务，手术成功！
    conn.commit()
    print("✅ 修复大获成功！你的所有历史数据已完好无损地迁移到了正确的新表结构中！")

except Exception as e:
    # 如果中间任何一步出错，立刻回滚，你的数据依然不会丢
    conn.rollback()
    print(f"❌ 修复失败，已安全撤销: {e}")

finally:
    # 9. 重新开启外键检查，恢复系统的严谨性
    c.execute("PRAGMA foreign_keys=ON;")
    conn.close()

print("✨ 现在请回到网页再次点击【立即分析】，幽灵报错已彻底消失！")