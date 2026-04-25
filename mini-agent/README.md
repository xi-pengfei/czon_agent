# Mini Agent

极简 Python Agent Runtime，支持 Kimi / Qwen / DeepSeek，Skills 即插即用。

## 5 分钟快速开始

### 1. 安装依赖

```bash
cd mini-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入至少一个 API Key
# MOONSHOT_API_KEY=sk-...
```

### 3. 初始化示例数据库

```bash
python main.py setup
```

### 4. 启动

**命令行单次执行：**
```bash
python main.py cli "你好，我叫小明"
```

**命令行交互模式：**
```bash
python main.py cli --interactive
```

**WebUI（浏览器）：**
```bash
python main.py webui
# 打开 http://127.0.0.1:8000
```

---

## 目录说明

```
mini-agent/
├── core/           # 核心引擎（LLM、Agent 循环、Skill 加载、工具注册）
├── tools_builtin/  # 4 个内置工具（read / write / bash / activate_skill）
├── skills/         # 可插拔 Skills 目录
├── adapters/       # CLI 和 WebUI 适配器
├── webui/          # 单文件前端（HTML + Tailwind）
├── data/           # 示例 SQLite 数据库
├── uploads/        # 上传文件（运行时）
├── logs/           # 日志文件（运行时）
├── config.yaml     # 主配置
└── main.py         # 统一入口
```

---

## 如何添加新 Skill

1. 在 `skills/` 下创建目录，名称只能含小写字母、数字、连字符（如 `my-skill`）
2. 新建 `SKILL.md`，**必须包含 YAML frontmatter**：

```markdown
---
name: my-skill
description: 一句话说明这个 skill 做什么，以及何时应该用它。
---

# My Skill

## How to use

1. 步骤一…
2. 调用脚本：bash: python skills/my-skill/scripts/run.py
```

3. 在 `scripts/` 目录放你的 Python 脚本
4. 重启 Agent，`activate_skill("my-skill")` 即可加载

**规范要求（agentskills.io 标准）：**
- `name`：最多 64 字符，只能小写字母/数字/连字符
- `description`：最多 1024 字符，不能含 `<` 或 `>`

---

## 切换 LLM

编辑 `config.yaml`：

```yaml
active_provider: qwen   # kimi | qwen | deepseek
```

或在 WebUI 右上角下拉切换（实时生效）。

---

## 内置工具

| 工具 | 说明 |
|------|------|
| `read` | 读取文本文件（最多 10000 字符） |
| `write` | 写文件（限 workspace/、uploads/、logs/ 目录） |
| `bash` | 执行 shell 命令，返回 stdout+stderr |
| `activate_skill` | 按需加载 Skill 完整说明 |
