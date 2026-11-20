# 2026.11.20.1 发布说明

网页侧栏底部显示发布版本，展开可查看 Git 提交号和安装时间。命令行使用 `python main.py --version`，无需读取业务配置或访问数据库。正式安装由 `.release.json` 记录提交号、安装时间及程序文件校验值；运行时保存启动时的版本信息。数据库、配置和技能与主程序版本分开管理。

本次同时收录移动端显式 LAN 模式的登录/会话恢复修复，以及通过构建环境指定默认服务地址的功能。发布源码不固定个人测试域名；`EXPO_PUBLIC_CZON_SERVER` 或 `CZON_DEFAULT_SERVER` 可设置默认地址。未设置则由用户输入。配置接口参考 https://docs.expo.dev/versions/v58.0.0/sdk/constants/ 和 https://docs.expo.dev/guides/environment-variables/ 。

## Linux 升级约束

固定 Git 提交构建，运行测试后才可发布。代码升级范围为 core、adapters、tools_builtin、webui、main.py、requirements.txt、VERSION；前端构建产物整套切换。不要整目录覆盖项目，不把开发机数据库、.env、配置、skills、workspace、uploads、日志或虚拟环境复制到客户机器。

先创建客户备份和独立 Linux 依赖环境；数据库用 SQLite backup API 创建一致性副本，先在副本上验证结构升级与用户/模型/权限/会话保留。停机切换前再次备份数据库；没有正在执行业务任务时再停服务。客户 config.yaml 保留原值，必要的新字段单独审查，不能用开发配置整体替换。

正式切换保留旧程序和旧依赖。先验证服务登录入口、静态资源、权限接口、数据库完整性和技能文件校验；失败则停止新版并恢复旧程序及升级前数据库，再启动旧版。回滚恢复数据库会回退新启动后的数据，因此切换验收期间不应开展真实业务。升级过程中不重新执行历史任务、不提交金蝶单据。

`.release.json` 为本机部署元数据，不提交 Git。构建来源必须是明确的已提交版本，元数据的 revision 使用完整 commit ID；不能用客户项目残留的旧 Git HEAD 冒充新安装版本。发布版本更新时同时更新 VERSION，并打同名 v 前缀 Git 标签。
