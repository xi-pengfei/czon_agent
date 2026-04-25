# czon Agent — 技术架构与场景应用解读

> 一个极简、优雅、可插拔的 Python Agent Runtime
> —— 核心代码 ~600 行，垂直能力靠 skills 即插即用

---

## 一、一句话定位

czon Agent 不是一个 chat bot，**是一个会调工具、能完成实际工作的执行框架**。

它把传统 Agent 框架里"啥都揽进核心"的部分全部解耦：

| 关注点 | 由谁负责 |
|---|---|
| 垂直能力（处理 PDF/Excel/数据库…） | **skills/** 目录下的 SKILL.md，即插即用 |
| 安全边界（什么命令要确认、什么禁用） | **config.yaml** 的 `tool_policy` 配置 |
| 业务约束（输出路径、命名规范、降级策略） | **config.yaml** 的 `agent.extra_rules` |
| 用户交互（CLI / WebUI / 未来其他端） | **adapters/** 适配器层 |

核心代码（core/）只剩三件事：**循环、工具分发、模型调用**。

---

## 二、整体架构

### 2.1 分层架构图

```
┌─────────────────────────────────────────────────────────┐
│                    Adapters 适配器层                     │
│  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │  CLI / REPL  │  │  FastAPI WebUI（SSE 流式 + 会话）  │ │
│  │  cli.py      │  │  server.py                       │ │
│  └──────┬───────┘  └────────────────┬─────────────────┘ │
└─────────┼────────────────────────────┼──────────────────┘
          │                            │
          │   agent.run(text, history, on_step, on_delta)
          ▼                            ▼
┌─────────────────────────────────────────────────────────┐
│                    Core 核心层（无状态）                 │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Agent 主循环  core/agent.py                        │ │
│  │   • build_system_prompt()  组装 skill 目录 + 规则   │ │
│  │   • _complete() / _consume_stream()  流式 + 兜底    │ │
│  │   • for iteration in 1..max:                        │ │
│  │       msg = LLM.complete(...)                       │ │
│  │       if no tool_calls: return reply                │ │
│  │       for tc in tool_calls: registry.execute(...)   │ │
│  └─────┬───────────────────┬───────────────────┬───────┘ │
│        │                   │                   │         │
│  ┌─────▼──────┐  ┌─────────▼────────┐  ┌──────▼───────┐ │
│  │ LLM 抽象   │  │ ToolRegistry +   │  │ SkillLoader  │ │
│  │ core/llm.py│  │ ToolPolicy       │  │ core/skills  │ │
│  │            │  │ core/tools.py    │  │ .py          │ │
│  │ kimi/qwen/ │  │  • allow/confirm │  │  • 扫描       │ │
│  │ deepseek   │  │   /block 三态    │  │  • 校验       │ │
│  │ OpenAI 兼容 │  │  • ToolResult    │  │  • 懒加载     │ │
│  └────────────┘  │   统一返回格式   │  └──────────────┘ │
│                  └──────────────────┘                    │
└─────────────────────────────────────────────────────────┘
          │                                │
          ▼                                ▼
┌────────────────────────┐    ┌────────────────────────────┐
│  内置工具 tools_builtin │    │  外部资源                   │
│   • read  (file_ops)   │    │   • skills/<name>/SKILL.md │
│   • write (file_ops)   │    │   • workspace/  输出区     │
│   • bash  (shell)      │    │   • uploads/    上传区     │
│   • activate_skill     │    │   • .env        密钥        │
└────────────────────────┘    └────────────────────────────┘
```

### 2.2 目录结构

```
czon_agent/
├── main.py                    # 统一入口（CLI / REPL / WebUI / setup）
├── config.yaml                # provider、skills、规则、策略
├── .env                       # API Keys
│
├── core/                      # ── 核心抽象（无状态、薄）
│   ├── agent.py              #    Agent 主循环
│   ├── llm.py                #    LLM 抽象（OpenAI 兼容协议封装）
│   ├── skills.py             #    Skill 扫描器 + 懒加载器
│   ├── tools.py              #    工具注册表 + 策略引擎
│   └── logging_setup.py      #    rich + file 双输出日志
│
├── adapters/                  # ── 适配器（管交互、管会话）
│   ├── cli.py                #    交互式 REPL + 单次执行
│   └── server.py             #    FastAPI + SSE + 会话 + 上传下载
│
├── tools_builtin/             # ── 内置工具（可被 skill 复用）
│   ├── file_ops.py           #    read / write
│   ├── shell.py              #    bash
│   └── skill_ops.py          #    activate_skill
│
├── skills/                    # ── 可插拔垂直能力（每子目录一个 skill）
│   ├── pdf/SKILL.md
│   ├── xlsx/SKILL.md
│   └── ...
│
├── workspace/                 # ── Agent 唯一可写目录（输出落地）
├── uploads/                   # ── 用户上传文件
├── webui/                     # ── 前端静态资源
└── logs/                      # ── 运行日志
```

---

## 三、场景驱动：一次完整请求的生命周期

### 3.1 场景设定

> **用户在 WebUI 输入：**
> "我桌面上的 `sales.xlsx` 是 Q1 销售流水，帮我分析一下哪个产品季度内增速最快，
> 然后生成一份 PDF 报告，放到 workspace 里给我下载链接。"

这条请求会**串起 czon Agent 几乎全部模块**：用户输入 → 适配器 → 核心循环 → LLM 决策 → skills 激活 → bash 执行 → 文件写入 → 适配器返回。

### 3.2 端到端时序图

```
用户                WebUI(server.py)         Agent(agent.py)        LLM            Tools/Skills
 │                       │                        │                  │                  │
 │  输入文本+附件         │                        │                  │                  │
 ├──────────────────────►│                        │                  │                  │
 │                       │  ① /api/chat/stream    │                  │                  │
 │                       │     拿到 session 历史   │                  │                  │
 │                       │     调 agent.run()     │                  │                  │
 │                       ├───────────────────────►│                  │                  │
 │                       │                        │ ② build_system   │                  │
 │                       │                        │   _prompt()      │                  │
 │                       │                        │   含 skill 目录   │                  │
 │                       │                        │                  │                  │
 │                       │                        │ ③ stream_complete│                  │
 │                       │                        ├─────────────────►│                  │
 │                       │                        │                  │                  │
 │                       │                        │ ④ tool_calls=    │                  │
 │                       │                        │   activate_skill │                  │
 │                       │                        │   ("xlsx")       │                  │
 │                       │                        │◄─────────────────┤                  │
 │                       │                        │                                     │
 │                       │                        │ ⑤ registry.execute("activate_skill")│
 │                       │                        ├────────────────────────────────────►│
 │                       │                        │   返回 SKILL.md 正文（怎么读 xlsx）  │
 │                       │                        │◄────────────────────────────────────┤
 │                       │ on_step→SSE 推送        │                                     │
 │                       │◄───────────────────────│                                     │
 │   实时看到 🔧 step    │                        │                                     │
 │◄──────────────────────│                        │                                     │
 │                       │                        │ ⑥ 第二轮 LLM 调用（带 skill 内容）  │
 │                       │                        ├─────────────────►│                  │
 │                       │                        │   tool_calls=bash("python ...xlsx") │
 │                       │                        │◄─────────────────┤                  │
 │                       │                        │ ⑦ ToolPolicy 检查 → allow            │
 │                       │                        │   bash 执行 → stdout 含分析数据      │
 │                       │                        ├────────────────────────────────────►│
 │                       │                        │◄────────────────────────────────────┤
 │                       │                        │                                     │
 │                       │                        │ ⑧ 第三轮 LLM 调用                    │
 │                       │                        │   activate_skill("pdf")              │
 │                       │                        │   bash 生成 PDF 到 workspace/        │
 │                       │                        │   write_file 兜底（受 workspace 限制）│
 │                       │                        │                                     │
 │                       │                        │ ⑨ 最终轮：no tool_calls              │
 │                       │                        │   返回 reply（含 markdown 下载链接）  │
 │                       │                        │◄─────────────────┤                  │
 │                       │  ⑩ append_history       │                                     │
 │                       │     SSE event=agent_done│                                     │
 │   渲染回复 + 下载链接 │                        │                                     │
 │◄──────────────────────│                        │                                     │
```

### 3.3 每一步对应的代码位置

| 步骤 | 关键代码 | 文件:行 |
|---|---|---|
| ① 接收请求、查 session | `chat_stream` 端点、`get_history` | `adapters/server.py:171-221`, `:85-87` |
| ② 构建 system prompt | `_build_system_prompt` | `core/agent.py:136-166` |
| ③ 首轮 LLM 调用 | `_complete` → `stream_complete` | `core/agent.py:200-209`, `core/llm.py:60-64` |
| ④ 流式聚合 tool_calls | `_consume_stream` | `core/agent.py:211-261` |
| ⑤ activate_skill 执行 | `make_activate_skill` | `tools_builtin/skill_ops.py:9-25` |
| ⑥ 第二轮 LLM 调用 | 主循环 `for iteration in range(...)` | `core/agent.py:51-128` |
| ⑦ bash 策略检查 + 执行 | `ToolPolicy._check_bash` → `run_bash` | `core/tools.py:138-162`, `tools_builtin/shell.py:12-58` |
| ⑧ 写文件路径限制 | `write_file` 的 `relative_to` | `tools_builtin/file_ops.py:32-48` |
| ⑨ 终止条件 | `if not msg.tool_calls: return reply` | `core/agent.py:57-60` |
| ⑩ 历史落库 + SSE 完成 | `append_history` + `events.put("agent_done")` | `adapters/server.py:89-96`, `:204-205` |

---

## 四、核心模块逐文件解读

### 4.1 `main.py` — 统一入口

**职责**：解析命令、装配 Agent、把 LLM/skills/tools/policy/rules 拼装到一起。

**关键设计**：

#### 4.1.1 `build_agent(config, provider_override)` — 装配函数（main.py:32-73）
```python
llm = make_llm_from_config(config)
skill_loader = SkillLoader(skills_dir, enabled=enabled).scan()
registry = ToolRegistry(policy=ToolPolicy(config.get("tool_policy", {})))
file_ops.register(registry, workspace_dir=workspace_dir)
shell.register(registry)
skill_ops.register(registry, skill_loader)
return Agent(llm, skill_loader, registry, max_iterations, extra_rules)
```
**为什么这样设计**：
- 所有依赖**显式注入**，没有全局单例。可测试性好，core 不依赖 main。
- `tools_builtin/*.register()` 是把工具往 registry 里"挂"——加新内置工具不用改 Agent，照葫芦画瓢写一个 `xxx_ops.py` 暴露 `register()` 即可。

#### 4.1.2 WebUI 与 CLI 的 extra_rules 分离（main.py:111-123）
```python
def agent_factory(provider: str):
    webui_rules = config.get("webui", {}).get("extra_rules") or []
    merged_config = {
        **config,
        "agent": {
            **(config.get("agent") or {}),
            "extra_rules": [
                *((config.get("agent") or {}).get("extra_rules") or []),
                *webui_rules,
            ],
        },
    }
    return build_agent(merged_config, provider_override=provider)
```
**当时的设计权衡**：
- 像"输出 markdown 下载链接"这种规则**只在 WebUI 有意义**，CLI 里强行让 LLM 输出 `/download/xxx` 反而干扰用户。
- 所以 `agent.extra_rules` 是通用规则，`webui.extra_rules` 是只在 WebUI 时叠加。CLI 走 `cmd_cli` 不会合并 webui 规则。

#### 4.1.3 `_render_rule` 用 replace 不用 format（main.py:131-132）
```python
def _render_rule(rule, workspace_dir: str) -> str:
    return str(rule).replace("{workspace_dir}", workspace_dir.rstrip("/"))
```
**为什么不用 `.format()`**：rules 里包含的 `{` 字符（比如 markdown 链接 `[file](/path)` 里没有，但用户可能写 `{...}` 占位符做注释）会让 `.format()` 抛 `KeyError`。`.replace()` 简单粗暴，符合"极简"。

---

### 4.2 `core/agent.py` — Agent 主循环（无状态）

**职责**：跑 ReAct 循环，仅此而已。

**整体只有 ~150 行有效代码**，是整个项目最小的核心。

#### 4.2.1 无状态契约（agent.py:32-49）
```python
def run(self, user_text, attachments=None, history=None, on_step=None, on_delta=None):
    messages = list(history or [])
    messages.append(self._build_user_message(user_text, attachments))
    steps: List[Dict] = []
```
**为什么无状态**：
- core/Agent 不持有 session、不缓存历史、不感知"上下文管理"。
- 多轮记忆由 **adapter 注入**：CLI 模式不传 history 就是单轮；WebUI 模式 server 维护 sessions dict 然后 `agent.run(..., history=session_history)`。
- 同一个 Agent 实例可以被 N 个并发请求复用（thread-safe，因为没有可变状态）。

#### 4.2.2 ReAct 主循环（agent.py:51-128）
```python
for iteration in range(1, self.max_iterations + 1):
    msg = self._complete(system, messages, tools, on_delta=on_delta)

    if not msg.tool_calls:
        return msg.content or "", steps   # 终止：LLM 不再调工具

    # 否则：执行所有 tool_calls，把结果追加进 messages，进入下一轮
    for tc in msg.tool_calls:
        result = self.tool_registry.execute(tool_name, args)
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": ...})
```
**设计要点**：
- **终止条件唯一**：LLM 不再调用工具。不靠"输出某个特殊 token"或"次数 hardcode"。
- **每轮可以并行多个 tool_calls**：模型一次返回多个 tool_call，全执行后再回 LLM，最大化吞吐。
- **超出 max_iterations 不抛异常**，而是返回"任务未完成 + 最后进展"，让用户/上层有机会接管。
- **ConfirmationRequired 即停**（agent.py:125-128）：只要某个工具返回需要确认，立即把整个循环中断，由 adapter 把"确认请求"暴露给用户，用户点确认后通过 `/api/tool/confirm` 重新触发执行。

#### 4.2.3 system prompt 的极简结构（agent.py:136-166）
```python
return f"""You are an execution agent, not a general chat assistant.

Available tools: {tool_names}.

Tool priority:
1. If a relevant skill exists, call activate_skill(name) first, ...
2. If no skill fits but read/write/bash can solve the task, use the built-in tools.
3. If the task cannot be solved with available tools, say the capability is missing ...

{catalog}    # ← skill 目录（轻量元数据，每条一行）

Rules:
- ...

{extra_rules_block}   # ← 配置注入的业务规则
"""
```
**为什么这样组织**：
- **核心 prompt 极短**（< 500 tokens），把"业务约束"完全交给 `extra_rules`，让一份 Agent 代码能跑不同业务场景。
- **skill 目录是轻量的**（只放 name + description），不灌入每个 SKILL.md 的全文，否则 100 个 skill 直接撑爆 context。

#### 4.2.4 流式聚合（agent.py:211-261）
```python
def _consume_stream(self, stream, on_delta):
    content_parts, reasoning_parts, tool_call_parts = [], [], {}
    for chunk in stream:
        delta = chunk.choices[0].delta
        if text := getattr(delta, "content", None):
            content_parts.append(text)
            on_delta(text)              # ← 实时推前端
        if reasoning := _get_field(delta, "reasoning_content"):
            reasoning_parts.append(reasoning)
        for tc in getattr(delta, "tool_calls", None) or []:
            ...                          # tool_call 增量拼接
    return SimpleNamespace(content=..., reasoning_content=..., tool_calls=...)
```
**踩过的坑**：
- DeepSeek 的 thinking 模式要求多轮请求里**带回 reasoning_content**，否则 400。流式响应里 reasoning 是逐 chunk 来的，必须聚合后回写到 messages。
- `_get_field`（agent.py:269-281）做了三层 fallback：`getattr` → `model_extra` → `dict.get`，兼容 OpenAI SDK 不同版本对自定义字段的暴露方式。

#### 4.2.5 多模态附件（agent.py:168-198）
```python
if not mime.startswith("image/"):
    content.append({"type": "text", "text": f"[附件：name=..., path=..., mime=...]"})
    continue
# 仅图片才转 base64 进 image_url
```
**为什么**：图片走多模态消息直传；其他文件（pdf/xlsx/...）只把**路径**告诉 LLM，让 LLM 决定 activate 哪个 skill 去处理。这避免了"把 100MB 的 PDF base64 塞进 context"的灾难。

---

### 4.3 `core/llm.py` — LLM 抽象层

**职责**：把 OpenAI、Kimi、Qwen、DeepSeek 三家 API 抹平成一个接口。

#### 4.3.1 `PROVIDERS` 注册表（llm.py:14-33）
```python
PROVIDERS = {
    "kimi":     {"base_url": "https://api.moonshot.cn/v1",                  "default_model": "moonshot-v1-128k", "supports_vision": True,  "env_key": "MOONSHOT_API_KEY"},
    "qwen":     {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "default_model": "qwen-vl-max", "supports_vision": True,  "env_key": "DASHSCOPE_API_KEY"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1",                "default_model": "deepseek-v4-pro",  "supports_vision": False, "env_key": "DEEPSEEK_API_KEY"},
}
```
**为什么用 dict 而不是类继承**：每家差异只有 4 个字段，没必要为每家写一个子类。新增 provider 只需要在这里加一行。

#### 4.3.2 视觉降级（llm.py:82-98）
```python
def _strip_images(self, messages):
    # DeepSeek 不支持视觉，把 image_url 替换成文字提示
    ...
    new_parts.append({"type": "text", "text": f"[图片：...（该 provider 不支持视觉，已忽略）]"})
```
**优雅之处**：用户切到 DeepSeek 时不会因为带图片直接 400，而是降级 + 警告日志，agent 还能继续跑。

---

### 4.4 `core/skills.py` — Skill 扫描与懒加载

**职责**：把 `skills/` 目录下的 SKILL.md 元数据抽出来，遵守 [agentskills.io](https://agentskills.io) 规范。

#### 4.4.1 SKILL.md 格式约定
```markdown
---
name: pdf
description: 处理 PDF 文件的读写、合并、拆分、表单填写...
license: MIT
---

# PDF Skill

具体的操作指令、脚本路径、参数说明...
```

#### 4.4.2 双层加载（skills.py:125-147）
```python
def get_catalog_text(self) -> str:
    """给 system prompt 用：仅 name + description"""
    lines = ["Available skills (use activate_skill to load details):"]
    for name, meta in self.catalog.items():
        lines.append(f"  - {name}: {meta.description}")
    return "\n".join(lines)

def load_body(self, name: str) -> str:
    """给 activate_skill 工具用：返回完整正文"""
    skill_file = self.catalog[name].path / "SKILL.md"
    content = skill_file.read_text(...)
    # 去掉 frontmatter，只返回正文
```
**核心设计**：**catalog** 进 system prompt（轻），**body** 通过工具按需取（重）。这才是"100 个 skill 也撑不爆 context"的关键。

#### 4.4.3 严格的 frontmatter 校验（skills.py:90-114）
- name 必须 `^[a-z0-9][a-z0-9-]*[a-z0-9]$`、不超过 64 字符、不允许 `--`
- description 必填、不超过 1024 字符、不允许尖括号

**为什么管这么细**：name 会拼到 `activate_skill` 的参数里，description 会进 system prompt 给 LLM 看；尖括号会被 LLM 当成 XML 标签理解，名称不规范会让模型混淆。

---

### 4.5 `core/tools.py` — 工具注册表 + 策略引擎

**职责**：所有工具的执行边界和返回格式在这里统一。

#### 4.5.1 `ToolResult` 统一返回格式（tools.py:25-56）
```python
@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: Optional[ToolError] = None
    meta: Dict = field(default_factory=dict)
```
**为什么不用裸字符串**：
- LLM 看到 `ok=false` 立刻就知道**不能装作成功**。
- `error.type` 是机器可解析的（`PolicyBlocked` / `ConfirmationRequired` / `CommandFailed` / `ToolNotFound`），让模型在循环里能自己判断"是不是要换思路"。
- `meta` 携带二级信息（policy decision、confirmation token 等），把"用户确认 → 重新执行"的流程闭环。

#### 4.5.2 三态策略：allow / confirm / block（tools.py:113-173）
```python
def check(self, tool_name, args) -> PolicyDecision:
    if tool_name in block_tools: return PolicyDecision.block(...)
    if tool_name in confirm_tools: return PolicyDecision.confirm(...)
    if tool_name == "bash": return self._check_bash(...)
    if tool_name == "write": return self._check_write(...)
    return PolicyDecision.allow()
```
**默认放行哲学**：`config.yaml` 里 `tool_policy.default: allow`，**只对真正高危的命令做 block 或 confirm**：

| 类型 | 命中规则 |
|---|---|
| **block**（高危禁用） | `rm -rf /`、`sudo`、`shutdown`、`mkfs`、`dd if=` |
| **confirm**（中危拍板） | `rm `、`mv `、`chmod `、`chown ` |
| **write confirm** | `.env`、`config.yaml` |
| 其他 | 一律放行 |

**对比传统 Agent 框架**：很多框架默认禁掉一切 shell 命令，反而让 Agent 没法干活。czon Agent 的取舍是"信任用户的本机 + 拦住明确危险的"。

#### 4.5.3 `_looks_like_ambiguous_delete` 智能保护（tools.py:299-315）
```python
def _looks_like_ambiguous_delete(command):
    parts = shlex.split(command)
    if parts[0] != "rm": return False
    targets = [p for p in parts[1:] if not p.startswith("-")]
    for target in targets:
        if target.startswith(("/", "~", "./", "../")) or "/" in target:
            continue
        return True   # ← 类似 `rm aaa.txt` 这种没路径定位的，直接 block
    return False
```
**为什么必要**：LLM 经常看到用户说"删掉 aaa.txt"就直接 `rm aaa.txt`——可问题是它不知道当前 cwd 是什么、aaa.txt 可能匹配多个位置。这个守卫强迫 LLM 先 `find` 或 `ls` 定位到完整路径，再删。

#### 4.5.4 ConfirmationRequired 流程（tools.py:222-238 + server.py:223-247）
```python
# 工具被判定 confirm，第一次返回结构化错误（不是抛异常）
return ToolResult.failure(
    "ConfirmationRequired", reason,
    meta={"confirmation": {"tool_name": ..., "args": ..., "risk_level": ...}}
)

# server.py 把它接住，分配 confirmation_id 推给前端
# 用户点"同意"后，前端调 /api/tool/confirm
agent.tool_registry.execute(tool_name, args, confirmed=True)
```
**优雅之处**：核心 Agent 不感知"是不是 WebUI、是不是要弹确认框"，只返回结构化结果；适配器层把"待确认 → UI → 重新执行"流程闭环。

---

### 4.6 `tools_builtin/` — 内置工具

#### 4.6.1 `file_ops.py:read` —— 读取无路径限制（file_ops.py:12-29）
读任何路径，超过 10000 字符截断，二进制返错。**故意不限制路径**，因为 LLM 经常需要读项目源码、读配置、读 uploads —— 限制反而碍事。

#### 4.6.2 `file_ops.py:write` —— 写入限于 workspace（file_ops.py:32-48）
```python
allowed_dir = Path(workspace_dir).resolve()
p = Path(path).resolve()
try:
    p.relative_to(allowed_dir)
except ValueError:
    return f"[error] 安全限制：write 只能写入 {workspace_dir}/ 目录..."
```
**安全要点**：用 `relative_to()` 而不是字符串前缀匹配，可以防住 `../../etc/passwd` 这类路径穿越。

#### 4.6.3 `shell.py` —— bash 三道防线（shell.py:12-58）
- **超时**：默认 60s，超时返回结构化结果而不是抛异常
- **截断**：stdout/stderr 各最多 10000 字符
- **结构化返回**：包含 `command`/`exit_code`/`stdout`/`stderr`/`timed_out`/`truncated`，让 LLM 在 `exit_code != 0` 时能立刻意识到失败

#### 4.6.4 `skill_ops.py:activate_skill` —— 闭包绑定 skill_loader
```python
def make_activate_skill(skill_loader):
    def activate_skill(name: str) -> str:
        try:
            return skill_loader.load_body(name)
        except KeyError:
            available = ", ".join(skill_loader.catalog.keys())
            return f"[error] skill '{name}' 不存在。可用 skill：{available}"
    return activate_skill
```
**优雅之处**：用工厂函数+闭包绑定 skill_loader 实例，避免在工具签名里暴露 loader。出错时**返回带"可用列表"的错误信息**，LLM 看到错误能立刻自己纠错（而不是死循环）。

---

### 4.7 `adapters/` — 适配器层

#### 4.7.1 `cli.py` —— CLI/REPL（cli.py:38-66）
```python
while True:
    text = console.input("[bold cyan]>>> [/bold cyan]").strip()
    if text in ("exit", "quit", "q"): break
    reply, _ = agent.run(text, on_step=print_step)
    console.print(Panel(Markdown(reply), ...))
```
**特性**：rich 渲染 markdown 输出、`on_step` 回调实时打印每个工具调用、Ctrl+C 优雅退出。

#### 4.7.2 `server.py` —— FastAPI + SSE

**关键端点**：

| 路径 | 方法 | 用途 |
|---|---|---|
| `/api/chat` | POST | 同步对话（非流式） |
| `/api/chat/stream` | POST | SSE 流式对话 |
| `/api/tool/confirm` | POST | 用户确认待批工具 |
| `/api/session/reset` | POST | 清空 session 历史 |
| `/api/upload` | POST | 上传附件 |
| `/api/providers` | GET | 列可用 LLM provider |
| `/download/{path}` | GET | 下载 workspace 文件 |

**SSE 事件设计**（server.py:175-221）：

```python
events.put(("agent_start", {"provider": ..., "text": ...}))
events.put(("assistant_delta", {"text": chunk}))      # 打字机效果
events.put(("tool_result", step_out))                 # 每个工具结果
events.put(("confirmation_required", step_out))       # 待确认
events.put(("agent_done", {"reply": ..., "steps_count": ...}))
events.put(("agent_error", {"error": ...}))
```
前端按事件类型分别渲染，工具执行过程对用户可见，对调试也极其友好。

**Session 历史管理**（server.py:49-96）：
```python
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 80_000

def _trim_history(messages):
    result = list(messages)[-MAX_HISTORY_MESSAGES:]
    while result and _message_chars(result) > MAX_HISTORY_CHARS:
        result.pop(0)
    return result
```
**双重截断**：先按消息条数取末尾 20 条，再按字符总数砍到 80k 以下。**不引入 LLM 做 summarization**，规则简单且可预测。

**Workspace 下载安全**（server.py:270-281）：
```python
target = (workspace_root / file_path).resolve()
try:
    target.relative_to(workspace_root)
except ValueError:
    raise HTTPException(403, detail="不允许访问 workspace 外的文件")
```
同样用 `relative_to` 防路径穿越，配合 LLM 输出的 `/download/xxx` 链接形成完整闭环。

---

### 4.8 `config.yaml` — 配置驱动

```yaml
active_provider: kimi
providers:
  kimi:     { model: moonshot-v1-32k-vision-preview }
  qwen:     { model: qwen-vl-max }
  deepseek: { model: deepseek-v4-pro }

skills:
  dir: ./skills
  enabled: null   # null=全开，可填白名单数组按需启用

workspace: { dir: ./workspace }

agent:
  max_iterations: 15
  extra_rules:
    - "For ambiguous local file names, search likely locations first..."
    - "Use {workspace_dir}/ as the default output directory..."
    - "The user is operating their own local machine..."
    - "For delete/remove requests, prefer moving files to ~/.Trash..."

tool_policy:
  default: allow
  bash:
    blocked_patterns: [...]    # 高危禁用
    confirm_patterns: [...]    # 中危确认
  write:
    confirm_paths: [".env", "config.yaml"]

webui:
  host: 127.0.0.1
  port: 8000
  extra_rules:
    - "When creating or modifying a file under {workspace_dir}/, provide a Markdown download link..."
```

**配置体现的设计哲学**：业务规则、安全策略、provider 选择、skill 白名单**全在配置里**，代码不变就能切环境。

---

## 五、设计取舍亮点（讲解时的重点）

### 5.1 为什么 Agent 是无状态的？

把"是否有上下文"的决策推给 adapter：
- CLI 单次执行 → 不传 history → 单轮
- WebUI 多 tab → 每 tab 一个 session_id → 各自独立的 history
- 未来接 ClawBot/钉钉机器人 → 各自实现 session 存储（Redis/数据库都行），core 一行不改

### 5.2 为什么 skill 用懒加载？

| 方案 | 100 个 skill 的 prompt 大小 |
|---|---|
| 全量灌入 system prompt | ~50,000 tokens（爆掉） |
| **catalog（仅 name+description）** | **~1,500 tokens（轻量）** |
| 单个 skill 完整正文（按需 activate） | ~500-3000 tokens（仅当用到时） |

LLM 自己根据用户问题决定激活哪个 skill，**容量随 skill 数量线性扩展但 context 占用基本恒定**。

### 5.3 为什么 ToolResult 用 JSON 而不是裸字符串？

| 场景 | 裸字符串 | ToolResult JSON |
|---|---|---|
| LLM 判断"是否成功" | 看正则匹配 "error" 字样（不可靠） | 直接看 `ok` 字段 |
| 是否可重试 | 模糊判断 | 看 `error.recoverable` |
| 待确认流程 | 无法表达 | `error.type=ConfirmationRequired` + meta 携带 token |
| 上层适配器分流 | 难 | 按 `error.type` switch 分支 |

### 5.4 为什么 bash 只 confirm 4 个命令？

**反过度安全**。很多 Agent 框架默认禁掉所有 shell，结果 LLM 啥也干不了，最后用户只能关掉安全开关——等于没保护。

czon Agent 的策略：
- **明确高危**（`rm -rf /` 这种）→ 死封
- **中等风险**（普通 rm/mv/chmod/chown）→ 让用户拍板
- **其他**（cat/grep/python/curl/find/...）→ 全放行

外加 `_looks_like_ambiguous_delete` 拦"没路径定位的删除"，覆盖了 90% 的"误删"风险点。

### 5.5 为什么核心代码这么小？

**Agent 框架的复杂度有两种来源**：

1. ❌ **抽象过度**：自创 BaseAgent/AgentExecutor/Chain/Memory/...，10 层继承
2. ✅ **能力丰富**：通过外部 skills/工具/适配器横向扩展

czon Agent 选择了 ②。core/ 五个文件，每个职责极清晰：

| 文件 | 行数 | 职责 |
|---|---:|---|
| `agent.py` | ~290 | ReAct 主循环 + 流式聚合 |
| `llm.py`   | ~115 | LLM 适配 |
| `skills.py`| ~150 | skill 元数据加载 |
| `tools.py` | ~316 | 工具注册表 + 策略引擎 |
| `logging_setup.py` | ~50 | 日志 |

**把"垂直能力"完全外推**到 skills/，把"安全策略"外推到 config，把"交互"外推到 adapters/。core 永远不需要为某个具体业务改动。

---

## 六、可插拔扩展实战

### 6.1 新增一个 skill —— 3 步搞定

**目标**：让 Agent 能处理 markdown 思维导图。

```bash
mkdir -p skills/mindmap
cat > skills/mindmap/SKILL.md <<'EOF'
---
name: mindmap
description: 把 markdown 文档转成 mindmap 思维导图，支持导出 png/svg。处理 .md 输入，调用 markmap-cli 生成可视化。
license: MIT
---

# Mindmap Skill

## 使用方法
1. 准备 markdown 输入文件
2. 调用 bash: `npx markmap-cli <input.md> -o <output.html>`
3. 输出 HTML 包含可交互的思维导图

## 注意事项
- 输出请放到 workspace/ 下
- 如需 png，加 `--no-open` 参数后用 puppeteer 截图
EOF
```

**重启服务**：

```bash
python main.py webui
```

完事。Agent 重新扫描 skills/，**catalog 自动多一行 `mindmap`**，下次用户说"把这文档转成思维导图"，LLM 看到 catalog 就会自己 `activate_skill('mindmap')`。

**全程 0 行 Python 代码改动**。

### 6.2 新增一个 LLM provider

```python
# core/llm.py
PROVIDERS["glm"] = {
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "default_model": "glm-4-plus",
    "supports_vision": True,
    "env_key": "ZHIPU_API_KEY",
}
# 同步给 Literal 加一个 "glm"
```

```bash
# .env
ZHIPU_API_KEY=...
```

```yaml
# config.yaml
active_provider: glm
```

完成。

### 6.3 新增一条业务规则

```yaml
# config.yaml
agent:
  extra_rules:
    - "对所有外发邮件类工具调用，先用 dry_run=True 模拟一遍。"   # ← 新加
```

下次启动即生效。**不动 Python 代码、不动 prompt 模板**。

### 6.4 新增一个内置工具

```python
# tools_builtin/sql.py
def query_db(dsn: str, sql: str) -> dict:
    ...

def register(registry):
    registry.register(name="sql_query", description="...", parameters={...}, handler=query_db)
```

```python
# main.py
from tools_builtin import sql
sql.register(registry)
```

完成。Agent 自动从 registry 拿到新工具的 schema 喂给 LLM。

---

## 七、总结：czon Agent 的"三个不"

> **核心代码不臃肿** —— 五个文件涵盖循环、模型、工具、技能、策略，~600 行。
>
> **业务能力不内置** —— 通过 skills/ 横向扩展垂直场景，不用改一行 Python。
>
> **安全策略不教条** —— 默认放行 + 高危死封 + 中危确认，符合"信任用户、阻挡明确危险"的本机 Agent 哲学。

把它放到一个**类比**里：

> **传统 Agent 框架 ≈ 全家桶笔记本**：什么都装好了，但每加一个新场景就得改框架。
> **czon Agent ≈ ThinkPad + USB 外设**：主机极简，需要什么能力就插什么，主机不用换。

---

## 附：速查清单

| 别人问什么 | 一句话回答 + 文件指引 |
|---|---|
| "它跟 LangChain 比有什么不同？" | 没有 Chain/Memory/Agent 这些抽象层；ReAct 循环就是一个 Python `for` 循环（`core/agent.py:51-128`） |
| "怎么保证不被 LLM 玩坏？" | ToolPolicy 三态判定（`core/tools.py:113-173`） + ToolResult 结构化错误 + workspace 路径限制（`tools_builtin/file_ops.py:32-48`） |
| "支持几家模型？" | OpenAI 兼容协议的都行，目前 Kimi/Qwen/DeepSeek（`core/llm.py:14-33`） |
| "skill 标准是自己定的吗？" | 遵守 [agentskills.io](https://agentskills.io) 的 SKILL.md 规范（`core/skills.py:90-114`） |
| "怎么处理多轮对话？" | core 无状态，adapter 维护 session（`adapters/server.py:78-96`） |
| "支持流式吗？" | SSE 流式 + 工具步骤实时推送（`adapters/server.py:171-221`） |
| "怎么处理超时和长输出？" | bash 60s 超时、stdout/stderr 各 10k 截断（`tools_builtin/shell.py:9-58`） |
| "扩展一个新场景需要多久？" | 写一个 SKILL.md，0 行 Python，几分钟（见 §6.1） |
