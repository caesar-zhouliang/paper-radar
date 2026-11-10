"""Build the short Feishu brief: summary, method and driving takeaway."""
from __future__ import annotations

from html import escape


def _pick_text(paper: dict) -> tuple[str, str, str, str]:
    brief = paper.get("brief_zh") or {}
    # The short brief is intentionally generated separately from the arXiv
    # abstract: keep scores and benchmark tables out of it.
    summary = brief.get("summary") or paper.get("abstract_zh") or paper.get("abstract") or ""
    method = brief.get("method") or ""
    driving = brief.get("driving") or ""
    return paper.get("title_zh") or paper["title"], summary.strip(), method.strip(), driving.strip()


def markdown(cfg, papers: list[dict], date_str: str) -> str:
    base = (cfg.nav("site.base_url", "") or "").rstrip("/")
    picks = sorted([p for p in papers if p.get("pick")], key=lambda p: -int(p.get("score", 0)))[:10]
    lines = [f"## {date_str} 论文简报", ""]
    for index, paper in enumerate(picks, 1):
        title, summary, method, driving = _pick_text(paper)
        reader = paper.get("reader_url") or ""
        lines.append(f"**{index}. {title}**")
        if summary:
            lines.append(f"**摘要**：{summary}")
        if method:
            lines.append(f"**实验方法**：{method}")
        if driving:
            lines.append(f"**对自动驾驶方案的帮助**：{driving}")
        lines.append(f"[论文主页]({paper['abs_url']})")
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
    feishu.send_markdown(f"Paper Radar · {date_str} 论文简报", body)
    return True
