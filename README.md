# czon agent

极简 Python Agent Runtime，
极简,优雅,只保留核心基本功能,
通过即插即用的skills 适配不同的垂直场景,专注企业生产力的AI Agent.
支持 OpenAI-compatible LLM、Skills、工具策略控制和 WebUI 流式输出。

czon agent 的定位不是普通聊天机器人，而是一个最小执行内核：优先使用 Skills，其次使用 read/write/bash；如果现有工具解决不了，可直接插入符合能力要求的Skill。

当前支持 Kimi / Qwen / DeepSeek。

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，至少填入一个 provider 的 key
# MOONSHOT_API_KEY=sk-...
```

### 3. 启动

```bash
# WebUI（推荐）
python main.py webui
# 打开 http://127.0.0.1:8000

# 交互式 CLI
python main.py

# 单次 CLI
python main.py "帮我列出 workspace 下的文件"
```

### 4. 启用向量知识库（RAG，首次部署）

向量检索是核心能力，支持法规/案例/合同的语义问答。首次部署需要额外两步：

```bash
# macOS：安装 Qdrant 本地向量数据库二进制（下载安装到 .runtime/qdrant/）
bash scripts/install_qdrant.sh

# 在 .env 中补充 embedding 所需的 key
QWEN_API_KEY=sk-xxx
```

安装后重启 Agent 即可使用。之后 `python main.py webui`、交互 CLI、单次 CLI 都会自动确保 Qdrant 在线，Qdrant 数据存于 `data/qdrant/`。建库、入库、检索、备份恢复的完整流程见下文"[向量知识库](#向量知识库rag完整使用流程)"章节。

### 5. 可选：初始化示例数据库

```bash
# 生成 data/sample.db（含 employees 表，供 sqlite-sample skill 演示用）
python main.py setup
```

## 目录结构

```text
czon_agent/
├── core/             # Agent loop、LLM、Skill、ToolRegistry、ToolPolicy
├── tools_builtin/    # file_ops(read/write)、shell(bash)、skill_ops(activate_skill)、vector_store(vector_search)
├── skills/           # 可插拔 Skill 目录（当前：hello-world、sqlite-sample、office-io、vector-store、dianxiaomi-export、pledgebox-sync）
├── adapters/         # CLI 和 FastAPI WebUI 适配器
├── webui/            # 单文件前端 index.html
├── scripts/          # 运维脚本（install_qdrant.sh 等）
├── data/             # 示例数据与本地数据库（sample.db / qdrant，均不进 Git）
├── .runtime/         # 项目本地运行依赖（Qdrant 二进制，不进 Git）
├── uploads/          # 用户上传文件输入区（文件名为 hash，WebUI 自动管理）
├── workspace/        # Agent 默认文件输出目录
├── logs/             # 运行日志
├── config.yaml       # Provider、Skill、Agent、ToolPolicy 配置
└── main.py           # 统一入口（webui / setup / 直接输入消息）
```

## 核心设计

### 执行优先级

Agent 的行为优先级：

1. 有相关 Skill：先 `activate_skill`，再按 Skill 说明执行。
2. 没有相关 Skill：尽量用 `read` / `write` / `bash` 完成任务。
3. 工具无法完成：直接说明当前缺少对应能力，不用普通大模型话术假装解决。

当用户询问当前文件、目录、数据库、命令输出或本机状态时，Agent 应先用工具检查，不应凭常识回答“无法访问”。

### Agent Loop

`Agent.run()` 每次执行一轮无状态任务：

1. 构建 system prompt 和用户消息。
2. 调用 LLM。
3. 如果 LLM 返回 `tool_calls`，逐个执行工具。
4. 把结构化工具结果作为 JSON 塞回 LLM 上下文。
5. 直到 LLM 返回最终文本，或达到最大迭代次数。

### ToolRegistry

`ToolRegistry` 负责统一管理工具：

- 注册 OpenAI function calling schema。
- 执行工具 handler。
- 调用 `ToolPolicy` 做 allow / confirm / block 判断。
- 把工具执行结果包装成结构化 `ToolResult`。

工具结果格式：

```json
{
  "ok": true,
  "data": "...",
  "error": null,
  "meta": {}
}
```

错误结果格式：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "type": "ConfirmationRequired",
    "message": "命令命中风险确认规则: rm ",
    "recoverable": true
  },
  "meta": {
    "confirmation": {
      "id": "pending-confirmation-id",
      "tool_name": "bash",
      "args": {"command": "rm workspace/a.txt"},
      "reason": "命令命中风险确认规则: rm ",
      "risk_level": "medium"
    }
  }
}
```

