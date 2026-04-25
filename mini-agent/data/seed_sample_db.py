#!/usr/bin/env python3
"""
初始化示例 SQLite 数据库：创建 employees 表并插入 10 条示例数据
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "sample.db"

EMPLOYEES = [
    ("张伟", "工程部", 18000, "2020-03-15"),
    ("李娜", "产品部", 22000, "2019-07-01"),
    ("王芳", "市场部", 15000, "2021-09-10"),
    ("刘洋", "工程部", 25000, "2018-01-20"),
    ("陈静", "财务部", 16000, "2022-04-05"),
    ("赵磊", "人力资源部", 14000, "2023-02-28"),
    ("孙悦", "工程部", 30000, "2017-06-18"),
    ("周鑫", "产品部", 20000, "2020-11-11"),
    ("吴超", "市场部", 17500, "2021-03-22"),
    ("郑梅", "财务部", 19000, "2019-12-01"),
]


def seed():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            department TEXT NOT NULL,
            salary    REAL NOT NULL,
            hire_date TEXT NOT NULL
        )
    """)

    cur.execute("SELECT COUNT(*) FROM employees")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO employees (name, department, salary, hire_date) VALUES (?, ?, ?, ?)",
            EMPLOYEES,
        )
        print(f"已插入 {len(EMPLOYEES)} 条员工数据")
    else:
        print("数据库已存在，跳过初始化")

    conn.commit()
    conn.close()
    print(f"数据库已就绪：{DB_PATH}")


if __name__ == "__main__":
    seed()
