#!/usr/bin/env python3
"""Paper Radar daily orchestration.

04:30 prepare: fetch, rank, translate all abstracts, generate two readers,
              build the site, and push it to GitHub Pages.
08:30 send:    validate the prepared brief and deliver it once to Feishu.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from psradar import brief, reader_agent, summaries, zh
from psradar.config import DATA_DIR, load_config

ROOT = Path(__file__).resolve().parent
PREPARED_DIR = DATA_DIR / "prepared"
SENT_DIR = DATA_DIR / "sent"


def _run(cmd: list[str], cwd: Path) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _save_history(date_str: str, papers: list[dict]) -> None:
    path = DATA_DIR / "history" / f"{date_str}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(papers, ensure_ascii=False), "utf-8")


def _git_publish(date_str: str) -> bool:
    if _run(["git", "pull", "--rebase", "--autostash", "origin", "main"], ROOT) != 0:
        return False
    _run(["git", "add", "data"], ROOT)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        if _run(["git", "commit", "-m", f"chore: daily briefing {date_str}"], ROOT) != 0:
            return False
    return _run(["git", "push", "origin", "main"], ROOT) == 0


def prepare(date_str: str, *, offline: bool, push: bool) -> int:
    marker = PREPARED_DIR / f"{date_str}.json"
    if marker.exists():
        print(f"  · {date_str} 已完成预处理，06:00 重试任务跳过", flush=True)
        return 0

    cmd = [sys.executable, str(ROOT / "run.py"), "--date", date_str, "--no-notify"]
    if offline:
        cmd.append("--offline")
    if _run(cmd, ROOT) != 0:
        history = DATA_DIR / "history" / f"{date_str}.json"
        if not history.exists():
            return 1
        print("  ! 在线抓取失败，继续使用已有当天数据", flush=True)

    history = DATA_DIR / "history" / f"{date_str}.json"
    papers = json.loads(history.read_text("utf-8"))

    missing = zh.ensure(papers)
    if missing:
        print(f"  · 中文摘要补全 {missing} 篇", flush=True)
        _save_history(date_str, papers)

    summaries.ensure(papers)
    _save_history(date_str, papers)

    generated = 0
    for paper in reader_agent.choose(papers, limit=2):
        result = reader_agent.generate(paper, date_str, reader_limit=2)
        if result:
            generated += 1
            if result.get("summary") and not (paper.get("brief_zh") or {}).get("summary"):
                item = paper.get("brief_zh") or {}
                item["summary"] = result["summary"]
                paper["brief_zh"] = item
        _save_history(date_str, papers)
    print(f"  · 中文精读完成 {generated} 篇", flush=True)

    summaries.ensure(papers)
    _save_history(date_str, papers)

    if _run([sys.executable, str(ROOT / "run.py"), "--date", date_str, "--offline", "--no-notify"], ROOT) != 0:
        return 1

    if push and not _git_publish(date_str):
        return 1

    PREPARED_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({
        "date": date_str,
        "prepared_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "papers": len(papers),
        "picks": sum(1 for p in papers if p.get("pick")),
        "readers": generated,
    }, ensure_ascii=False, indent=1), "utf-8")
    print(f"  ✅ 预处理完成：{len(papers)} 篇，精读 {generated} 篇；08:30 将发送飞书", flush=True)
    return 0


def send(date_str: str) -> int:
    SENT_DIR.mkdir(parents=True, exist_ok=True)
    sent_marker = SENT_DIR / f"{date_str}.json"
    if sent_marker.exists():
        print(f"  · {date_str} 飞书已发送，跳过重复投递", flush=True)
        return 0

    history = DATA_DIR / "history" / f"{date_str}.json"
    if not history.exists():
        print(f"  ! 缺少 {date_str} 数据，无法发送", flush=True)
        return 1
    papers = json.loads(history.read_text("utf-8"))
    picks = [p for p in papers if p.get("pick")]
    if not picks:
        print("  ! 今日没有精选论文，无法发送", flush=True)
        return 1
    if any(not (p.get("brief_zh") or {}).get("summary") for p in picks):
        print("  ! 仍有精选论文缺少中文摘要，08:30 暂不发送", flush=True)
        return 1

    cfg = load_config()
    brief.send(cfg, papers, date_str)
    sent_marker.write_text(json.dumps({
        "date": date_str,
        "sent_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "picks": len(picks),
    }, ensure_ascii=False, indent=1), "utf-8")
    print(f"  ✅ 飞书已发送：{len(picks)} 篇精选", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    tz = ZoneInfo(cfg.nav("site.timezone", "Asia/Shanghai"))
    date_str = args.date or datetime.now(tz).strftime("%Y-%m-%d")

    if args.prepare and not args.send:
        return prepare(date_str, offline=args.offline, push=not args.no_push)
    if args.send and not args.prepare:
        return send(date_str)
    code = prepare(date_str, offline=args.offline, push=not args.no_push)
    if code != 0:
        return code
    return send(date_str)


if __name__ == "__main__":
    raise SystemExit(main())
