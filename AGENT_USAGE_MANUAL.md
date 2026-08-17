# 音视频转录 Agent

## 它是什么

这是一个音视频转录整理 Agent，可以把 YouTube、B 站、小宇宙 FM、飞书妙记、音视频文件或音视频直链，自动下载/读取后转成飞书妙记，再生成 Markdown 文件和飞书在线文档。

当前 Agent 名称：`audio-video-transcription-agent`

飞书 Bot 名称：`jetty`

当前 Profile：`C:\Users\bozhu\OneDrive\文档\音视频转录Agent\04-Profile.md`

当前输出群：`我的龙虾团队`

## 省了什么人工

- 之前：人工打开链接，下载音视频，上传飞书，创建妙记，等待转录，复制逐字稿，再整理成文档。一次通常需要 20-60 分钟，长音视频还要反复等待和检查。
- 现在：在飞书里把链接或文件发给 `jetty`，Agent 自动下载、上传、创建妙记、等待逐字稿、生成 Markdown 和飞书文档。人工只需要发送链接或文件。
- 量化：原来约 20-60 分钟人工操作 -> 现在约 10-30 秒发起任务，后续等待系统自动完成。实际转写耗时取决于音视频长度和飞书妙记处理速度。

## 用了什么工具

- Codex：负责开发、维护和排查这个 Agent 的本地桥接代码；配置 Windows 定时任务；检查运行日志；失败时在 Codex 对话里说明原因。
- Hermes：作为 Agent 的运行环境和 Profile 承载层；普通文本问答会尽量按当前 Profile 执行。
- 飞书 CLI：负责连接飞书 Bot、监听消息、发送群消息、下载飞书消息附件、上传云空间、创建飞书妙记、读取逐字稿、创建飞书文档。
- yt-dlp：负责下载 YouTube、B 站、小宇宙 FM 等平台的音视频。
- ffmpeg：负责合并或处理下载到的视频/音频文件，由 `imageio-ffmpeg` 自动提供。

## 输入

- 输入 1：YouTube 视频链接。格式示例：`https://www.youtube.com/watch?v=...`。从 YouTube 页面复制。
- 输入 2：B 站视频链接。格式示例：`https://www.bilibili.com/video/BV...` 或 `https://b23.tv/...`。从 B 站分享页复制。
- 输入 3：小宇宙 FM 单集链接。格式示例：`https://www.xiaoyuzhoufm.com/episode/...`。从小宇宙网页版或分享页复制。
- 输入 4：飞书妙记链接。格式示例：飞书妙记页面 URL。适合已有妙记的内容导出。
- 输入 5：飞书聊天里的音频/视频文件。支持常见格式，例如 `mp3`、`m4a`、`mp4`、`mov` 等。
- 输入 6：音视频直链。URL 本身需要带可识别后缀，例如 `.mp3`、`.m4a`、`.mp4`。

## 如何触发

### 立即处理

在飞书私聊或群聊中，把链接或音视频文件发给 `jetty`。

群里建议写法：

```text
@jetty https://www.xiaoyuzhoufm.com/episode/xxxx
```

私聊里可以直接发：

```text
https://www.bilibili.com/video/BVxxxx
```

注意：`@jetty + 链接` 默认是立即处理，不是加入定时队列。

### 加入每天 9:00 定时队列

在飞书群或私聊中，必须带上定时关键词。

推荐写法：

```text
@jetty 定时处理 https://www.xiaoyuzhoufm.com/episode/xxxx
```

或：

```text
@jetty 加入队列 https://www.bilibili.com/video/BVxxxx
```

当前支持的入队关键词：

- `定时处理`
- `加入队列`
- `加入定时`
- `明天处理`
- `9点处理`
- `九点处理`

每天上午 9:00，Windows 计划任务会运行一次队列：

- 计划任务名：`AudioVideoTranscriptionAgentDailyRun`
- 队列文件：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\scheduled_queue.json`
- 运行日志：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\scheduled-runs.jsonl`
- 结果发送群：`我的龙虾团队`

Codex 每天 09:15 检查一次运行日志。如果 9 点任务失败或没有运行，会在当前 Codex 对话里说明失败原因。

## 输出示例

真实群聊输出示例，来自 `我的龙虾团队`，时间：`2026-08-17 23:39`。

```text
转录完成，已生成干净逐字稿。
Markdown 文件：https://my.feishu.cn/file/DcwSbCAfcoQABNxWE22cUZSDnKf
飞书文档：https://my.feishu.cn/docx/ZwnRdpEhWocCGwxfyvOc0VWsn7e
```

处理过程中还会有中间状态提示，例如：

```text
已收到小宇宙 FM 链接，开始下载音频并生成飞书妙记。下载文件会保留在本机 bridge-downloads 目录。
```

```text
飞书妙记已创建，正在等待逐字稿生成：
https://ncuhbk85k6.feishu.cn/minutes/obcnhn515ux7fwb3g7as748t
```

