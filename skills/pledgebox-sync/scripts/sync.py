#!/usr/bin/env python3
"""
PledgeBox 订单同步脚本
功能：从 PledgeBox API 拉取未锁定订单，写入 MySQL 数据库（7 张表）
依赖：pip install requests pymysql python-dotenv
"""

import os
import sys
import json
import time
import requests
import pymysql
import pymysql.cursors
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── 加载 .env ────────────────────────────────────────────────
# 从脚本位置向上查找含 main.py 的目录（即 czon_agent 根目录）
def find_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "main.py").exists():
            return parent
    return start  # fallback：找不到就用脚本所在目录

BASE_DIR = find_root(Path(__file__).resolve())
load_dotenv(BASE_DIR / ".env")

API_TOKEN  = os.getenv("PB_API_TOKEN", "")
DB_HOST    = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT    = int(os.getenv("DB_PORT", 3306))
DB_USER    = os.getenv("DB_USER", "root")
DB_PASS    = os.getenv("DB_PASSWORD", "")
DB_NAME    = os.getenv("DB_NAME", "nocobase")

API_BASE   = "https://api.pledgebox.com/api/openapi/orders"
PAGE_DELAY = 0.3   # 翻页间隔（秒），避免触发限流


# ════════════════════════════════════════════════════════════
#  数据库连接
# ════════════════════════════════════════════════════════════
def get_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASS,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


# ════════════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════════════
def to_decimal(val):
    """把 API 返回的金额字符串/数字转成 float，失败返回 None"""
    try:
        return float(val) if val not in (None, "", "null") else None
    except (ValueError, TypeError):
        return None

def to_datetime(val):
    """把字符串日期转成 datetime，失败返回 None"""
    if not val:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None

def to_json(val):
    """把列表/字典序列化为 JSON 字符串，空则返回 None"""
    if val is None:
        return None
    return json.dumps(val, ensure_ascii=False) if val else None


# ════════════════════════════════════════════════════════════
#  API 拉取（自动翻页）
# ════════════════════════════════════════════════════════════
def fetch_orders(project_id: int):
    """拉取指定项目的全部未锁定已完成订单，自动翻页，返回订单列表"""
    all_orders = []
    page = 1
    while True:
        try:
            resp = requests.get(API_BASE, params={
                "api_token":    API_TOKEN,
                "project_id":   project_id,
                "is_completed": 1,
                "order_status": "unlock",
                "page":         page,
            }, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    ⚠ 第{page}页请求失败: {e}")
            break

        data = resp.json()
        if isinstance(data, list):
            page_data = data
        elif isinstance(data, dict):
            page_data = data.get("data") or data.get("orders") or []
        else:
            page_data = []

        if not page_data:
            break

        all_orders.extend(page_data)
        print(f"    第{page}页: {len(page_data)} 条", end="\r")
        page += 1
        time.sleep(PAGE_DELAY)

    return all_orders


# ════════════════════════════════════════════════════════════
#  写入数据库
# ════════════════════════════════════════════════════════════
def insert_order(cur, order: dict, project_id: int) -> int:
    """
    写入订单主表，返回新插入的本地 id；
    若 pb_order_id 已存在（重复），返回 0。
    """
    addr   = order.get("shipping_address") or {}
    reward = order.get("reward") or {}

    sql = """
    INSERT IGNORE INTO pb_orders (
        pb_order_id, pbid, project_id, source,
        ks_id, ks_sequence,
        order_status, survey_status,
        date_confirmed, date_invited, date_completed,
        is_dropped, note,
        courier_name, tracking_code,
        email,
        ship_name, ship_phone,
        ship_address, ship_address2,
        ship_city, ship_state, ship_zip,
        ship_country, ship_country_code,
        paid_amount, shipping_amount,
        tax, value_added_tax, custom_duty, tariff,
        credit_offer, balance,
        reward_id, reward_name, reward_price
    ) VALUES (
        %s,%s,%s,%s,
        %s,%s,
        %s,%s,
        %s,%s,%s,
        %s,%s,
        %s,%s,
        %s,
        %s,%s,
        %s,%s,
        %s,%s,%s,
        %s,%s,
        %s,%s,
        %s,%s,%s,%s,
        %s,%s,
        %s,%s,%s
    )
    """
    cur.execute(sql, (
        order.get("id"),
        order.get("pbid"),
        project_id,
        order.get("source"),
        order.get("ks_id"),
        order.get("sequence"),
        order.get("order_status"),
        order.get("survey_status"),
        to_datetime(order.get("date_confirmed")),
        to_datetime(order.get("date_invited")),
        to_datetime(order.get("date_completed")),
        1 if order.get("is_dropped") else 0,
        order.get("note") or "",
        order.get("courier_name"),
        order.get("tracking_code"),
        order.get("email"),
        addr.get("name"),
        addr.get("phone"),
        addr.get("address"),
        addr.get("address2"),
        addr.get("city"),
        addr.get("state"),
        addr.get("zip"),
        addr.get("country"),
        addr.get("country_code"),
        to_decimal(order.get("paid_amount")),
        to_decimal(order.get("shipping_amount")),
        to_decimal(order.get("tax")),
        to_decimal(order.get("value_added_tax")),
        to_decimal(order.get("custom_duty")),
        to_decimal(order.get("tariff")),
        to_decimal(order.get("credit_offer")),
        to_decimal(order.get("balance")),
        reward.get("id"),
        reward.get("name"),
        to_decimal(reward.get("price")),
    ))
    if cur.rowcount == 0:
        return 0  # 重复，跳过
    return cur.lastrowid


def insert_items(cur, order_id: int, pbid: str, items: list) -> int:
    """写入 Reward 产品明细及其提问"""
    count = 0
    for idx, item in enumerate(items or []):
        cur.execute("""
            INSERT INTO pb_order_items
              (order_id, pbid, item_id, item_name, sku, variant, quantity, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            order_id, pbid,
            item.get("id"),
            item.get("name"),
            item.get("sku"),
            to_json(item.get("variant")),
            item.get("number", 1),
            idx,
        ))
        item_row_id = cur.lastrowid
        count += 1
        for q_idx, q in enumerate(item.get("questions") or []):
            cur.execute("""
                INSERT INTO pb_order_item_questions
                  (order_item_id, order_id, question, answer, sort_order)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                item_row_id, order_id,
                q.get("question") if isinstance(q, dict) else str(q),
                q.get("answer")   if isinstance(q, dict) else None,
                q_idx,
            ))
    return count


