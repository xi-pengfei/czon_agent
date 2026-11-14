# CzON Agent 移动端

独立的 React Native + Expo 原生应用，复用 Python/FastAPI 服务。不是 WebView，也不替换现有 React WebUI。iOS 优先，Android 共用代码但尚未真机验证。

## 首版范围

- 服务地址、账号登录，凭据保存在系统 SecureStore（iOS Keychain）；不保存密码。
- 初始密码修改、简体中文 / 繁体中文 / English 界面。
- 最近任务、新任务、模型与技能选择、Markdown 回答、文件上传及成果分享。
- 多会话独立运行、SSE 流式输出、断线及回前台恢复；继续沿用服务器的并发上限。
- 原生麦克风录音，结束后上传 ASR，文字可编辑再发送。不是逐字实时 ASR。
- 点击已完成回答旁的扬声器，生成并播放服务端语音摘要；默认不自动播报。
- 业务写入确认仍须用户点击确认；不自动跳过后端权限。

手机进入后台时关闭订阅和录音/播放，服务器任务继续运行；回到前台重新读取快照再订阅。iOS 不保证 App 在后台持续执行 JavaScript，因此不依赖后台 JS 保活任务。

## 运行后端

先使用包含移动端登录接口的新代码启动后端。在项目根目录执行：

```sh
.venv/bin/python main.py webui
```

已有旧服务时，在任务结束后停止旧进程再启动。App 使用同一账号、模型权限和技能权限；不把 ASR/TTS 或模型密钥放入 App。语音继续使用后端 `.env` 的语音服务配置。

## 本机 iOS 开发

当前 Expo SDK 58 要求 **Xcode 26.4 或以上**。安装前必须核对 macOS 兼容性及磁盘空间；例如 Xcode 26.4.1 要求 macOS 26.2 或以上。打开 Xcode 完成组件安装，并在 Xcode → Settings → Accounts 登录 Apple 开发者账号。只有 Command Line Tools 无法编译/运行 iOS。

2026-11-14 实机检查：macOS 15.7.3、可用空间约 3.7 GiB，目前不满足本地构建准备条件。不能直接按下面命令完成安装；需要先解决系统及空间，或使用下方 EAS 云构建。系统升级、个人文件清理和云构建账号关联均尚未执行。

```sh
cd czon_agent/mobile
npm ci
CZON_MOBILE_LAN=1 npx expo prebuild --platform ios --no-install
CZON_MOBILE_LAN=1 DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer npm run ios -- --device
```

这会生成 `ios/` 并编译安装原生开发版。连接 iPhone、信任此电脑，并在 iPhone 上启用开发者模式；首次签名需要选择你的开发团队。Bundle ID 默认 `cn.czon.agent.mobile`，若签名冲突可在构建时设置 `CZON_IOS_BUNDLE_ID` 为你自己的唯一标识。重新使用不同原生配置时先执行对应环境变量下的 `npx expo prebuild --platform ios`。

之后启动 JS 开发服务：

```sh
npm start
```

手机与电脑使用同一 Wi-Fi。在登录页填写**后端地址**（例如 `http://192.168.0.35:8000`，以电脑当前 IP 为准），不是 Metro 的 8081 地址，也不是手机自己的 localhost。

原生录音通过系统麦克风权限，不受浏览器 getUserMedia 的 HTTPS 限制。HTTP 局域网只用于开发：`CZON_MOBILE_LAN=1` 为原生开发包添加 ATS 例外，客户端仍只接受局域网 HTTP；正式发行包只接受 HTTPS。不要在不可信 Wi-Fi 上使用 HTTP 登录。

## 云构建 / TestFlight

`eas.json` 已提供 development / simulator / production 配置。不在仓库里存放 Apple 证书或密码。

```sh
npx eas-cli login
npx eas-cli build:configure
npx eas-cli build --platform ios --profile development
# 正式 HTTPS 服务就绪后：
npx eas-cli build --platform ios --profile production
```

EAS 首次关联项目和签名需要你的 Expo / Apple 账号操作；本次没有创建云项目、上传构建或发布 App Store。开发包分发需要登记设备，TestFlight 使用正式构建。Apple 开发者账号本身不能替代本机的 Xcode。

## 验证

```sh
npm run lint
npm run typecheck
npm test
npm run export:ios
# 仓库根目录：
.venv/bin/python -m unittest tests.test_mobile_auth tests.test_server_security
```

`export:ios` 验证原生 JS/资源打包，不等于签名 IPA，也不等于真机验收。真机还需验证：小屏/横屏、键盘遮挡、系统大字体、录音权限拒绝/恢复、耳机与扬声器、弱网重连、上传分享、确认业务操作，以及后台→前台和多会话切换。

## 与现有系统的边界

- 后端新增 `/api/auth/mobile/login`；凭据仍来自原有会话表，密码修改/禁用/注销沿用原有机制。
- Bearer 请求仍要求 `X-CSRF-Token`；Web Cookie 登录保持兼容，不在 Web 登录 JSON 中暴露凭据。
- 原有 WebUI、小智 MCP 和技能格式不变。界面翻译文件在 `src/strings.ts`，不会翻译用户名字、技能 Display Name 或业务回答。
- 暂未实现推送通知、锁屏播报、实时 ASR、离线任务、移动管理后台。原有女性头像以静态资源保留，表情动画留待原生真机验收后接入。

## 本次验证记录（2026-11-14）

- 后端认证、安全、任务并发/重连以及原生 Bearer 同等接口回归：65 项通过（临时数据库，不调用真实业务）。
- 移动端协议与 Markdown 检查：5 项通过；TypeScript 与 iOS JavaScript/资源导出通过。
- iOS 原生工程预生成通过；检查了录音权限、开发版局域网与正式版 ATS 配置。
- Markdown 解析器、Expo fingerprint 与 ESLint 解析器的依赖已显式覆盖至修复版本，并检查解析兼容性。`npm audit` 当次检查无已知漏洞。
- 当前机器仅有 Command Line Tools，缺少完整 Xcode。因此没有编译签名 IPA，也没有进行模拟器或真机视觉/录音验收。

实现依据：[Expo 58 原生录音](https://docs.expo.dev/versions/v58.0.0/sdk/audio/)、[SecureStore](https://docs.expo.dev/versions/v58.0.0/sdk/securestore/)、[文件操作](https://docs.expo.dev/versions/v58.0.0/sdk/filesystem/)。App 图标由现有 WebUI 的蓝底 C 标志转换而来，聊天头像保留现有女性形象。

## 服务器地址与构建位置

App 首次启动不预填本机地址，成功登录后记住该服务地址。后端可以在本机或自有云服务器；云端使用 HTTPS，且须部署包含 `/api/auth/mobile/login` 的版本。填错地址可在登录页修改；已登录则从设置退出后更换地址重新登录。服务不可达时也可在退出尝试超时后退出本机。切换服务不会迁移原服务的账号、任务和文件。EAS 云构建只负责生成安装包，不会把业务后端自动迁入 EAS。

环境依据：[Expo 58 支持版本](https://docs.expo.dev/versions/v58.0.0/)、[Apple Xcode 系统要求](https://developer.apple.com/xcode/system-requirements)。
