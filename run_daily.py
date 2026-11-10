#!/usr/bin/env python3
"""08:30 daily orchestration for Paper Radar.

Steps:
1. Run the existing fetch/rank/translate/site pipeline.
2. Generate summary-only briefs for today's picks.
3. Build the site readers and brief pages.
4. Commit/push data and readers to GitHub Pages.
5. Send the summary brief to Feishu.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from psradar import brief, notify, reader_agent
from psradar.config import DATA_DIR, load_config


def _run(cmd: list[str], cwd: Path) -> int:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _summaries(papers: list[dict], date_str: str) -> None:
    """Ensure every picked paper has a compact summary field."""
    # One full reader per day; the site keeps the translation and the brief
    # gets its generated 基础摘要.
    generated = {}
    for paper in reader_agent.choose(papers, limit=2):
        result = reader_agent.generate(paper, date_str, reader_limit=2)
        if result:
            generated[paper["id"]] = result.get("summary", "")
    for paper in papers:
        if not paper.get("pick"):
            continue
        current = paper.get("brief_zh") or {}
        if current.get("summary"):
            continue
        text = generated.get(paper["id"]) or (paper.get("abstract_zh") or paper.get("abstract") or "").strip()
        if text:
            text = " ".join(text.split())
            if len(text) > 420:
                text = text[:417].rstrip() + "…"
            current["summary"] = text
            paper["brief_zh"] = current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--no-feishu", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    root = Path(__file__).resolve().parent
    tz = ZoneInfo(cfg.nav("site.timezone", "Asia/Shanghai"))
    date_str = args.date or datetime.now(tz).strftime("%Y-%m-%d")

    cmd = [sys.executable, str(root / "run.py"), "--date", date_str, "--no-notify"]
    if args.offline:
        cmd.append("--offline")
    code = _run(cmd, root)
    if code != 0:
        return code

    history = DATA_DIR / "history" / f"{date_str}.json"
    papers = json.loads(history.read_text("utf-8"))
    _summaries(papers, date_str)
    history.write_text(json.dumps(papers, ensure_ascii=False), "utf-8")

    # Rebuild after adding summaries so the site and brief reflect them.
    renderer_cmd = [sys.executable, str(root / "run.py"), "--date", date_str, "--offline", "--no-notify"]
    code = _run(renderer_cmd, root)
    if code != 0:
        return code

    if not args.no_push:
        _run(["git", "add", "data"], root)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode != 0:
            _run(["git", "commit", "-m", f"chore: daily briefing {date_str}"], root)
            _run(["git", "push", "origin", "main"], root)

    if not args.no_feishu:
        notify.notify_all(cfg, papers, date_str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
