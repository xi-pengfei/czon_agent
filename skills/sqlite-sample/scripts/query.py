#!/usr/bin/env python3
"""
SQLite 查询脚本：只允许 SELECT 语句，结果以 JSON 输出
用法：python query.py --sql "SELECT * FROM employees LIMIT 5"
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

# 数据库路径（相对于项目根目录执行）
DB_PATH = Path("data/sample.db")
DEFAULT_LIMIT = 100


def main():
    parser = argparse.ArgumentParser(description="查询示例 SQLite 数据库")
    parser.add_argument("--sql", required=True, help="SELECT 语句")
    args = parser.parse_args()

    sql = args.sql.strip()

    # 安全验证：只允许 SELECT
    if not sql.lower().startswith("select"):
        print(json.dumps({"error": "只允许 SELECT 查询，拒绝执行其他操作"}, ensure_ascii=False))
        sys.exit(1)

    if not DB_PATH.exists():
        print(json.dumps({"error": f"数据库文件不存在：{DB_PATH}，请先运行 python main.py setup"}, ensure_ascii=False))
        sys.exit(1)

    # 自动添加 LIMIT（如果没有）
    if "limit" not in sql.lower():
        sql = f"{sql} LIMIT {DEFAULT_LIMIT}"

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        print(json.dumps({"count": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
    except sqlite3.Error as e:
        print(json.dumps({"error": f"SQL 执行失败：{e}"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
