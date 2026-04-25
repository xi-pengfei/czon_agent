# czon Agent

极简 Python Agent Runtime，支持 OpenAI-compatible LLM、工具调用、可插拔 Skills、工具策略控制和 WebUI 流式输出。

czon Agent 的定位不是普通聊天机器人，而是一个最小执行内核：优先使用 Skills，其次使用 read/write/bash；如果现有工具解决不了，就明确说明缺少能力并建议添加 Skill。

当前支持 Kimi / Qwen / DeepSeek。

## 快速开始

### 1. 安装依赖

```bash
cd /Users/pengfei/Desktop/czon_agent
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

### 3. 可选：初始化示例数据库

```bash
python main.py setup
```

### 4. 启动

```bash
# 默认进入交互式 CLI
python main.py

# 单次 CLI
python main.py "你好，我叫小明"

# WebUI
python main.py webui
# 打开 http://127.0.0.1:8000
```

## 目录结构

```text
czon_agent/
├── core/             # Agent loop、LLM、Skill、ToolRegistry、ToolPolicy
├── tools_builtin/    # read / write / bash / activate_skill
├── skills/           # 可插拔 Skill 目录
├── adapters/         # CLI 和 FastAPI WebUI
├── webui/            # 单文件前端
├── data/             # 示例 SQLite 数据库
├── uploads/          # 用户上传输入
├── workspace/        # Agent 默认输出目录
├── logs/             # 日志
├── config.yaml       # Provider、Skill、Agent、ToolPolicy 配置
└── main.py           # 统一入口
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

内置的 `sqlite-sample` 演示了通过 Skill 查询 SQLite 数据库：

```bash
python skills/sqlite-sample/scripts/query.py --sql "SELECT * FROM employees"
```

内置的 `office-io` 演示了通过 Skill 读写常见办公文件：

```bash
python skills/office-io/scripts/office.py read uploads/example.docx
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