```text
本机下载文件已保留：C:\Users\bozhu\OneDrive\文档\FeiShuCLI\bridge-downloads\小宇宙-#678.All-In 激辩AI新格局：2万亿美元IPO、扎克伯格AI宣言、英伟达5000亿算力融资 [lu4qvdLwNXEDicnGFGDapsNfIHrq].m4a
```

## 成功运行截图

当前说明书先用真实运行记录替代截图。需要对外展示时，可以在飞书群 `我的龙虾团队` 中截取 `2026-08-17 23:35-23:39` 的消息记录。

真实运行日志：

```text
[2026-08-17 23:35:56] received event=853930da3c2f7fd5b33a96d612e3664a type=text chat=group message=om_x100b6706eb4d14acb183d9b547a1105
[2026-08-17 23:36:03] xiaoyuzhou downloaded message=om_x100b6706eb4d14acb183d9b547a1105 file=小宇宙-#678.All-In 激辩AI新格局：2万亿美元IPO、扎克伯格AI宣言、英伟达5000亿算力融资 [lu4qvdLwNXEDicnGFGDapsNfIHrq].m4a
[2026-08-17 23:36:31] uploaded media source=om_x100b6706eb4d14acb183d9b547a1105 drive_file_token=HKPNbxMBgoa3bmxGacYcMBJan9Z
[2026-08-17 23:36:34] minute created source=om_x100b6706eb4d14acb183d9b547a1105 minute_token=obcnhn515ux7fwb3g7as748t
[2026-08-17 23:39:43] minute transcribed source=om_x100b6706eb4d14acb183d9b547a1105 md_created=yes doc_created=yes
```

定时任务手动测试记录：

```json
{"run_id": "scheduled-20260817-233134", "started_at": "2026-08-17 23:31:34", "finished_at": "2026-08-17 23:31:35", "status": "no_input", "processed": 0, "results": []}
```

## 圈友怎么用

1. 确认飞书里已经能看到 Bot：`jetty`。
2. 如果想立即转写，在飞书私聊或群里发送链接/文件给 `jetty`。
3. 如果想每天 9 点统一处理，发送：`@jetty 定时处理 <链接>`。
4. 等待 Bot 回复处理状态。
5. 任务完成后，打开 Bot 返回的 Markdown 文件链接或飞书文档链接。
6. 如果链接无法处理，先看 Bot 返回的失败原因，再决定是否更换链接、提供文件、授权访问或改用飞书妙记链接。

一个完整例子：

```text
@jetty 定时处理 https://www.xiaoyuzhoufm.com/episode/6a82806517676351c572fc2e
```

每天 9 点后，Agent 会自动处理队列，并把结果发到 `我的龙虾团队`。

## 注意事项

- 它不能绕过平台访问控制，不能处理未授权的私密、付费、需要密码或邀请码的内容。
- YouTube 如果触发真人验证，可能需要换代理出口，或在明确授权后使用浏览器 cookies。
- B 站下载偶尔会遇到 SSL EOF，当前代码已增加重试和降级处理，但仍可能受网络和代理影响。
- 小宇宙 FM 通常可以由 `yt-dlp` 解析音频，但如果节目下架或链接失效会失败。
- 飞书 user 授权会过期。若上传云空间、创建妙记或创建文档失败，需要重新授权飞书 user 身份。
- 直接发 `@jetty + 链接` 是立即处理；要进定时队列，必须写 `定时处理` 或 `加入队列`。
- 目前定时队列只处理已加入队列的链接，不会主动扫描群聊历史里的普通链接。
- 当前输出默认发到 `我的龙虾团队`。如果要换群，需要修改 `scheduled_config.json` 里的 `output_chat_id` 和 `output_chat_name`。
- 当前生成的是逐字稿 Markdown 和飞书文档。Profile 中提到的“分享式提纯稿”能力还需要后续进一步接入整理步骤；当前稳定主流程是音视频转写和文档交付。
- 本地下载文件会保留在 `bridge-downloads/`，需要定期清理磁盘空间。
- 不要把 `.hermes-bind/`、API key、飞书密钥、二维码、运行日志或临时音视频提交到 GitHub。

## 维护入口

常用文件：

- 主程序：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\feishu_hermes_bridge.py`
- 启动脚本：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\start_feishu_hermes_bridge.ps1`
- 停止脚本：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\stop_feishu_hermes_bridge.ps1`
- 定时入口：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\scheduled_run.py`
- 定时配置：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\scheduled_config.json`
- 运行日志：`C:\Users\bozhu\OneDrive\文档\FeiShuCLI\scheduled-runs.jsonl`

常用维护命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_feishu_hermes_bridge.ps1
powershell -ExecutionPolicy Bypass -File .\stop_feishu_hermes_bridge.ps1
python scheduled_run.py
```