### ToolPolicy

工具策略采用“三层策略”：

1. 明显危险：直接 block。
2. 有风险但合理：要求用户确认。
3. 普通行为：默认 allow。

策略默认是自由优先，只保留少量高危 block 和必要确认。命中 `confirm` 时，WebUI 会弹出确认框并在工具步骤里显示“确认执行”按钮；用户点击按钮，或在仍有待确认项时输入“确认”，后端都会执行原始 pending tool call，而不是让模型重新猜命令。

```yaml
tool_policy:
  default: allow
  block_tools: []
  confirm_tools: []
  bash:
    blocked_patterns:
      - "rm -rf /"
      - "sudo"
      - "shutdown"
      - "reboot"
      - "> /dev/"
    confirm_patterns:
      - "rm "
      - "mv "
      - "chmod "
      - "chown "
  write:
    confirm_paths:
      - ".env"
      - "config.yaml"
```

### Skills

Skill 是文档驱动的能力扩展。启动时只把 name 和 description 放进 catalog；真正需要时，LLM 会调用 `activate_skill` 加载完整 `SKILL.md`。

这样可以避免把所有技能说明一次性塞进上下文，也能减少模型乱猜脚本用法。

## 内置工具

| 工具 | 说明 |
|------|------|
| `read` | 读取文本文件，最多返回 10000 字符 |
| `write` | 写入文本文件，只允许写入配置的 workspace 目录 |
| `bash` | 执行 shell 命令，返回结构化 `exit_code/stdout/stderr`，受 ToolPolicy 管控 |
| `activate_skill` | 按需加载 Skill 的完整说明 |
| `vector_search` | 语义向量检索（需 Qdrant 服务 + QWEN_API_KEY） |

目录约定：

- `uploads/` 是用户上传给 Agent 的输入区。
- `workspace/` 是 Agent 生成文件的默认输出区。
- `logs/` 是系统日志目录，不作为 Agent 工作产物目录。
- 生成或修改 `workspace/` 下的文件后，Agent 应在最终回复中提供下载链接：`/download/<相对路径>`。

默认工作区可以在 `config.yaml` 中调整：

```yaml
workspace:
  dir: ./workspace
```

## Web API

### 普通接口

```http
POST /api/chat
```

请求：

```json
{
  "text": "查询薪资最高的3个员工",
  "attachments": [],
  "provider": "kimi",
  "session_id": "browser-session-id"
}
```

`attachments` 来自 `/api/upload`，结构示例：

```json
{
  "path": "uploads/xxx.docx",
  "name": "方案.docx",
  "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "size": 12345
}
```

响应：

```json
{
  "reply": "...",
  "steps": [
    {
      "type": "tool_call",
      "name": "activate_skill",
      "args": {"name": "sqlite-sample"},
      "result": {"ok": true, "data": "...", "error": null, "meta": {}}
    }
  ]
}
```

### 流式接口

```http
POST /api/chat/stream
```

返回 `text/event-stream`，事件类型：

| 事件 | 说明 |
|------|------|
| `agent_start` | Agent 开始处理 |
| `assistant_delta` | LLM 文本增量输出 |
| `tool_result` | 一个工具步骤完成 |
| `confirmation_required` | 工具命中确认策略 |
| `agent_done` | 最终回复完成 |
| `agent_error` | 后端执行异常 |

当前支持 token delta 和工具步骤事件。工具调用本身仍然遵循模型 function calling 协议：模型决定调用工具后，后端执行工具并把结构化结果推给前端。

### WebUI 会话历史

WebUI 使用 `sessionStorage` 保存当前标签页的 `session_id`，后端用内存保存该 session 的短期历史。

