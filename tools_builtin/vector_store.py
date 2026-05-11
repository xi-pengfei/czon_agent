"""
核心工具：vector_list_collections + vector_search

注册进 ToolRegistry，LLM 直接 function call，无需 skill 激活。
只负责检索和发现；文档入库、库管理通过 skills/vector-store/scripts/ 脚本执行。

Qdrant 需单独安装并运行（见 scripts/install_qdrant.sh）：
  bash scripts/install_qdrant.sh   # 一键安装，开机自启
  数据目录：~/data/qdrant/

环境变量：
  QWEN_API_KEY    DashScope API Key（vector_search 必填）
  QDRANT_URL      Qdrant 地址（默认 http://localhost:6333）
  EMBED_MODEL     embedding 模型（默认 text-embedding-v3，维度 1024）
"""
import logging
import os

import requests as _req

logger = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v3")
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_OPENAI_CLIENTS = {}


def get_embedding_client(api_key: str):
    from openai import OpenAI

    cache_key = (api_key, DASHSCOPE_BASE)
    if cache_key not in _OPENAI_CLIENTS:
        _OPENAI_CLIENTS[cache_key] = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE)
    return _OPENAI_CLIENTS[cache_key]


def vector_list_collections() -> dict:
    """
    列出所有可用的 collection 及文档数量。
    Agent 不确定搜哪个库时先调此工具。
    失败抛异常，ToolRegistry 包装成 ToolResult.failure。
    """
    try:
        r = _req.get(f"{QDRANT_URL}/collections", timeout=10)
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"无法连接 Qdrant，请先运行 scripts/install_qdrant.sh：{e}") from e

    result = []
    for col in r.json().get("result", {}).get("collections", []):
        name = col["name"]
        try:
            # Qdrant count 接口是 POST，GET 会返回 404
            cr = _req.post(f"{QDRANT_URL}/collections/{name}/points/count",
                           json={}, timeout=10)
            count = cr.json().get("result", {}).get("count", "?") if cr.ok else "?"
        except Exception:
            count = "?"
        result.append({"collection": name, "points_count": count})

    return {"collections": result}


def vector_search(query: str, collection: str, top_k: int = 5, category: str = "") -> dict:
    """
    在指定 collection 中语义检索，返回 top-k 结果。
    失败抛异常，ToolRegistry 包装成 ToolResult.failure。
    """
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 QWEN_API_KEY 环境变量")

    # 1. Embed query
    try:
        client = get_embedding_client(api_key)
        vector = client.embeddings.create(model=EMBED_MODEL, input=[query]).data[0].embedding
    except Exception as e:
        raise RuntimeError(f"Embedding 失败：{e}") from e

    # 2. Search
    body = {"vector": vector, "limit": top_k, "with_payload": True}
    if category:
        body["filter"] = {"must": [{"key": "category", "match": {"value": category}}]}

    try:
        r = _req.post(
            f"{QDRANT_URL}/collections/{collection}/points/search",
            json=body, timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Qdrant 检索失败：{e}") from e

    hits = [
        {
            "score": round(item.get("score", 0), 4),
            "content": item.get("payload", {}).get("content", ""),
            "source_file": item.get("payload", {}).get("source_file", ""),
            "category": item.get("payload", {}).get("category", ""),
        }
        for item in r.json().get("result", [])
    ]
    return {"query": query, "collection": collection, "hits": hits}


def register(registry):
    """注册 vector_list_collections 和 vector_search 到 ToolRegistry"""
    registry.register(
        name="vector_list_collections",
        description=(
            "列出所有向量知识库（collection）及文档数量。"
            "用户问题涉及知识库但未指定库名时，先调此工具确认有哪些库，再调 vector_search。"
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        handler=vector_list_collections,
    )
    registry.register(
        name="vector_search",
        description=(
            "语义检索：在指定知识库中找与问题最相关的文档片段。"
            "适用场景：法律法规查询、案例检索、企业知识库问答。"
            "常用库名：law_regulations（法规）、court_cases（判例）、contract_templates（合同模板）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query":      {"type": "string", "description": "检索问题，自然语言描述"},
                "collection": {"type": "string", "description": "目标知识库名称"},
                "top_k":      {"type": "integer", "default": 5, "description": "返回结果数（默认 5）"},
                "category":   {"type": "string", "default": "", "description": "可选：按标签过滤"},
            },
            "required": ["query", "collection"],
        },
        handler=vector_search,
    )
