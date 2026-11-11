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
        "title_zh": p.get("title_zh") or p.get("title", ""),
        "abstract": p.get("abstract", ""),
        "abstract_zh": p.get("abstract_zh") or "（中文摘要待生成）",
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
        "source": p.get("source") or "arXiv",
        "sources": p.get("sources") or ["arXiv"],
        "reader_url": p.get("reader_url", ""),
        "brief_zh": p.get("brief_zh", {}),
    }


def _page(cfg, papers: list[dict], date_str: str, generated: str, days: list[dict],
          brief_days: list[dict], root: str, tpl: str, css: str, js: str) -> str:
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
    brief_options = "".join(
        f'<option value="{root}brief/{d["date"]}.html"{" selected" if d["date"] == date_str else ""}>{d["date"]}（{d["picks"]}篇推送）</option>'
        for d in brief_days
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
        "__BRIEF_OPTIONS__": brief_options,
        "__ROOT__": root,
        "__DATA__": data_json,
        "__CSS__": css,
        "__JS__": js,
        "__DATE__": date_str,
    }.items():
        html = html.replace(key, val)
    return html


def _brief_picks(papers: list[dict]) -> list[dict]:
    picks = [p for p in papers if p.get("pick")]
    picks.sort(key=lambda p: -int(p.get("score", 0)))
    return picks[:10]


def _has_brief(papers: list[dict]) -> bool:
    return any((p.get("brief_zh") or {}).get("summary") for p in _brief_picks(papers))


