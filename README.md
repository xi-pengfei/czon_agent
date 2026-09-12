# czon_agent

面向企业内部使用的精简 Python AI 智能体。应用自身提供登录、角色权限、历史会话、模型管理、Skills、工具策略、附件、实时输出和主动停止；WebUI 使用 React、TypeScript 和 Vite，生产运行仍只有 Python/FastAPI 服务。

## 首次启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py setup-admin
python main.py webui
```

Mac 本机访问 `http://127.0.0.1:8000`；同一局域网访问 `http://Mac的局域网IP:8000`。首次管理员登录必须修改初始密码。

登录后由系统管理员在“模型配置”页面添加模型和 API Key。模型密钥加密保存在本地数据库，不再从 `.env` 读取。

以后启动命令不变：

```bash
source .venv/bin/activate
python main.py webui
```

也支持 CLI：

```bash
python main.py
python main.py "帮我列出 workspace 下的文件"
```

## 配置边界

`config.yaml` 只保留机器和运行时配置：

- `active_provider`：CLI 默认模型。
- `skills`、`workspace`：目录和全局 Skill 开关。
- `agent`：总运行时间、连续异常、模型连接/读取/写入超时和有限重试。
- `tool_policy`：底层工具安全策略。
- `webui.host`、`webui.port`：监听地址和端口。
- `webui.session_db`：用户、权限、模型、审计和会话数据库。
- `webui.cookie_secure`：全站 HTTPS 时设为 `true`，HTTP 直连时为 `false`。

`.env` 只保存 PledgeBox、数据库、金蝶等业务系统凭据。模型清单、连接信息和 API Key 全部以数据库为唯一管理来源，主智能体和业务 Skill 使用同一个模型解析入口。

## 用户与管理

管理员登录后访问独立管理页面：

- 用户：创建、启停、分配部门和角色，设置用户月 Token 额度并重置临时密码。
- 组织：维护任意层级部门和部门默认月 Token 额度。
- 角色：通过搜索多选限制 Skills、`read`、`write`、`bash`、`activate_skill` 和模型。
- 模型：管理 OpenAI 兼容接口、模型名、多模态/工具/流式能力，测试连接并读取模型列表。
- 日志：分别查看用户、角色和模型管理审计，以及脱敏后的运行日志。

模型 API Key 只能在管理页面填写。Key 使用 `data/czon_agent.key` 加密后保存，页面只显示“已配置”，编辑时不会返回旧值。

## 会话与执行

- 历史会话保存在 `data/czon_agent.db`，普通用户只能访问自己的会话。
- 登录使用浏览器会话 Cookie，30 分钟无操作或登录满 8 小时后失效。
- 输入 `/` 可选择当前角色允许的 Skill，后端仍会再次校验权限。
- 模型回答和 shell 进度通过 SSE 实时显示。
- 新生成的成果文件绑定到用户和会话，回答下方可直接下载；其他账号不能访问。
- 回答保存运行时间和真实 Token 用量，管理页面按百万 Token（`M`）展示月额度。
- WebUI 停止会终止对应子进程组；CLI 使用 `Ctrl+C`。
- 正常任务不按固定轮数中断，仍保留总时间、断连和连续异常保护。

## 部署方式

应用可直接提供完整 WebUI，也可以选择在 Ubuntu 前面增加 Nginx，用于标准端口、HTTPS 和反向代理。应用自身的登录负责用户、角色和数据权限，默认不再叠加 Nginx Basic Auth。部署步骤见 [Ubuntu 部署指南](DEPLOY_UBUNTU.md) 和 [Windows 部署指南](DEPLOY_WINDOWS.md)。

Ubuntu 和 Windows 均支持在线一键安装：引导脚本会自动从 GitHub 下载最新版；客户现场不能访问 GitHub 时，仍可使用 ZIP 离线安装。

下载 ZIP 并解压后，Windows 用户双击根目录的 `INSTALL_WINDOWS.cmd`；Ubuntu 用户在根目录执行 `bash INSTALL_UBUNTU.sh`。底层安装脚本位于 `deploy/`，普通用户不需要直接操作。

## 项目结构

```text
czon_agent/
├── adapters/       # CLI 和 FastAPI
├── core/           # Agent、认证、会话、LLM、Skills、工具策略
├── data/           # SQLite 数据
├── deploy/         # 可选 Nginx 与 systemd 模板
├── frontend/       # React + TypeScript 源码
├── skills/         # 业务 Skills
├── tools_builtin/  # read、write、bash、activate_skill
├── uploads/        # WebUI 上传文件
├── webui/          # Vite 生成的生产静态文件
├── workspace/      # 企业共享工作区
├── config.yaml
└── main.py
```

向量库、Qdrant、embedding、演示数据库和演示 Skills 已从系统移除。

## 验证

```bash
python -m unittest discover -s tests -v
cd frontend
npm ci
npm run build
```

Node.js 只在修改前端和重新构建时使用。生产服务器直接使用已经生成的 `webui/`，无需运行 Node 服务。`data/czon_agent.db`、`data/czon_agent.key` 和 `data/artifacts/` 必须一起备份；丢失 Key 文件后，网页中保存的模型密钥无法恢复。

当前 `workspace` 是 Agent 执行时的共享工作区，但网页成果下载使用按用户隔离的不可变副本。正式生产建议通过 Nginx 配置 HTTPS。
