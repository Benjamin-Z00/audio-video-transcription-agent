import base64
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / "feishu-hermes-bridge.log"
TEMP_DIR = ROOT / "bridge-temp"

LARK_CLI = r"C:\Users\bozhu\.trae-cn\plugins\trae-remote-official\lark\1.0.3\bin\lark-cli.exe"
HERMES_HOME = str(ROOT / ".hermes-bind")
SANDBOX = "audio-video-transcription-agent"
MODEL = os.environ.get("HERMES_MODEL", "deepseek/deepseek-v4-flash")
HERMES_API = os.environ.get("HERMES_API", "http://127.0.0.1:8642/v1/chat/completions")
STT_PROVIDER = os.environ.get("HERMES_STT_PROVIDER", "openrouter").lower()
STT_API_URL = os.environ.get("HERMES_STT_API_URL", "https://openrouter.ai/api/v1/audio/transcriptions")
STT_MODEL = os.environ.get("HERMES_STT_MODEL", "openai/whisper-1")
YTDLP_PROXY = os.environ.get("YTDLP_PROXY", "http://127.0.0.1:7897")

MEDIA_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".wma", ".amr", ".avi", ".wmv", ".mov", ".mp4", ".m4v", ".mpeg", ".flv"}
YOUTUBE_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\s]+|youtu\.be/[^\s]+)", re.I)
MINUTE_URL_RE = re.compile(r"https?://[^\s]+/minutes/(obcn[a-zA-Z0-9]+)", re.I)
FILE_RE = re.compile(r'<file\s+key="([^"]+)"\s+name="([^"]+)"\s*/?>')


