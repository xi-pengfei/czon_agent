---
name: vector-store
description: 知识库操作：把用户上传的文件存入指定知识库，或用自然语言在知识库中检索内容。当用户说"存入/保存到XX库"或"在知识库里找/搜索"时激活。
---

# Vector Store Skill

## 权限边界（严格遵守）

| 操作 | 是否允许 |
|------|---------|
| 查询已有库 | ✅ |
| 存入文档到已有库 | ✅ |
| **新建库** | ❌ 管理员专属，拒绝执行 |
| **删除库或文档** | ❌ 管理员专属，拒绝执行 |

如果用户要求建库或删库，回复："知识库的创建和删除由管理员负责，我无法执行这个操作。"

---

## 场景一：查询

用户用自然语言提问时，先用 `vector_list_collections` 工具查看有哪些库可用，再用 `vector_search` 工具检索，把命中内容和来源文件名一起告诉用户。

**示例**
用户：民法典违约责任的条款是什么？
做法：
1. 调用 `vector_list_collections` 确认 law_regulations 存在
2. 调用 `vector_search`，query="违约责任条款"，collection="law_regulations"
3. 把 hits 里的 content 整理成回答，说明来源文件

---

## 场景二：存入文档

用户上传文件并说"存到XX库"时，执行以下步骤：

**第一步：确认目标库存在**

    bash: python skills/vector-store/scripts/manage.py list

检查用户说的库名是否在列表里。**如果不在，告知用户该库不存在，请联系管理员，不要自行创建。**

**第二步：确定文件的实际路径**

优先使用附件上下文中的完整路径（Agent 收到上传文件时，上下文里会有 `path` 字段）。
如果没有明确路径，再用 `bash: ls uploads/` 列出目录内容，找到对应文件名，拼成完整路径。
**不要直接猜 `uploads/<文件名>`，文件名可能含空格、哈希前缀或与用户描述不一致。**

**第三步：执行入库**

    bash: python skills/vector-store/scripts/ingest.py --file <实际路径> --collection <库名> [--mode law] [--category <标签>]

- 法律法规文件用 `--mode law`（按条款切片）
- 其他文件不加 mode（按段落切片）
- category 从用户描述里提取，如"合同法"、"刑法"

入库完成后告诉用户：文件已存入 XX 库，共切片 N 条，原始文件已归档。

**示例**
用户：把这份民法典上传到法规库，是合同法内容
做法：
1. 确认 law_regulations 库存在
2. 执行 `python skills/vector-store/scripts/ingest.py --file uploads/民法典.txt --collection law_regulations --mode law --category 合同法`
3. 回复入库结果

---

## 已有知识库说明

> ⚠️ **此表由管理员维护，每次新建库后必须在此补一行。**
> `vector_list_collections` 只返回库的英文名，不含描述。Agent 靠读这张表判断"用户的问题该搜哪个库"，表里没有的库 Agent 无法正确路由。
> `config.yaml` 不需要改，其规则已是通用的。

| 库名 | 存放内容 |
|------|---------|
| `law_regulations` | 法律法规（民法典、刑法、劳动法等） |
| `court_cases` | 司法判例、裁判文书 |
| `contract_templates` | 合同模板 |
| `legal_procedures` | 办案流程、诉讼指引 |

新建库的完整流程见 `README.md` → "第三步：新建知识库（三步缺一不可）"。

---

## 重要：Qdrant 启动方式

首次部署运行 `bash scripts/install_qdrant.sh` 完成安装，之后 Qdrant 随系统自动启动。
`python main.py webui` 只启动 Agent，Qdrant 是独立本地进程，数据存于 `~/data/qdrant/`。
