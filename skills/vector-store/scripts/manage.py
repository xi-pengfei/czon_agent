#!/usr/bin/env python3
"""
向量库管理：list / create / delete / info / delete-source

用法：
  python manage.py list
  python manage.py create --collection <name>
  python manage.py delete --collection <name>
  python manage.py info   --collection <name>
  python manage.py delete-source --collection <name> --source <文件名>

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
    dim = args.dim
    body = {"vectors": {"size": dim, "distance": "Cosine"}}
    r = requests.put(f"{QDRANT_URL}/collections/{args.collection}", json=body, timeout=10)
    r.raise_for_status()
    print(json.dumps({"ok": True, "created": args.collection, "dim": dim}, ensure_ascii=False))


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
    count_r = requests.post(f"{QDRANT_URL}/collections/{args.collection}/points/count", json={}, timeout=10)
    count = count_r.json().get("result", {}).get("count", "?") if count_r.ok else "?"
    print(json.dumps({"ok": True, "collection": args.collection, "points_count": count, "info": info}, ensure_ascii=False))


def cmd_delete_source(args):
    """
    删除某个 collection 中指定源文件的所有向量片段。
    优先用 --source-hash（MD5，可靠）；无 hash 时退回到 --source 文件名匹配（可能撞名）。
    删除后验证 count 是否归零。
    """
    if args.source_hash:
        # 可靠路径：按 MD5 删除，不受文件名影响
        match_field, match_value = "source_hash", args.source_hash
        label = f"hash={args.source_hash}"
    elif args.source:
        # 兜底路径：按文件名删除，存在撞名风险
        match_field, match_value = "source_file", args.source
        label = f"file={args.source}"
        print(f"[WARNING] 按文件名删除存在撞名风险，建议使用 --source-hash", file=sys.stderr)
    else:
        print(json.dumps({"ok": False, "error": "需要 --source 或 --source-hash 参数"}, ensure_ascii=False))
        sys.exit(1)

    flt = {"must": [{"key": match_field, "match": {"value": match_value}}]}

    # 删除前 count
    before_r = requests.post(
        f"{QDRANT_URL}/collections/{args.collection}/points/count",
        json={"filter": flt}, timeout=10,
    )
    count_before = before_r.json().get("result", {}).get("count", "?") if before_r.ok else "?"

    # 删除
    r = requests.post(
        f"{QDRANT_URL}/collections/{args.collection}/points/delete",
        json={"filter": flt}, timeout=15,
    )
    r.raise_for_status()

    # 删除后验证
    after_r = requests.post(
        f"{QDRANT_URL}/collections/{args.collection}/points/count",
        json={"filter": flt}, timeout=10,
    )
    count_after = after_r.json().get("result", {}).get("count", 0) if after_r.ok else "?"

    verified = count_after == 0
    print(json.dumps(
        {
            "ok": True,
            "collection": args.collection,
            "matched": label,
            "deleted_count": count_before,
            "remaining": count_after,
            "verified_clean": verified,
        },
        ensure_ascii=False,
    ))


def main():
    parser = argparse.ArgumentParser(description="Qdrant collection 管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出所有 collection")

    p_create = sub.add_parser("create", help="创建 collection")
    p_create.add_argument("--collection", required=True, help="库名")
    p_create.add_argument("--dim", type=int, default=DEFAULT_DIM,
                          help=f"向量维度，需与 EMBED_MODEL 一致（默认 {DEFAULT_DIM}，text-embedding-v3）")

    p_delete = sub.add_parser("delete", help="删除整个 collection")
    p_delete.add_argument("--collection", required=True, help="库名")

    p_info = sub.add_parser("info", help="查看 collection 信息")
    p_info.add_argument("--collection", required=True, help="库名")

    p_ds = sub.add_parser("delete-source", help="删除某个源文件对应的所有向量")
    p_ds.add_argument("--collection", required=True, help="库名")
    p_ds.add_argument("--source", default="", help="源文件名（如 民法典.txt）")
    p_ds.add_argument("--source-hash", default="", dest="source_hash",
                      help="文件 MD5（ingest 时输出，推荐使用，比文件名可靠）")

    args = parser.parse_args()
    {
        "list": cmd_list,
        "create": cmd_create,
        "delete": cmd_delete,
        "info": cmd_info,
        "delete-source": cmd_delete_source,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