def insert_addons(cur, order_id: int, pbid: str, addons: list) -> int:
    """写入加购产品及其提问"""
    count = 0
    for idx, addon in enumerate(addons or []):
        cur.execute("""
            INSERT INTO pb_order_addons
              (order_id, pbid, addon_id, addon_name, sku, price, variant, quantity, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            order_id, pbid,
            addon.get("id"),
            addon.get("name"),
            addon.get("sku"),
            to_decimal(addon.get("price")),
            to_json(addon.get("variant")),
            addon.get("number", 1),
            idx,
        ))
        addon_row_id = cur.lastrowid
        count += 1
        for q_idx, q in enumerate(addon.get("questions") or []):
            cur.execute("""
                INSERT INTO pb_order_addon_questions
                  (order_addon_id, order_id, question, answer, sort_order)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                addon_row_id, order_id,
                q.get("question") if isinstance(q, dict) else str(q),
                q.get("answer")   if isinstance(q, dict) else None,
                q_idx,
            ))
    return count


def insert_gifts(cur, order_id: int, pbid: str, gifts: list) -> int:
    """写入礼物"""
    count = 0
    for idx, gift in enumerate(gifts or []):
        cur.execute("""
            INSERT INTO pb_order_gifts
              (order_id, pbid, gift_id, gift_name, sku, variant, quantity, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            order_id, pbid,
            gift.get("id"),
            gift.get("name"),
            gift.get("sku"),
            to_json(gift.get("variant")),
            gift.get("number", 1),
            idx,
        ))
        count += 1
    return count


def insert_reward_questions(cur, order_id: int, pbid: str, questions: list):
    """写入 Reward 级别提问"""
    for idx, q in enumerate(questions or []):
        cur.execute("""
            INSERT INTO pb_order_reward_questions
              (order_id, pbid, question, answer, sort_order)
            VALUES (%s,%s,%s,%s,%s)
        """, (
            order_id, pbid,
            q.get("question") if isinstance(q, dict) else str(q),
            q.get("answer")   if isinstance(q, dict) else None,
            idx,
        ))


# ════════════════════════════════════════════════════════════
#  主流程
# ════════════════════════════════════════════════════════════
def main():
    start_time = time.time()
    print("=" * 52)
    print("  PledgeBox 订单同步")
    print("=" * 52)

    # 连接数据库
    try:
        conn = get_conn()
    except pymysql.Error as e:
        print(f"❌ 数据库连接失败: {e}")
        sys.exit(1)

    total_projects  = 0
    total_new       = 0
    total_skip      = 0
    total_items     = 0
    total_addons    = 0
    total_gifts     = 0

    try:
        # 读取活跃项目
        with conn.cursor() as cur:
            cur.execute("SELECT project_id, project_name FROM pb_projects WHERE is_active='是'")
            projects = cur.fetchall()

        if not projects:
            print("⚠ pb_projects 中没有 is_active='是' 的项目")
            return

        for proj in projects:
            pid   = proj["project_id"]
            pname = proj.get("project_name") or f"项目{pid}"
            total_projects += 1
            print(f"\n▶ [{pname}] project_id={pid}")

            orders = fetch_orders(pid)
            print(f"  共拉取 {len(orders)} 条订单")

            for order in orders:
                pbid   = order.get("pbid", "")
                reward = order.get("reward") or {}

                try:
                    with conn.cursor() as cur:
                        order_id = insert_order(cur, order, pid)

                        if order_id == 0:
                            total_skip += 1
                            conn.commit()
                            continue

                        # 写子表
                        total_items  += insert_items(
                            cur, order_id, pbid, reward.get("items", []))
                        total_addons += insert_addons(
                            cur, order_id, pbid, order.get("addons", []))
                        total_gifts  += insert_gifts(
                            cur, order_id, pbid, order.get("gifts", []))
                        insert_reward_questions(
                            cur, order_id, pbid, reward.get("questions", []))

                        conn.commit()
                        total_new += 1

                except pymysql.Error as e:
                    conn.rollback()
                    print(f"  ⚠ 订单 {pbid} 写入失败: {e}")
                    continue

    finally:
        conn.close()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 52}")
    print(f"  [同步完成]")
    print(f"  处理项目数：{total_projects}")
    print(f"  新增订单数：{total_new}")
    print(f"  跳过重复数：{total_skip}")
    print(f"  新增产品行：{total_items}")
    print(f"  新增加购行：{total_addons}")
    print(f"  新增礼物行：{total_gifts}")
    print(f"  耗时：{elapsed:.1f} 秒")
    print(f"{'=' * 52}")


if __name__ == "__main__":
    main()
