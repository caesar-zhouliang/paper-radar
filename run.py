#!/usr/bin/env python3
"""Paper Radar 每日流水线：抓取 → 打分 → 翻译 → 生成站点 → 推送。

用法：
    python run.py                      # 正常跑今天
    python run.py --days 3             # 回看 3 天
    python run.py --no-translate       # 不翻译（省 token）
    python run.py --offline            # 用本地缓存数据重建站点（改样式时用）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from psradar import arxiv_client, notify, ranker, renderer, translator
from psradar.config import CACHE_DIR, DATA_DIR, load_config

HISTORY_DIR = DATA_DIR / "history"
DAYS_FILE = DATA_DIR / "days.json"
ARCHIVE_LIMIT = 30   # 重新生成多少天的历史页面
KEEP_DAYS = 120      # 历史 JSON 保留天数


def _load_days() -> list[dict]:
    if DAYS_FILE.exists():
        try:
            return json.loads(DAYS_FILE.read_text("utf-8"))
        except Exception:
            return []
    return []


def _save_days(days: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DAYS_FILE.write_text(json.dumps(days, ensure_ascii=False, indent=1), "utf-8")


def _save_history(date_str: str, papers: list[dict]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_DIR / f"{date_str}.json").write_text(
        json.dumps(papers, ensure_ascii=False), "utf-8"
    )


def _load_archive(days: list[dict]) -> dict[str, list[dict]]:
    out = {}
    for d in days[:ARCHIVE_LIMIT]:
        path = HISTORY_DIR / f"{d['date']}.json"
        if path.exists():
            try:
                out[d["date"]] = json.loads(path.read_text("utf-8"))
            except Exception:
                continue
    return out


def _prune() -> None:
    if not HISTORY_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    for f in HISTORY_DIR.glob("*.json"):
        try:
            if datetime.strptime(f.stem, "%Y-%m-%d") < cutoff:
                f.unlink()
        except ValueError:
            continue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="回看天数")
    ap.add_argument("--date", default=None, help="把结果标记为某一天（补跑用）")
    ap.add_argument("--no-translate", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--offline", action="store_true", help="跳过抓取，用已有 history 重建站点")
    args = ap.parse_args()

    cfg = load_config()
    tz = ZoneInfo(cfg.nav("site.timezone", "Asia/Shanghai") or "Asia/Shanghai")
    date_str = args.date or datetime.now(tz).strftime("%Y-%m-%d")
    fetch_days = args.days or int(cfg.nav("fetch.days", 2))
    max_papers = int(cfg.nav("site.max_papers", 700))

    print(f"=== Paper Radar {date_str} ===")

    if args.offline:
        path = HISTORY_DIR / f"{date_str}.json"
        if not path.exists():
            print(f"没有 {date_str} 的历史数据，无法离线重建")
            return 1
        papers = json.loads(path.read_text("utf-8"))
    else:
        print("[1/5] 抓取 arXiv …")
        raw = arxiv_client.fetch_recent(
            cfg.nav("fetch.categories", ["cs.CV", "cs.LG", "cs.RO"]),
            days=fetch_days,
            page_size=int(cfg.nav("fetch.page_size", 200)),
            max_docs=int(cfg.nav("fetch.max_docs", 3000)),
            interval=float(cfg.nav("fetch.request_interval", 3.2)),
        )
        if not raw:
            print("没抓到论文，退出")
            return 1

        print("[2/5] 方向匹配 + 打分 …")
        papers = ranker.rank(raw, cfg)
        print(f"  · 与方向相关 {len(papers)} 篇")

        # 超出上限时优先保留精选
        papers.sort(key=lambda p: (not p["pick"], -p["score"]))
        papers = papers[:max_papers]

        print("[3/5] 中文翻译 …")
        if args.no_translate:
            print("  · 已跳过")
        else:
            translator.translate_papers(papers, cfg, CACHE_DIR)

        _save_history(date_str, papers)

    if not args.offline:
        print("[4/5] 生成站点 …")
    else:
        print("[1/3] 生成站点 …")

    days = _load_days()
    days = [d for d in days if d["date"] != date_str]
    days.insert(0, {"date": date_str, "path": f"day/{date_str}.html", "count": len(papers)})
    days.sort(key=lambda d: d["date"], reverse=True)
    _save_days(days)

    archive = _load_archive(days)
    renderer.build_site(cfg, papers, date_str, days, archive)
    renderer.build_feed(cfg, papers, date_str)
    print(f"  · 站点已生成：{renderer.SITE_DIR}")

    if not args.no_notify:
        print("[5/5] 推送 …")
        notify.notify_all(cfg, papers, date_str)

    _prune()
    picks = sum(1 for p in papers if p.get("pick"))
    print(f"✅ 完成：{len(papers)} 篇，精选 {picks} 篇，历史 {len(days)} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
