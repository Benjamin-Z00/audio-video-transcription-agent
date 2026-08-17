import json
import sys
import time
import traceback
from pathlib import Path

import feishu_hermes_bridge as bridge

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "scheduled_config.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def append_run_log(record: dict) -> None:
    bridge.SCHEDULED_RUN_LOG_PATH.open("a", encoding="utf-8").write(
        json.dumps(record, ensure_ascii=False) + "\n"
    )


def process_entry(entry: dict, output_chat_id: str, run_id: str, index: int) -> dict:
    url = entry["url"]
    source_id = entry.get("source_message_id") or f"scheduled-{entry['id']}"
    event_id = f"{run_id}-{index}-{entry['id']}"
    before = time.time()
    handled = False

    if bridge.handle_minute_link_message(url, source_id, output_chat_id, event_id):
        handled = True
    elif bridge.handle_youtube_message(url, source_id, output_chat_id, event_id):
        handled = True
    elif bridge.handle_xiaoyuzhou_message(url, source_id, output_chat_id, event_id):
        handled = True
    elif bridge.handle_bilibili_message(url, source_id, output_chat_id, event_id):
        handled = True
    elif bridge.handle_media_url_message(url, source_id, output_chat_id, event_id):
        handled = True

    if not handled:
        raise RuntimeError(f"unsupported scheduled URL: {url}")
    return {"id": entry["id"], "url": url, "status": "success", "duration_seconds": round(time.time() - before, 2)}


def main() -> int:
    config = load_config()
    output_chat_id = config["output_chat_id"]
    run_id = "scheduled-" + time.strftime("%Y%m%d-%H%M%S")
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    queue = bridge.load_scheduled_queue()
    pending = [item for item in queue if item.get("status") == "pending"]
    results = []
    overall_status = "success"

    bridge.send_chat(output_chat_id, f"定时转写任务开始：{started_at}\n待处理链接：{len(pending)}", run_id, "-start")

    if not pending:
        record = {"run_id": run_id, "started_at": started_at, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"), "status": "no_input", "processed": 0, "results": []}
        append_run_log(record)
        bridge.send_chat(output_chat_id, "定时转写任务完成：今天没有待处理链接。", run_id, "-no-input")
        return 0

    by_id = {item["id"]: item for item in queue}
    for index, entry in enumerate(pending, start=1):
        try:
            result = process_entry(entry, output_chat_id, run_id, index)
            by_id[entry["id"]]["status"] = "done"
            by_id[entry["id"]]["processed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            results.append(result)
        except Exception as exc:
            overall_status = "failed"
            error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            by_id[entry["id"]]["status"] = "failed"
            by_id[entry["id"]]["failed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            by_id[entry["id"]]["error"] = error
            results.append({"id": entry["id"], "url": entry.get("url"), "status": "failed", "error": error})
            bridge.send_chat(output_chat_id, f"定时转写失败：{entry.get('url')}\n原因：{error}", run_id, f"-failed-{index}")

    bridge.save_scheduled_queue(list(by_id.values()))
    record = {"run_id": run_id, "started_at": started_at, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"), "status": overall_status, "processed": len(pending), "results": results}
    append_run_log(record)
    bridge.send_chat(output_chat_id, f"定时转写任务结束：{overall_status}\n处理数量：{len(pending)}", run_id, "-done")
    return 0 if overall_status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
