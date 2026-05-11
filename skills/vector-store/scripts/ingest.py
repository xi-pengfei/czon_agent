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
import hashlib
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

def ensure_collection(name: str) -> dict:
    """确认 collection 存在；不存在则报错，不自动创建（建库是管理员职责）"""
    r = requests.get(f"{QDRANT_URL}/collections/{name}", timeout=10)
    if r.status_code == 404:
        raise RuntimeError(
            f"知识库 '{name}' 不存在，请联系管理员执行：\n"
            f"  python skills/vector-store/scripts/manage.py create --collection {name} --dim 1024\n"
            f"并在 skills/vector-store/SKILL.md 和 config.yaml 中补充该库的说明。"
        )
    r.raise_for_status()
    return r.json().get("result", {})


def collection_vector_size(info: dict):
    vectors = (info.get("config") or {}).get("params", {}).get("vectors")
    if isinstance(vectors, dict) and "size" in vectors:
        return vectors.get("size")
    if isinstance(vectors, dict):
        for value in vectors.values():
            if isinstance(value, dict) and "size" in value:
                return value.get("size")
    return None


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

    # 先确认 collection 存在，避免库名错误时仍调用 embedding API
    try:
        collection_info = ensure_collection(args.collection)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    # Embedding
    try:
        vectors = embed_batch(chunks, api_key)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Embedding 失败：{e}"}, ensure_ascii=False))
        sys.exit(1)

    dim = len(vectors[0])

    expected_dim = collection_vector_size(collection_info)
    if expected_dim and expected_dim != dim:
        print(json.dumps({
            "ok": False,
            "error": f"Embedding 维度 {dim} 与 collection 维度 {expected_dim} 不一致，请检查 EMBED_MODEL 或重新建库",
        }, ensure_ascii=False))
        sys.exit(1)

    # 计算源文件 metadata（先算 hash，再决定归档路径）
    src = Path(args.file).resolve()
    source_hash = hashlib.md5(src.read_bytes()).hexdigest()

    # 把原始文件归档到 workspace/vector-docs/<collection>/ 下统一管理
    # 同名但内容不同时，在文件名中嵌入 hash 前8位，避免覆盖旧内容
    root = Path(__file__).resolve().parents[3]
    archive_dir = root / "workspace" / "vector-docs" / args.collection
    archive_dir.mkdir(parents=True, exist_ok=True)

    existing = archive_dir / src.name
    if not existing.exists():
        dest = existing
    else:
        existing_hash = hashlib.md5(existing.read_bytes()).hexdigest()
        if existing_hash == source_hash:
            dest = existing  # 完全相同，复用
            print(f"[INFO] 原始文件内容相同，复用归档 {dest}", file=sys.stderr)
        else:
            # 同名不同内容：归档为 filename.<hash8>.ext
            stem, suffix = src.stem, src.suffix
            dest = archive_dir / f"{stem}.{source_hash[:8]}{suffix}"
            print(f"[INFO] 同名文件内容不同，归档为新文件 {dest}", file=sys.stderr)

    if not dest.exists():
        import shutil
        shutil.copy2(str(src), str(dest))
        print(f"[INFO] 原始文件已归档至 {dest}", file=sys.stderr)

    source_path = str(dest)          # 指向归档位置，而非上传临时路径
    source_file = src.name           # 原始文件名（展示用）
    # source_hash 已在归档阶段计算，此处复用

    # 构造 points，每个 chunk 都携带完整的来源 metadata
    points = [
        {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{args.collection}:{source_hash}:{i}")),
            "vector": vector,
            "payload": {
                "content": chunk,
                "source_file": source_file,    # 文件名（展示用）
                "source_path": source_path,    # 完整路径（定位用）
                "source_hash": source_hash,    # 文件 MD5（可靠删除/更新用）
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
        {
            "ok": True,
            "chunks_stored": len(chunks),
            "collection": args.collection,
            "source_file": source_file,
            "source_hash": source_hash,
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
