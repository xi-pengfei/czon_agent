"""
核心工具：vector_search — 语义向量检索

注册进 ToolRegistry 后，LLM 可直接 function call 调用，无需 skill 激活。
其他 skill（法规检索、案例检索、知识库问答等）通过此工具获取语义检索结果。

依赖（运行时可选，未安装则工具返回错误提示）：
  pip install openai requests

环境变量：
  QWEN_API_KEY   DashScope API Key（必填，用于 Qwen text-embedding-v3）
  QDRANT_URL     Qdrant 服务地址（默认 http://localhost:6333）
  EMBED_MODEL    embedding 模型（默认 text-embedding-v3）
"""
import logging
import os

logger = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v3")
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def vector_search(query: str, collection: str, top_k: int = 5, category: str = "") -> dict:
    """
    在指定 Qdrant collection 中做语义检索，返回 top-k 结果。

    Args:
        query:      用户问题或检索词
        collection: 目标 collection 名（如 law_regulations、court_cases）
        top_k:      返回结果数量（默认 5）
        category:   可选过滤标签（对应入库时的 --category 参数）

    Returns:
        {"ok": True, "hits": [{"score":..., "content":..., "source_file":..., "category":...}]}
        或 {"ok": False, "error": "..."}
    """
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return {"ok": False, "error": "缺少 QWEN_API_KEY 环境变量，无法使用向量检索"}

    try:
        from openai import OpenAI
        import requests as _requests
    except ImportError as e:
        return {"ok": False, "error": f"缺少依赖，请运行 pip install openai requests：{e}"}

    # 1. Embed query
    try:
        client = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE)
        resp = client.embeddings.create(model=EMBED_MODEL, input=[query])
        vector = resp.data[0].embedding
    except Exception as e:
        logger.error(f"vector_search embedding 失败：{e}")
        return {"ok": False, "error": f"Embedding 失败：{e}"}

    # 2. Search Qdrant
    body = {"vector": vector, "limit": top_k, "with_payload": True}
    if category:
        body["filter"] = {"must": [{"key": "category", "match": {"value": category}}]}

    try:
        r = _requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/search",
            json=body,
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        logger.error(f"vector_search Qdrant 检索失败：{e}")
        return {"ok": False, "error": f"Qdrant 检索失败（确认服务已启动）：{e}"}

    results = r.json().get("result", [])
    hits = [
        {
            "score": round(item.get("score", 0), 4),
            "content": item.get("payload", {}).get("content", ""),
            "source_file": item.get("payload", {}).get("source_file", ""),
            "category": item.get("payload", {}).get("category", ""),
        }
        for item in results
    ]

    return {"ok": True, "query": query, "collection": collection, "hits": hits}


def register(registry):
    """向 ToolRegistry 注册 vector_search 工具"""
    registry.register(
        name="vector_search",
        description=(
            "语义向量检索：在指定知识库（collection）中检索与 query 语义最相近的文档片段。"
            "适用于法律法规查询、案例检索、企业知识库问答等场景。"
            "使用前需确保 Qdrant 服务运行（QDRANT_URL）且已通过 ingest 脚本存入文档。"
            "常用 collection：law_regulations（法规）、court_cases（案例）、contract_templates（合同模板）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索问题或关键词，用自然语言描述",
                },
                "collection": {
                    "type": "string",
                    "description": "目标知识库名称，如 law_regulations、court_cases",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "返回结果数量（默认 5）",
                },
                "category": {
                    "type": "string",
                    "default": "",
                    "description": "可选：按标签过滤，如 合同法、刑法",
                },
            },
            "required": ["query", "collection"],
        },
        handler=vector_search,
    )
