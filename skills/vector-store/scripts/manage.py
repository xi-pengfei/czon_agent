#!/usr/bin/env python3
"""
向量库管理：list / create / delete / info collection

用法：
  python manage.py list
  python manage.py create --collection <name>
  python manage.py delete --collection <name>
  python manage.py info   --collection <name>

环境变量：
  QDRANT_URL  Qdrant 服务地址（默认 http://localhost:6333）
"""
import argparse
import json
import os
import sys

import requests

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
# text-embedding-v3 默认维度
DEFAULT_DIM = 1024


def cmd_list(_args):
    r = requests.get(f"{QDRANT_URL}/collections", timeout=10)
    r.raise_for_status()
    cols = [c["name"] for c in r.json().get("result", {}).get("collections", [])]
    print(json.dumps({"ok": True, "collections": cols}, ensure_ascii=False))


def cmd_create(args):
    body = {"vectors": {"size": DEFAULT_DIM, "distance": "Cosine"}}
    r = requests.put(f"{QDRANT_URL}/collections/{args.collection}", json=body, timeout=10)
    r.raise_for_status()
    print(json.dumps({"ok": True, "created": args.collection}, ensure_ascii=False))


def cmd_delete(args):
    r = requests.delete(f"{QDRANT_URL}/collections/{args.collection}", timeout=10)
    r.raise_for_status()
    print(json.dumps({"ok": True, "deleted": args.collection}, ensure_ascii=False))


def cmd_info(args):
    r = requests.get(f"{QDRANT_URL}/collections/{args.collection}", timeout=10)
    if r.status_code == 404:
        print(json.dumps({"ok": False, "error": f"collection '{args.collection}' 不存在"}, ensure_ascii=False))
        sys.exit(1)
    r.raise_for_status()
    info = r.json().get("result", {})
    count_r = requests.get(f"{QDRANT_URL}/collections/{args.collection}/points/count", timeout=10)
    count = count_r.json().get("result", {}).get("count", "?") if count_r.ok else "?"
    print(json.dumps({"ok": True, "collection": args.collection, "points_count": count, "info": info}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Qdrant collection 管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出所有 collection")

    p_create = sub.add_parser("create", help="创建 collection")
    p_create.add_argument("--collection", required=True, help="库名")

    p_delete = sub.add_parser("delete", help="删除 collection")
    p_delete.add_argument("--collection", required=True, help="库名")

    p_info = sub.add_parser("info", help="查看 collection 信息")
    p_info.add_argument("--collection", required=True, help="库名")

    args = parser.parse_args()
    {"list": cmd_list, "create": cmd_create, "delete": cmd_delete, "info": cmd_info}[args.cmd](args)


if __name__ == "__main__":
    main()
