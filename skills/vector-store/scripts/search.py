#!/usr/bin/env python3
"""
语义检索：query embedding → Qdrant 向量检索 → 返回 top-k 结果

用法：
  python search.py --query "<问题>" --collection <库名> [--top-k 5] [--category <标签>]

参数：
  --query       用户问题或检索词
  --collection  目标 collection 名
  --top-k       返回结果数量（默认 5）
  --category    可选：只检索该标签的文档

环境变量：
  QWEN_API_KEY   DashScope API Key（必填）
  QDRANT_URL     Qdrant 服务地址（默认 http://localhost:6333）
  EMBED_MODEL    embedding 模型名（默认 text-embedding-v3）
"""
import argparse
import json
import os
import sys

import requests

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v3")
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def embed_query(text: str, api_key: str) -> list:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE)
    resp = client.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding


def search(collection: str, vector: list, top_k: int, category: str) -> list:
    body = {"vector": vector, "limit": top_k, "with_payload": True}
    if category:
        body["filter"] = {"must": [{"key": "category", "match": {"value": category}}]}
    r = requests.post(
        f"{QDRANT_URL}/collections/{collection}/points/search",
        json=body,
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("result", [])


def main():
    parser = argparse.ArgumentParser(description="Qdrant 语义检索")
    parser.add_argument("--query", required=True, help="检索问题")
    parser.add_argument("--collection", required=True, help="目标 collection 名")
    parser.add_argument("--top-k", type=int, default=5, dest="top_k", help="返回结果数（默认 5）")
    parser.add_argument("--category", default="", help="可选：只检索该标签")
    args = parser.parse_args()

    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print(json.dumps({"ok": False, "error": "缺少 QWEN_API_KEY 环境变量"}, ensure_ascii=False))
        sys.exit(1)

    # Embed query
    try:
        vector = embed_query(args.query, api_key)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Embedding 失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    # Search
    try:
        results = search(args.collection, vector, args.top_k, args.category)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"检索失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    hits = [
        {
            "score": round(item.get("score", 0), 4),
            "content": item.get("payload", {}).get("content", ""),
            "source_file": item.get("payload", {}).get("source_file", ""),
            "chunk_index": item.get("payload", {}).get("chunk_index", 0),
            "category": item.get("payload", {}).get("category", ""),
        }
        for item in results
    ]

    print(json.dumps(
        {"ok": True, "query": args.query, "collection": args.collection, "hits": hits},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
