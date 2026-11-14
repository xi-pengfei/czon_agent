# 手机访问、录音和播报

手机访问 `http://192.168.0.35:8000` 是局域网 HTTP，不是手机自己的 localhost。
文字聊天、输入法听写后发送、音频播放可以使用 HTTP；网页麦克风需要受信任的 HTTPS 和麦克风授权。
不需要打包 App，也不需要把服务或录音改成公网托管。截图是应用内浏览器，建议先在 iPhone Safari 中测试。

## 当前 Mac + 同一 Wi-Fi 的 iPhone：本地证书

下面操作会安装本地证书工具和信任根证书。只在自己的测试设备上安装；多人正式使用建议由管理员配置域名和受信任证书。

在 Mac 终端执行（IP 若变化需替换并重新生成证书）：

```sh
cd /Users/pengfei/Desktop/czon_agent
brew install mkcert
mkcert -install
mkdir -p certs
mkcert -cert-file certs/lan.pem -key-file certs/lan-key.pem 192.168.0.35 localhost 127.0.0.1 ::1
chmod 600 certs/lan-key.pem
open "$(mkcert -CAROOT)"
```

最后一步打开证书文件夹。用隔空投送把 **rootCA.pem** 发到自己的 iPhone，安装描述文件，然后在“设置 → 通用 → 关于本机 → 证书信任设置”中开启该根证书的完全信任。
只传根证书 `rootCA.pem`，不要传 `rootCA-key.pem` 或 `lan-key.pem` 私钥。iOS 版本不同，描述文件安装入口可能在“通用 → VPN 与设备管理”。

在项目 `config.yaml` **现有的 `webui:` 下**增加两项，不要另建第二个 webui 段：

```yaml
webui:
  host: "0.0.0.0"
  port: 8000
  ssl_certfile: "certs/lan.pem"
  ssl_keyfile: "certs/lan-key.pem"
  # 保留原有 session_db、runs 等其他配置
```

`ssl_certfile` 是服务器出示的证书；`ssl_keyfile` 是服务器私钥。相对路径以项目目录为准；证书放在被 Git 忽略的 certs/ 目录，不是语音 API 密钥。

等待当前任务结束，停止旧服务，再以原来的命令启动：

```sh
.venv/bin/python main.py webui
```

手机 Safari 打开 **https://192.168.0.35:8000**；此时旧 HTTP 地址不再可用。确认没有证书警告，再登录并点击麦克风，允许录音。电脑也改用 HTTPS 访问。HTTPS 直连会自动使用 Secure 登录 Cookie。
如仍有证书警告，检查证书是否包含当前 IP，以及手机是否已安装并完全信任根证书，不能靠跳过警告解决麦克风权限。

本次代码只添加 HTTPS 启动支持，没有在本机安装根证书、生成证书或切换正在运行的服务。

## 手机没有声音时

1. 在新对话点击右上角喇叭，默认保持静音，不会强制手机播放。
2. 点击出现的“试听声音”。它走相同的 TTS 服务和播放器，不执行业务任务。
3. 开启声音后，文字输入和手机键盘听写发送都应触发播报；输入方式不决定是否播放。
4. 如果页面提示“声音已暂停”，点击“恢复声音”。发送消息时也会尝试恢复被听写暂停的音频通道。
5. 如果仍听不到，检查媒体音量、静音模式、蓝牙输出，并用 Safari 单独打开同一地址再试。应用内浏览器存在额外限制，HTTPS 不会自动解除播放限制。
6. TTS 服务失败会显示错误，任务继续执行。HTTP 麦克风限制与 TTS 失败是两个不同问题。

参考：[浏览器麦克风权限](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)、[iOS 音频中断](https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/state)、[mkcert 手机证书说明](https://github.com/FiloSottile/mkcert#mobile-devices)。