def log(message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def base_env() -> dict:
    env = os.environ.copy()
    env["HTTP_PROXY"] = ""
    env["HTTPS_PROXY"] = ""
    env["ALL_PROXY"] = ""
    env["HERMES_HOME"] = HERMES_HOME
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    return env


def hermes_token() -> str:
    cmd = [
        "wsl", "-d", "Ubuntu", "--", "env",
        "PATH=/home/benjamin/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "/home/benjamin/.local/bin/nemohermes", SANDBOX, "gateway-token", "--quiet",
    ]
    token = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    if not token:
        raise RuntimeError("Hermes gateway token is empty")
    return token


def ask_hermes(content: str, sender_id: str, chat_type: str) -> str:
    token = hermes_token()
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are an audio/video transcription agent. Reply in Chinese, concise and practical."},
            {"role": "user", "content": f"Feishu {chat_type} message, sender={sender_id}: {content}"},
        ],
        "max_tokens": 500,
    }
    req = urllib.request.Request(
        HERMES_API,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Hermes HTTP {exc.code}: {body[:500]}") from exc
    text = (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Hermes returned empty content")
    return text


def run_lark(args: list[str], timeout: int = 60, input_text: str | None = None) -> dict:
    result = subprocess.run(
        [LARK_CLI, *args],
        env=base_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        capture_output=True,
        timeout=timeout,
        cwd=str(ROOT),
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    raw = stdout.strip() or stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(raw)
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"lark-cli returned non-json output: {raw[:300]}") from exc


def idempotency_key(prefix: str, event_id: str, suffix: str = "") -> str:
    digest = hashlib.sha1(f"{event_id}:{suffix}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def reply(message_id: str, text: str, event_id: str, suffix: str = "") -> None:
    run_lark([
        "im", "+messages-reply", "--as", "bot", "--message-id", message_id,
        "--text", text, "--idempotency-key", idempotency_key("hb-r", event_id, suffix),
    ], timeout=30)

def send_chat(chat_id: str, text: str, event_id: str, suffix: str = "") -> None:
    run_lark([
        "im", "+messages-send", "--as", "bot", "--chat-id", chat_id,
        "--text", text, "--idempotency-key", idempotency_key("hb-c", event_id, suffix),
    ], timeout=30)
def get_message_content(message_id: str) -> str:
    data = run_lark(["im", "+messages-mget", "--as", "bot", "--message-ids", message_id, "--format", "json"], timeout=30)
    messages = ((data.get("data") or {}).get("messages") or [])
    return (messages[0].get("content") or "") if messages else ""


def parse_file_message(message_id: str) -> tuple[str, str]:
    detail = get_message_content(message_id)
    match = FILE_RE.search(detail)
    if not match:
        raise RuntimeError("未能从文件消息中解析 file_key")
    return match.group(1), match.group(2)


def safe_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned or fallback


def download_message_file(message_id: str, file_key: str, name: str) -> Path:
    TEMP_DIR.mkdir(exist_ok=True)
    ext = Path(name).suffix.lower() or ".bin"
    rel = f"bridge-temp/{message_id}{ext}"
    data = run_lark([
        "im", "+messages-resources-download", "--as", "bot", "--message-id", message_id,
        "--file-key", file_key, "--type", "file", "--output", rel, "--format", "json",
    ], timeout=180)
    saved = ((data.get("data") or {}).get("saved_path") or str(ROOT / rel))
    return Path(saved)


def stt_api_key() -> str:
    key = os.environ.get("HERMES_STT_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("缺少云端转录 API key。请设置 HERMES_STT_API_KEY 或 OPENROUTER_API_KEY 后重启 bridge。")
    return key


def openrouter_transcribe(file_path: Path) -> str:
    boundary = "----HermesBridge" + hashlib.sha1(f"{file_path}:{time.time()}".encode("utf-8")).hexdigest()
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{STT_MODEL}\r\n".encode("utf-8"),
        (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8"),
        file_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    req = urllib.request.Request(
        STT_API_URL,
        data=b"".join(chunks),
        headers={
            "Authorization": f"Bearer {stt_api_key()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "HTTP-Referer": "https://www.nvidia.com/nemoclaw/",
            "X-Title": "Feishu Hermes Transcription Agent",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"OpenRouter 转录失败 HTTP {exc.code}: {msg[:500]}") from exc
    text = (data.get("text") or data.get("transcription") or "").strip()
    if not text:
        raise RuntimeError("OpenRouter 转录返回为空")
    return text

def markdown_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("<", "\\<")


def clean_transcript_text(transcript: str) -> str:
    lines = []
    skip_keywords = False
    for raw in transcript.splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\w+\|", line):
            continue
        if line == "Keywords:":
            skip_keywords = True
            continue
        if skip_keywords:
            skip_keywords = False
            continue
        if re.match(r"^Speaker\s+\S+\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s*$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}(?:\.\d+)?\s*$", line):
            continue
        lines.append(line)
    text = "\n\n".join(part for part in "\n".join(lines).split("\n\n") if part.strip())
    return text.strip()



def create_transcript_doc(original_name: str, transcript: str, message_id: str, minute_url: str = "") -> str:
    title = f"逐字稿 - {original_name}"
    content = clean_transcript_text(transcript) + "\n"
    data = run_lark([
        "docs", "+create", "--as", "user", "--doc-format", "markdown",
        "--title", title, "--content", "-", "--format", "json",
    ], timeout=120, input_text=content)
    document = ((data.get("data") or {}).get("document") or {})
    url = document.get("url") or ""
    if not url:
        raise RuntimeError(f"文档创建成功但未返回 URL: {json.dumps(data, ensure_ascii=False)[:500]}")
    return url


def drive_upload_media(file_path: Path, name: str) -> tuple[str, str]:
    rel = file_path.relative_to(ROOT).as_posix()
    data = run_lark([
        "drive", "+upload", "--as", "user", "--file", rel,
        "--name", name, "--format", "json",
    ], timeout=240)
    info = data.get("data") or {}
    token = info.get("file_token") or ""
    url = info.get("url") or ""
    if not token:
        raise RuntimeError(f"音视频上传云空间成功但未返回 file_token: {json.dumps(data, ensure_ascii=False)[:500]}")
    return token, url


def create_minute(file_token: str) -> tuple[str, str]:
    data = run_lark([
        "minutes", "+upload", "--as", "user", "--file-token", file_token, "--format", "json",
    ], timeout=120)
    info = data.get("data") or {}
    token = info.get("minute_token") or ""
    url = info.get("minute_url") or ""
    if not token or not url:
        raise RuntimeError(f"妙记创建成功但未返回链接: {json.dumps(data, ensure_ascii=False)[:500]}")
    return token, url


def fetch_minute_transcript(minute_token: str) -> tuple[str, Path | None]:
    out_dir = "bridge-minutes"
    data = run_lark([
        "minutes", "+detail", "--as", "user", "--minute-tokens", minute_token,
        "--wait-ready", "--summary", "--transcript", "--output-dir", out_dir,
        "--overwrite", "--format", "json",
    ], timeout=600)
    minutes = ((data.get("data") or {}).get("minutes") or [])
    artifacts = ((minutes[0] if minutes else {}).get("artifacts") or {})
    transcript_file = artifacts.get("transcript_file") or ""
    if not transcript_file:
        raise RuntimeError(f"妙记已创建但未返回逐字稿文件: {json.dumps(data, ensure_ascii=False)[:500]}")
    transcript_path = ROOT / transcript_file
    transcript = transcript_path.read_text(encoding="utf-8").strip()
    if not transcript:
        raise RuntimeError("妙记逐字稿为空")
    return transcript, transcript_path



def fetch_minute_artifacts(minute_token: str) -> tuple[str, str, str, Path | None]:
    out_dir = "bridge-minutes"
    data = run_lark([
        "minutes", "+detail", "--as", "user", "--minute-tokens", minute_token,
        "--wait-ready", "--summary", "--transcript", "--output-dir", out_dir,
        "--overwrite", "--format", "json",
    ], timeout=600)
    minutes = ((data.get("data") or {}).get("minutes") or [])
    minute = minutes[0] if minutes else {}
    title = minute.get("title") or minute_token
    artifacts = minute.get("artifacts") or {}
    summary = artifacts.get("summary") or ""
    transcript_file = artifacts.get("transcript_file") or ""
    if not transcript_file:
        raise RuntimeError(f"妙记已创建但未返回逐字稿文件: {json.dumps(data, ensure_ascii=False)[:500]}")
    transcript_path = ROOT / transcript_file
    transcript = transcript_path.read_text(encoding="utf-8").strip()
    if not transcript:
        raise RuntimeError("妙记逐字稿为空")
    return title, summary, transcript, transcript_path


def build_transcript_markdown(title: str, source_id: str, minute_url: str, summary: str, transcript: str) -> str:
    return clean_transcript_text(transcript) + "\n"


def upload_markdown_file(title: str, content: str, source_id: str) -> str:
    TEMP_DIR.mkdir(exist_ok=True)
    digest = hashlib.sha1(source_id.encode("utf-8")).hexdigest()[:12]
    filename = safe_filename(f"转录结果 - {title}-{digest}.md", f"transcript-{digest}.md")
    path = TEMP_DIR / filename
    path.write_text(content, encoding="utf-8")
    try:
        rel = path.relative_to(ROOT).as_posix()
        data = run_lark([
            "drive", "+upload", "--as", "user", "--file", rel,
            "--name", filename, "--format", "json",
        ], timeout=180)
        info = data.get("data") or {}
        url = info.get("url") or ""
        if not url:
            raise RuntimeError(f"Markdown 上传成功但未返回 URL: {json.dumps(data, ensure_ascii=False)[:500]}")
        return url
    finally:
        try:
            if path.exists():
                path.unlink()
        except Exception as exc:
            log(f"failed to delete temp markdown file={path}: {exc}")


def handle_minute_link_message(content: str, message_id: str, chat_id: str, event_id: str) -> bool:
    match = MINUTE_URL_RE.search(content)
    if not match:
        return False
    minute_token = match.group(1)
    minute_url = match.group(0)
    transcript_path: Path | None = None
    send_chat(chat_id, f"已收到飞书妙记链接，开始读取逐字稿并生成 Markdown 文件：\n{minute_url}", event_id, "-min-start")
    try:
        title, summary, transcript, transcript_path = fetch_minute_artifacts(minute_token)
        markdown = build_transcript_markdown(title, message_id, minute_url, summary, transcript)
        md_url = upload_markdown_file(title, markdown, message_id)
        doc_url = create_transcript_doc(title, transcript, message_id, minute_url)
        send_chat(chat_id, f"已生成转录结果。\nMarkdown 文件：{md_url}\n飞书文档：{doc_url}", event_id, "-min-done")
        log(f"minute link exported message={message_id} minute_token={minute_token}")
    finally:
        cleanup_generated_transcript(transcript_path)
    return True


def cleanup_generated_transcript(path: Path | None) -> None:
    if not path:
        return
    try:
        if path.exists():
            path.unlink()
        parent = path.parent
        while parent != ROOT and parent.name in {"bridge-minutes", path.parent.name}:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    except Exception as exc:
        log(f"failed to delete generated transcript file={path}: {exc}")


def process_local_media(local_path: Path, name: str, source_id: str, chat_id: str, event_id: str) -> None:
    transcript_path: Path | None = None
    try:
        size = local_path.stat().st_size
        log(f"media ready source={source_id} file={safe_filename(name, source_id)} size={size}")

        file_token, drive_url = drive_upload_media(local_path, name)
        log(f"uploaded media source={source_id} drive_file_token={file_token}")

        minute_token, minute_url = create_minute(file_token)
        send_chat(chat_id, f"飞书妙记已创建，正在等待逐字稿生成：\n{minute_url}", event_id, "-minute")
        log(f"minute created source={source_id} minute_token={minute_token}")

        transcript, transcript_path = fetch_minute_transcript(minute_token)
        doc_url = create_transcript_doc(name, transcript, source_id, minute_url)
        send_chat(chat_id, f"转录完成。\n妙记：{minute_url}\n逐字稿文档：{doc_url}", event_id, "-done")
        log(f"minute transcribed source={source_id} doc_created=yes")
    finally:
        cleanup_generated_transcript(transcript_path)


def handle_file_message(message_id: str, chat_id: str, event_id: str) -> None:
    file_key, name = parse_file_message(message_id)
    ext = Path(name).suffix.lower()
    if ext not in MEDIA_EXTS:
        send_chat(chat_id, f"我收到文件：{name}。它不是当前支持的音视频格式。", event_id)
        return

    local_path: Path | None = None
    send_chat(chat_id, f"已收到音视频文件：{name}\n开始生成飞书妙记，完成后会把逐字稿保存到飞书文档，并删除本地临时文件。", event_id, "-start")
    try:
        local_path = download_message_file(message_id, file_key, name)
        log(f"downloaded message={message_id} file={safe_filename(name, message_id)}")
        process_local_media(local_path, name, message_id, chat_id, event_id)
    finally:
        if local_path and local_path.exists():
            try:
                local_path.unlink()
                log(f"deleted temp media message={message_id}")
            except Exception as exc:
                log(f"failed to delete temp media message={message_id}: {exc}")


def download_youtube_audio(url: str, event_id: str) -> tuple[Path, str]:
    TEMP_DIR.mkdir(exist_ok=True)
    digest = hashlib.sha1(f"{event_id}:{url}".encode("utf-8")).hexdigest()[:12]
    output_template = str(TEMP_DIR / f"yt-{digest}.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "--windows-filenames",
        "-f", "bestaudio/best",
        "-o", output_template,
        url,
    ]
    if YTDLP_PROXY:
        cmd[3:3] = ["--proxy", YTDLP_PROXY]
    result = subprocess.run(
        cmd, cwd=str(ROOT), text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=1800,
    )
    if result.returncode != 0:
        raw = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"yt-dlp 下载失败：{raw[:700]}")
    matches = sorted(TEMP_DIR.glob(f"yt-{digest}.*"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError("yt-dlp 下载完成但未找到输出文件")
    media_path = matches[0]
    title = media_path.name
    return media_path, title


def handle_youtube_message(content: str, message_id: str, chat_id: str, event_id: str) -> bool:
    match = YOUTUBE_RE.search(content)
    if not match:
        return False
    url = match.group(0)
    local_path: Path | None = None
    send_chat(chat_id, "已收到视频链接，开始用 yt-dlp 临时下载音频并生成飞书妙记。", event_id, "-yt-start")
    try:
        local_path, name = download_youtube_audio(url, event_id)
        log(f"yt-dlp downloaded message={message_id} file={local_path.name}")
        process_local_media(local_path, name, message_id, chat_id, event_id)
    finally:
        if local_path and local_path.exists():
            try:
                local_path.unlink()
                log(f"deleted temp youtube media message={message_id}")
            except Exception as exc:
                log(f"failed to delete temp youtube media message={message_id}: {exc}")
    return True


def consume() -> subprocess.Popen:
    return subprocess.Popen(
        [LARK_CLI, "event", "consume", "im.message.receive_v1", "--as", "bot"],
        env=base_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )


def main() -> int:
    LOG_PATH.write_text("", encoding="utf-8")
    log("starting Feishu -> Hermes bridge")
    proc = consume()
    assert proc.stdout is not None and proc.stderr is not None

    while True:
        err_line = proc.stderr.readline()
        if not err_line:
            break
        log("event stderr: " + err_line.rstrip())
        if "[event] ready" in err_line:
            break

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            event_id = event.get("event_id") or str(int(time.time() * 1000))
            message_id = event["message_id"]
            content = (event.get("content") or "").strip()
            message_type = event.get("message_type")
            chat_id = event.get("chat_id", "")
            sender_id = event.get("sender_id", "")
            chat_type = event.get("chat_type", "")
            log(f"received event={event_id} type={message_type} chat={chat_type} message={message_id}")

            if message_type in ("file", "audio", "media", "video"):
                handle_file_message(message_id, chat_id, event_id)
                continue

            if message_type != "text" or not content:
                reply(message_id, "我目前可以处理文本消息和音视频文件。这个消息类型暂不支持。", event_id)
                continue

            if handle_minute_link_message(content, message_id, chat_id, event_id):
                continue

            if handle_youtube_message(content, message_id, chat_id, event_id):
                continue

            answer = ask_hermes(content, sender_id, chat_type)
            reply(message_id, answer, event_id)
            log(f"replied event={event_id} message={message_id}")
        except Exception as exc:
            log(f"error handling event: {exc}")
            try:
                if "chat_id" in locals() and chat_id and "event_id" in locals():
                    send_chat(chat_id, f"处理失败：{exc}", event_id, "-error")
            except Exception as reply_exc:
                log(f"error reply failed: {reply_exc}")

    code = proc.poll()
    log(f"event consumer exited code={code}")
    return 1 if code not in (None, 0) else 0


if __name__ == "__main__":
    sys.exit(main())