def build_site(cfg, papers: list[dict], date_str: str, days: list[dict], extra_days: dict[str, list[dict]] | None = None) -> Path:
    """生成整个站点。extra_days: {date: [papers]} 用于回填历史页面。"""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "day").mkdir(exist_ok=True)
    (SITE_DIR / "data").mkdir(exist_ok=True)
    mathjax_src = ROOT / "assets" / "mathjax"
    if mathjax_src.exists():
        shutil.copytree(mathjax_src, SITE_DIR / "assets" / "mathjax", dirs_exist_ok=True)

    tpl = _read(ROOT / "templates" / "page.html")
    css = _read(ROOT / "assets" / "style.css")
    js = _read(ROOT / "assets" / "app.js")
    tz = ZoneInfo(cfg.nav("site.timezone", "Asia/Shanghai") or "Asia/Shanghai")
    generated = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    by_date = dict(extra_days or {})
    by_date[date_str] = papers
    brief_days = [
        {"date": d["date"], "picks": len(_brief_picks(by_date.get(d["date"], [])))}
        for d in days
        if _has_brief(by_date.get(d["date"], []))
    ]

    # Readers and brief must be built before pages because they attach
    # reader_url to today's papers and generate the linked brief page.
    _build_readers(cfg, papers)
    _build_brief(cfg, papers, date_str, brief_days)
    for day, old_papers in (extra_days or {}).items():
        if day != date_str and _has_brief(old_papers):
            _build_brief(cfg, old_papers, day, brief_days)
    _build_brief_index(cfg, brief_days, by_date, generated)

    # 历史页
    for d, ps in (extra_days or {}).items():
        if d == date_str:
            continue
        html = _page(cfg, ps, d, generated, days, brief_days, "../", tpl, css, js)
        (SITE_DIR / "day" / f"{d}.html").write_text(html, "utf-8")

    # 首页 = 最新一天
    index = _page(cfg, papers, date_str, generated, days, brief_days, "", tpl, css, js)
    (SITE_DIR / "index.html").write_text(index, "utf-8")
    (SITE_DIR / "day" / f"{date_str}.html").write_text(
        _page(cfg, papers, date_str, generated, days, brief_days, "../", tpl, css, js), "utf-8"
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


def _build_readers(cfg, papers: list[dict]) -> None:
    """Publish pre-generated Chinese readers and attach their URLs to papers."""
    readers_root = ROOT / "data" / "readers"
    if not readers_root.exists():
        return
    from .reader import build as build_reader
    by_id = {p["id"]: p for p in papers}
    for source in readers_root.iterdir():
        if not source.is_dir():
            continue
        paper = by_id.get(source.name)
        if not paper:
            # Keep readers for older papers available even if today's JSON
            # does not include that record.
            paper = {"id": source.name, "title": source.name, "title_zh": "", "abstract": "",
                     "authors": [], "published_date": "", "categories": [], "primary_topic": "",
                     "abs_url": "https://arxiv.org/abs/" + source.name,
                     "pdf_url": "https://arxiv.org/pdf/" + source.name}
        markdown = source / "translation.md"
        if markdown.exists():
            build_reader(SITE_DIR, paper, markdown, source)
        target = SITE_DIR / "readers" / paper["id"]
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
                shutil.copy2(item, target / item.name)
        paper["reader_url"] = "readers/" + paper["id"] + "/index.html"


def _build_brief(cfg, papers: list[dict], date_str: str, brief_days: list[dict] | None = None) -> None:
    picks = _brief_picks(papers)
    cards = []
    for paper in picks:
        brief = paper.get("brief_zh") or {}
        title = paper.get("title_zh") or paper["title"]
        sections = []
        for key, label in (("summary", "摘要"), ("method", "实验方法"), ("driving", "对自动驾驶方案的帮助")):
            text = brief.get(key) or ""
            if text:
                sections.append("<h3>" + label + "</h3><p>" + escape(text) + "</p>")
        reader = paper.get("reader_url") or ""
        link = ""
        if reader:
            link = '<p><a class="reader-link" href="../' + escape(reader) + '">打开中文精读 →</a></p>'
        cards.append(
            '<article class="brief-card"><h2><a href="' + escape(paper["abs_url"]) + '">'
            + escape(title) + '</a></h2><div class="meta">' + escape(paper.get("id", ""))
            + " · 重要度 " + str(paper.get("score", 0)) + "</div>"
            + "".join(sections) + link + "</article>"
        )
    css = _read(ROOT / "assets" / "style.css")
    tpl = _read(ROOT / "templates" / "brief.html")
    days = brief_days or [{"date": date_str, "picks": len(picks)}]
    options = "".join(
        f'<option value="{escape(d["date"])}.html"{" selected" if d["date"] == date_str else ""}>{escape(d["date"])}（{d["picks"]}篇推送）</option>'
        for d in days
    )
    page = (tpl.replace("__CSS__", css)
            .replace("__DATE__", escape(date_str))
            .replace("__BRIEF_OPTIONS__", options)
            .replace("__CARDS__", "".join(cards) or "<p>今日暂无精选。</p>"))
    out = SITE_DIR / "brief" / (date_str + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, "utf-8")


def _build_brief_index(cfg, brief_days: list[dict], by_date: dict[str, list[dict]], generated: str) -> None:
    """Build the daily-delivery archive with its own date picker."""
    entries = []
    for day in brief_days:
        date_str = day["date"]
        picks = _brief_picks(by_date.get(date_str, []))
        items = []
        for paper in picks:
            reader = paper.get("reader_url") or ""
            extra = '<a class="reader-link" href="../' + escape(reader) + '">中文精读</a>' if reader else ""
            items.append(
                '<li><a href="' + escape(paper["abs_url"]) + '" target="_blank" rel="noopener">'
                + escape(paper.get("title_zh") or paper["title"]) + "</a>" + extra + "</li>"
            )
        entries.append(
            '<article class="brief-day"><div class="brief-day-head"><div><a class="brief-date" href="'
            + escape(date_str) + '.html">' + escape(date_str) + '</a><span class="brief-day-count">'
            + str(len(picks)) + ' 篇推送</span></div><a class="brief-day-link" href="'
            + escape(date_str) + '.html">阅读完整推送 →</a></div>'
            + '<ol class="brief-title-list">' + "".join(items) + "</ol></article>"
        )
    options = "".join(
        f'<option value="{escape(d["date"])}.html">{escape(d["date"])}（{d["picks"]}篇推送）</option>'
        for d in brief_days
    )
    tpl = _read(ROOT / "templates" / "brief-index.html")
    page = (tpl.replace("__CSS__", _read(ROOT / "assets" / "style.css"))
            .replace("__BRIEF_OPTIONS__", options)
            .replace("__ENTRIES__", "".join(entries) or '<p class="empty">暂无已生成的每日推送。</p>')
            .replace("__GENERATED__", escape(generated)))
    out = SITE_DIR / "brief" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, "utf-8")


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
