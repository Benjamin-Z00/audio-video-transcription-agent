# 音视频转录 Agent 桥接服务

这个目录保存飞书 bot 与 Hermes Agent 的本地桥接代码。服务监听飞书消息，并支持：

- 普通文本消息转发给 Hermes Agent 回复
- 飞书私聊/群聊中的音视频附件转飞书妙记
- 读取妙记逐字稿并创建飞书文档
- 飞书妙记链接导出为干净逐字稿 Markdown 文件并上传到飞书云空间
- YouTube 链接通过 `yt-dlp` 下载完整视频后转飞书妙记，并保留到 `bridge-downloads/`

## 主要文件

- `feishu_hermes_bridge.py`：主程序
- `start_feishu_hermes_bridge.ps1`：启动服务
- `stop_feishu_hermes_bridge.ps1`：停止服务
- `.gitignore`：排除密钥、日志、临时音视频、二维码等本地文件

## 本机依赖

- Python 3
- `lark-cli`
- NemoHermes / Hermes 本地运行时
- `yt-dlp`：用于处理 YouTube 链接

安装 yt-dlp：

```powershell
python -m pip install --user yt-dlp
```

桥接代码调用 `python -m yt_dlp`，不依赖 `yt-dlp.exe` 是否在 PATH 中。`ffmpeg` 由 `imageio-ffmpeg` 提供，桥接会自动传给 yt-dlp 用于合并视频。

## 飞书授权

当前流程需要两种身份：

- bot 身份：监听飞书消息、发送结果消息、下载消息附件
- user 身份：上传文件到飞书云空间、创建妙记、读取逐字稿、创建飞书文档

不要提交 `.hermes-bind/`、日志、二维码、临时音视频文件或任何 API key。

## YouTube 链接说明

服务默认用 `yt-dlp` 下载最佳音频，并通过 `YTDLP_PROXY` 指定代理。未设置时默认使用：

```text
http://127.0.0.1:7897
```

如果 YouTube 返回 “Sign in to confirm you’re not a bot”，说明该链接需要浏览器 cookies。出于隐私原因，默认不会读取浏览器 cookies；需要单独确认后再启用。

## 启停

```powershell
powershell -ExecutionPolicy Bypass -File .\start_feishu_hermes_bridge.ps1
powershell -ExecutionPolicy Bypass -File .\stop_feishu_hermes_bridge.ps1
```



## 最终输出规则

无论输入是：

- YouTube 视频链接
- 普通音频/视频直链
- 飞书聊天里的本地音频附件
- 飞书聊天里的本地视频附件
- 飞书妙记链接

最终都只输出干净的逐字稿正文，并保存为 Markdown 文件上传到飞书云空间；同时创建一份飞书在线文档。输出中不包含摘要、总结、标题、来源、Speaker 或时间戳。
