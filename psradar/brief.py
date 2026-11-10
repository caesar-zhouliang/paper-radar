"""Build the short Feishu brief: summary only, links to the site readers."""
from __future__ import annotations

from html import escape


def _pick_text(paper: dict) -> tuple[str, str, str]:
    brief = paper.get("brief_zh") or {}
    summary = brief.get("summary") or paper.get("abstract_zh") or paper.get("abstract") or ""
    driving = brief.get("driving") or ""
    return paper.get("title_zh") or paper["title"], summary.strip(), driving.strip()


def markdown(cfg, papers: list[dict], date_str: str) -> str:
    base = (cfg.nav("site.base_url", "") or "").rstrip("/")
    picks = [p for p in papers if p.get("pick")][:10]
    lines = [f"## {date_str} 论文摘要", ""]
    for index, paper in enumerate(picks, 1):
        title, summary, driving = _pick_text(paper)
        reader = paper.get("reader_url") or ""
        lines.append(f"**{index}. {title}**")
        if summary:
            lines.append(summary)
        if driving:
            lines.append(f"**对自动驾驶的启发**：{driving}")
        lines.append(f"[arXiv]({paper['abs_url']})")
        if reader:
            lines.append(f"[中文精读]({base}/{reader})")
        lines.append("")
    if not picks:
        lines.append("今日暂无精选论文。")
    lines.append(f"[论文雷达首页]({base}/)")
    return "\n".join(lines).replace("\n\n\n", "\n\n")


def send(cfg, papers: list[dict], date_str: str) -> bool:
    from . import feishu
    body = markdown(cfg, papers, date_str)
    feishu.send_markdown(f"Paper Radar · {date_str} 摘要", body)
    return True