- 历史只在本次服务进程内有效，服务重启后清空。
- 同一个标签页刷新后仍使用原 session；关闭标签页后由浏览器丢弃。
- 每个 session 最多保留最近 20 条 user/assistant 文本消息。
- 当历史总字符数超过 80000 时，从最旧消息开始截断。
- 不做语义相关性筛选，不做长期记忆。
- WebUI 的“新对话”按钮会清空当前 session 并创建新 session。

### 下载 workspace 文件

```http
GET /download/{file_path}
```

只允许下载配置的 workspace 目录内文件。示例：

```markdown
[下载文件](/download/report.docx)
```

### 确认执行接口

```http
POST /api/tool/confirm
```

请求：

```json
{
  "confirmation_id": "pending-confirmation-id"
}
```

响应会返回被确认执行的工具 step。WebUI 会自动调用这个接口，通常不需要手写请求。

## 添加新 Skill

1. 在 `skills/` 下创建目录，名称只能包含小写字母、数字和连字符。
2. 新建 `SKILL.md`，必须包含 YAML frontmatter。
3. 如需脚本，放到该 skill 的 `scripts/` 目录。
4. 重启 Agent 后自动扫描。

示例：

```markdown
---
name: my-skill
description: 一句话说明这个 skill 什么时候应该被使用。
---

# My Skill

## How to use

运行脚本：

    python skills/my-skill/scripts/run.py
```

### 向量知识库（RAG）完整使用流程 {#向量知识库rag完整使用流程}

检索由内置工具 `vector_search` 承担（Agent 启动即可用），文档入库和库管理由 `vector-store` skill 的脚本完成。

#### 架构说明

```
用户对话 → Agent (python main.py webui)
               ↓ 检索时自动调用
         vector_search（tools_builtin，常驻内存）
               ↓
         Qdrant（Agent 自动拉起 .runtime/qdrant/bin/qdrant）
               ↓
         data/qdrant/（collection 与向量数据）
               ↑ 入库时由 skill 脚本执行
         ingest.py（skills/vector-store/scripts/）
```

**Agent 如何知道中文问题对应哪个英文库名？**

`vector_list_collections` 只返回库的英文名（如 `law_regulations`），不含任何描述。Agent 靠读取 `skills/vector-store/SKILL.md` 里的中英对照表来判断"用户问的问题该搜哪个库"。**每次新建库，管理员必须在这张表里补一行，否则 Agent 看到库名也不知道它存的是什么内容，无法正确路由。**

`config.yaml` 的规则是通用的（"先调 list 看有哪些库，再搜最相关的"），新建库后不需要改它。

> 首次部署步骤见快速开始第4步（安装 Qdrant + 配置 QWEN_API_KEY）。日常只需启动 Agent；如果 Qdrant 未运行，Agent 会自动从 `.runtime/qdrant/bin/qdrant` 拉起本地进程，并把数据写入 `data/qdrant/`。

#### 安装、日常启动与备份

`scripts/install_qdrant.sh` 只在首次部署或更新 Qdrant 二进制时执行。它不是日常重启命令，也不会清空已有向量数据。当前脚本面向 macOS，会根据当前机器架构下载 Qdrant，放到项目本地，并在端口空闲时临时启动一次做 healthz 验证：

```text
.runtime/qdrant/bin/qdrant
```

`.runtime/` 是可重新生成的运行依赖，不提交到 Git，也不需要备份。日常启动只需要：

```bash
python main.py webui
```

Agent 会检查 `http://localhost:6333/healthz`；如果 Qdrant 没运行，就自动从 `.runtime/qdrant/bin/qdrant` 启动，并使用项目内数据目录：

```text
data/qdrant/
```

真正需要备份的是 `data/qdrant/`，这里保存 collection、向量和 payload。GitHub 只保存源码，不保存 `.runtime/` 和 `data/qdrant/`。

Windows/Linux 也可以使用同样的项目约束：把对应系统的 Qdrant 可执行文件放到项目内，或修改 `config.yaml` 里的 `qdrant.bin` 指向实际路径；`qdrant.data_dir` 仍应指向项目内的 `data/qdrant/`。这样 Agent 启动、备份、恢复的逻辑保持一致。

换电脑或重装系统时，恢复顺序是：

```bash
git clone <repo>
cd czon_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash scripts/install_qdrant.sh
# 然后把备份的 data/qdrant/ 恢复到项目同名目录
python main.py webui
```

