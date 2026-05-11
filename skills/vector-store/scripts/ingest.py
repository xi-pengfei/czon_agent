#!/usr/bin/env python3
"""
文档入库：读文件 → 切片 → Qwen embedding → 写入 Qdrant

用法：
  python ingest.py --file <路径> --collection <库名> [--mode law|default] [--category <标签>]

参数：
  --file        文件路径（支持 .txt .md .docx .pdf）
  --collection  目标 collection 名
  --mode        切片模式：law = 按"第X条"切；default = 按段落切（默认）
  --category    可选标签，写入 payload，检索时可过滤

环境变量：
  QWEN_API_KEY   DashScope API Key（必填）
  QDRANT_URL     Qdrant 服务地址（默认 http://localhost:6333）
  EMBED_MODEL    embedding 模型名（默认 text-embedding-v3，维度 1024）
"""
import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

import requests

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v3")
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BATCH_SIZE = 25  # embedding 单次最多条数
UPSERT_BATCH = 100  # Qdrant 单次写入条数


# ── 文件读取 ──────────────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".txt", ".md"):
        return p.read_text(encoding="utf-8")
    if suffix == ".docx":
        from docx import Document
        doc = Document(str(p))
        return "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())
    if suffix == ".pdf":
        import pdfplumber
        with pdfplumber.open(str(p)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages)
    # 其他格式兜底按文本读
    return p.read_text(encoding="utf-8")


# ── 切片 ──────────────────────────────────────────────────────────────────────

def chunk_default(text: str) -> list:
    """按空行段落切片，过滤空块"""
    return [c.strip() for c in text.split("\n\n") if c.strip()]


def chunk_law(text: str) -> list:
    """按"第X条"切片，适合法律法规文本"""
    parts = re.split(r"(?=第[零一二三四五六七八九十百千\d]+条)", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, mode: str) -> list:
    chunks = chunk_law(text) if mode == "law" else chunk_default(text)
    # 兜底：如果切完是空的就整段返回
    return chunks if chunks else [text.strip()]


# ── Embedding ────────────────────────────────────────────────────────────────

def embed_batch(texts: list, api_key: str) -> list:
    """调用 Qwen text-embedding-v3，返回向量列表"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE)
    all_vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        all_vectors.extend([d.embedding for d in resp.data])
    return all_vectors


# ── Qdrant ───────────────────────────────────────────────────────────────────

def ensure_collection(name: str, dim: int):
    """如果 collection 不存在则自动创建"""
    r = requests.get(f"{QDRANT_URL}/collections/{name}", timeout=10)
    if r.status_code == 404:
        body = {"vectors": {"size": dim, "distance": "Cosine"}}
        resp = requests.put(f"{QDRANT_URL}/collections/{name}", json=body, timeout=10)
        resp.raise_for_status()


def upsert_points(collection: str, points: list):
    """分批写入 Qdrant"""
    for i in range(0, len(points), UPSERT_BATCH):
        batch = points[i : i + UPSERT_BATCH]
        r = requests.put(
            f"{QDRANT_URL}/collections/{collection}/points",
            json={"points": batch},
            timeout=30,
        )
        r.raise_for_status()


# ── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="文档入库到 Qdrant")
    parser.add_argument("--file", required=True, help="文件路径")
    parser.add_argument("--collection", required=True, help="目标 collection 名")
    parser.add_argument("--mode", default="default", choices=["default", "law"], help="切片模式")
    parser.add_argument("--category", default="", help="可选标签")
    args = parser.parse_args()

    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print(json.dumps({"ok": False, "error": "缺少 QWEN_API_KEY 环境变量"}, ensure_ascii=False))
        sys.exit(1)

    # 读取
    try:
        text = read_file(args.file)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"读取文件失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    # 切片
    chunks = chunk_text(text, args.mode)
    print(f"[INFO] 切片完成，共 {len(chunks)} 块", file=sys.stderr)

    # Embedding
    try:
        vectors = embed_batch(chunks, api_key)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Embedding 失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    dim = len(vectors[0])

    # 确保 collection 存在
    try:
        ensure_collection(args.collection, dim)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"创建 collection 失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    # 构造 points
    source_name = Path(args.file).name
    points = [
        {
            "id": str(uuid.uuid4()),
            "vector": vector,
            "payload": {
                "content": chunk,
                "source_file": source_name,
                "chunk_index": i,
                "category": args.category,
            },
        }
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]

    # 写入
    try:
        upsert_points(args.collection, points)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"写入 Qdrant 失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(
        {"ok": True, "chunks_stored": len(chunks), "collection": args.collection, "source": source_name},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
