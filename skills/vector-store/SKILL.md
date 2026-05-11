---
name: vector-store
description: 向量知识库运维：把文档存入 Qdrant 向量库，或管理 collection。注意：检索功能已注册为核心工具 vector_search，无需激活此 skill 即可直接调用。激活此 skill 的场景是：用户明确要求"存入文档"或"管理知识库"（创建/删除/查看 collection）。
---

# Vector Store Skill（运维层）

## 架构说明

`vector_search` 已作为**核心工具**注册进 ToolRegistry，LLM 可直接 function call 调用，无需激活此 skill。

此 skill 只负责**运维操作**：文档入库（ingest）和 collection 管理（manage）。

```
核心工具（tools_builtin/vector_store.py）
  └── vector_search   ← LLM 直接 function call，实时检索

运维脚本（此 skill）
  ├── ingest.py       ← 文档存入（一次性/批量操作）
  └── manage.py       ← collection 管理（创建/删除/查看）
```

## 环境要求

- Qdrant 服务运行中（默认 `http://localhost:6333`，可用 `QDRANT_URL` 覆盖）
- 环境变量 `QWEN_API_KEY`（DashScope API Key）
- 可选：`EMBED_MODEL`（默认 `text-embedding-v3`）

---

## 1. 文档入库（ingest）

    bash: python skills/vector-store/scripts/ingest.py --file <文件路径> --collection <库名> [--mode law|default] [--category <标签>]

- `--mode law`：按"第X条"切片，适合法律法规文本；默认按段落切
- `--category`：可选标签，检索时可按标签过滤
- 支持格式：`.txt` `.md` `.docx` `.pdf`
- collection 不存在时自动创建

**示例：存入法规**

    bash: python skills/vector-store/scripts/ingest.py --file /path/to/民法典.txt --collection law_regulations --mode law --category 合同法

---

## 2. Collection 管理（manage）

**列出所有库：**

    bash: python skills/vector-store/scripts/manage.py list

**查看库信息（文档条数等）：**

    bash: python skills/vector-store/scripts/manage.py info --collection <库名>

**创建新库：**

    bash: python skills/vector-store/scripts/manage.py create --collection <库名>

**删除库：**

    bash: python skills/vector-store/scripts/manage.py delete --collection <库名>

---

## 常用 Collection 命名约定

| Collection 名 | 用途 |
|---------------|------|
| `law_regulations` | 法律法规 |
| `court_cases` | 司法案例 |
| `contract_templates` | 合同模板 |
| `hospital_knowledge` | 医院业务知识 |

---

## 其他 skill 如何使用检索能力

无需调用此 skill，直接说明 LLM 调用 `vector_search` 工具即可：

```
# 法规检索 skill 的 SKILL.md 示例写法：
调用 vector_search 工具，参数：
  query = <用户问题>
  collection = "law_regulations"
  top_k = 5
把 hits 里的 content 拼入回答，引用 source_file 说明出处。
```
