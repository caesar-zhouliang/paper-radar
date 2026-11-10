"""静态站生成：index.html / day/*.html / data/*.json / feed.xml / days.json"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ROOT, SITE_DIR


def _read(path: Path) -> str:
    return path.read_text("utf-8")


def _slim(p: dict) -> dict:
    """只保留前端要用的字段，减小页面体积。"""
    return {
        "id": p["id"],
        "title": p["title"],
        "title_zh": p.get("title_zh", ""),
        "abstract": p.get("abstract", ""),
        "abstract_zh": p.get("abstract_zh", ""),
        "authors": p.get("authors", [])[:12],
        "published_date": p.get("published_date", ""),
        "abs_url": p.get("abs_url", ""),
        "pdf_url": p.get("pdf_url", ""),
        "code": p.get("code", ""),
        "comment": p.get("comment", ""),
        "topics": p.get("topics", []),
        "primary_topic": p.get("primary_topic", ""),
        "score": p.get("score", 0),
        "pick": bool(p.get("pick")),
    }


def _page(cfg, papers: list[dict], date_str: str, generated: str, days: list[dict],
          root: str, tpl: str, css: str, js: str) -> str:
    site = cfg.get("site", {})
    topics = [{"id": t["id"], "name": t["name"], "color": t.get("color", "#888")} for t in cfg.get("topics", [])]
    payload = {
        "date": date_str,
        "generated": generated,
        "topics": topics,
        "days": days,
        "papers": [_slim(p) for p in papers],
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    options = "".join(
        f'<option value="{root}{d["path"]}"{" selected" if d["date"] == date_str else ""}>{d["date"]}（{d["count"]}篇）</option>'
        for d in days
    )
    label = "今日精选" if days and days[0]["date"] == date_str else f"{date_str} 论文"
    title = f"{site.get('title','Paper Radar')} · {date_str}"

    html = tpl
    for key, val in {
        "__TITLE__": escape(title),
        "__SUBTITLE__": escape(site.get("subtitle", "")),
        "__HEADLINE__": escape(label),
        "__STAMP__": escape(f"{date_str} · 共 {len(papers)} 篇"),
        "__DAY_OPTIONS__": options,
        "__ROOT__": root,
        "__DATA__": data_json,
        "__CSS__": css,
        "__JS__": js,
    }.items():
        html = html.replace(key, val)
    return html


def build_site(cfg, papers: list[dict], date_str: str, days: list[dict], extra_days: dict[str, list[dict]] | None = None) -> Path:
    """生成整个站点。extra_days: {date: [papers]} 用于回填历史页面。"""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "day").mkdir(exist_ok=True)
    (SITE_DIR / "data").mkdir(exist_ok=True)

    tpl = _read(ROOT / "templates" / "page.html")
    css = _read(ROOT / "assets" / "style.css")
    js = _read(ROOT / "assets" / "app.js")
    tz = ZoneInfo(cfg.nav("site.timezone", "Asia/Shanghai") or "Asia/Shanghai")
    generated = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    # 历史页
    for d, ps in (extra_days or {}).items():
        if d == date_str:
            continue
        html = _page(cfg, ps, d, generated, days, "../", tpl, css, js)
        (SITE_DIR / "day" / f"{d}.html").write_text(html, "utf-8")

    # 首页 = 最新一天
    index = _page(cfg, papers, date_str, generated, days, "", tpl, css, js)
    (SITE_DIR / "index.html").write_text(index, "utf-8")
    (SITE_DIR / "day" / f"{date_str}.html").write_text(
        _page(cfg, papers, date_str, generated, days, "../", tpl, css, js), "utf-8"
    )

    # 数据接口
    (SITE_DIR / "data" / f"{date_str}.json").write_text(
        json.dumps({"date": date_str, "papers": [_slim(p) for p in papers]}, ensure_ascii=False, indent=1), "utf-8"
    )
    (SITE_DIR / "data" / "latest.json").write_text(
        json.dumps({"date": date_str, "papers": [_slim(p) for p in papers]}, ensure_ascii=False, indent=1), "utf-8"
    )
    (SITE_DIR / "days.json").write_text(json.dumps(days, ensure_ascii=False, indent=1), "utf-8")
    (SITE_DIR / ".nojekyll").write_text("", "utf-8")
    return SITE_DIR


def build_feed(cfg, papers: list[dict], date_str: str) -> Path:
    site = cfg.get("site", {})
    base = (site.get("base_url") or "").rstrip("/")
    tz = ZoneInfo(site.get("timezone", "Asia/Shanghai"))
    now = datetime.now(tz)
    picks = [p for p in papers if p.get("pick")][:20] or papers[:20]

    items = []
    for p in picks:
        desc = p.get("abstract_zh") or p.get("abstract") or ""
        items.append(
            "<item>"
            f"<title>{escape(p.get('title_zh') or p['title'])}</title>"
            f"<link>{escape(p['abs_url'])}</link>"
            f'<guid isPermaLink="false">paper-radar-{escape(p["id"])}</guid>'
            f"<pubDate>{now.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
            f"<description>{escape(desc[:1200])}</description>"
            "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{escape(site.get('title', 'Paper Radar'))} · {date_str}</title>"
        f"<link>{escape(base)}</link>"
        f"<description>{escape(site.get('subtitle', ''))}</description>"
        f"<language>zh-cn</language><lastBuildDate>{now.strftime('%a, %d %b %Y %H:%M:%S %z')}</lastBuildDate>"
        + "".join(items)
        + "</channel></rss>"
    )
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    path = SITE_DIR / "feed.xml"
    path.write_text(xml, "utf-8")
    return path