如果没有备份 `data/qdrant/`，重新 clone 后可以恢复代码，但不能恢复原来的知识库内容。

#### 新建知识库（管理员，三步缺一不可）

> ⚠️ **注意：Qdrant 里没有任何预建库，下面的库名只是规划示例，需要管理员手动创建。**

**Step 1 — 在 Qdrant 里创建 collection：**

```bash
python skills/vector-store/scripts/manage.py create --collection law_regulations --dim 1024
```

**Step 2 — 更新 `skills/vector-store/SKILL.md` 中的中英对照表：**

在 `## 已有知识库说明` 表格里补一行，写清楚库名和存放内容。这是 Agent 判断"用户问的问题该搜哪个库"的唯一依据，不更新则 Agent 看到库名也不知道它存什么，无法正确路由。

`config.yaml` 不需要改，它的规则是通用的。

**其他管理命令：**

```bash
# 查看所有已建库
python skills/vector-store/scripts/manage.py list

# 查看某个库的文档数量
python skills/vector-store/scripts/manage.py info --collection law_regulations

# 删除整个库（管理员专属）
python skills/vector-store/scripts/manage.py delete --collection law_regulations
```

**规划中的库（需按上述三步手动创建）：**

| 库名（英文） | 建议存放内容 |
|-------------|------------|
| `law_regulations` | 法律法规（民法典、刑法、劳动法等） |
| `court_cases` | 司法判例、裁判文书 |
| `contract_templates` | 合同模板 |
| `legal_procedures` | 办案流程、诉讼指引 |

#### 第四步：文档入库

**方式一：用户通过 Agent 上传**（推荐，无需命令行）
> 用户说："把这份民法典存到法规库，是合同法内容"
> Agent 自动完成入库，原始文件归档至 `workspace/vector-docs/<库名>/`

**方式二：管理员直接执行脚本**

```bash
# 法律法规用 --mode law（按"第X条"切片）
python skills/vector-store/scripts/ingest.py \
  --file 民法典.txt --collection law_regulations --mode law --category 合同法

# 普通文档用默认模式（按段落切片）
python skills/vector-store/scripts/ingest.py \
  --file 劳动合同模板.docx --collection contract_templates
```

支持格式：`.txt` `.md` `.docx` `.pdf`

#### 第五步：删除某个文件的向量数据

```bash
# 精确删除（推荐，用入库时打印的 source_hash）
python skills/vector-store/scripts/manage.py delete-source \
  --collection law_regulations --source-hash abc123def456

# 按文件名删除（有重名风险）
python skills/vector-store/scripts/manage.py delete-source \
  --collection law_regulations --source 民法典.txt
```

#### 第六步：检索（直接对话）

无需任何命令，直接问 Agent：
> "民法典里关于违约责任的条款是什么？"
> "帮我找一份劳动合同模板"
> "有没有关于劳动争议的判例？"

Agent 自动调用 `vector_list_collections` 确认库，再调用 `vector_search` 检索，返回内容并标注来源文件名。

内置的 `sqlite-sample` 演示了通过 Skill 查询 SQLite 数据库（需先 `python main.py setup` 生成示例库）：

```bash
python skills/sqlite-sample/scripts/query.py --sql "SELECT * FROM employees"
```

内置的 `office-io` 支持读写常见办公文件（inspect / read / write-md / write-txt / write-csv / write-docx / write-xlsx / write-pptx / write-pdf）：

```bash
python skills/office-io/scripts/office.py read uploads/<文件名>
python skills/office-io/scripts/office.py write-xlsx workspace/table.xlsx --json '[{"姓名":"张三","薪资":18000}]'
```

## 切换 LLM

编辑 `config.yaml`：

```yaml
active_provider: qwen
```

或在 WebUI 右上角切换 provider。未配置 API Key 的 provider 会在前端禁用。

## 当前边界

- 用户确认目前是 WebUI 内存态 pending confirmation：服务重启后待确认项会丢失。
- WebUI 已支持 SSE，包括 `assistant_delta` 文本增量和工具步骤事件。
- `bash` 仍然是高自由度工具，适合本地可信使用；对外部署前应继续加强沙箱和审计。
- 垂直能力应优先通过 Skills 扩展，不进入核心 runtime。
