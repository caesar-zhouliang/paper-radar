"""Generate one full Chinese reader per day using Codex + PyMuPDF."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "PaperRadar/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        target.write_bytes(response.read())


def _text(pdf: Path, out: Path) -> None:
    result = subprocess.run(["pdftotext", "-layout", str(pdf), str(out)], check=False)
    if result.returncode != 0 or not out.exists():
        raise RuntimeError("pdftotext failed")


def _figures(pdf: Path, out_dir: Path, limit: int = 2) -> list[Path]:
    try:
        import pymupdf
    except ImportError:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    captions = []
    for page_index, page in enumerate(doc):
        for block in page.get_text("blocks"):
            match = re.match(r"(?i)^\s*(figure|fig\.)\s*(\d+)\s*[:.]", block[4])
            if match:
                captions.append((block[1], match.group(2), page_index, page))
    if not captions:
        return []
    priority = ("pipeline", "overview", "architecture", "framework", "illustration", "motivating")
    chosen = None
    for top, number, page_index, page in captions:
        text = page.get_text().lower()
        chosen = (top, number, page_index, page)
        if any(word in text for word in priority):
            break
    if chosen is None:
        return []
    top, number, page_index, page = chosen
    drawings = [
        d["rect"] for d in page.get_drawings()
        if d["rect"].y0 > 20 and d["rect"].y1 <= top - 4 and d["rect"].width > 2
    ]
    if not drawings:
        return []
    rect = drawings[0]
    for other in drawings[1:]:
        rect |= other
    clip = pymupdf.Rect(max(0, rect.x0 - 3), max(0, rect.y0 - 3), min(page.rect.x1, rect.x1 + 3), min(page.rect.y1, rect.y1 - 1))
    pix = page.get_pixmap(clip=clip, dpi=180, alpha=False)
    target = out_dir / f"figure-{number}.png"
    pix.save(target)
    return [target]


def _extract_summary(markdown: str) -> str:
    match = re.search(r"## 基础摘要\s*(.*?)(?=\n## )", markdown, re.S)
    return " ".join(match.group(1).split()) if match else ""


def generate(paper: dict, date_str: str, reader_limit: int = 1) -> dict | None:
    reader_dir = ROOT / "data" / "readers" / paper["id"]
    if (reader_dir / "translation.md").exists():
        return {"id": paper["id"], "summary": _extract_summary((reader_dir / "translation.md").read_text("utf-8"))}
    work = WORK / paper["id"]
    work.mkdir(parents=True, exist_ok=True)
    pdf = work / "paper.pdf"
    text = work / "paper.txt"
    try:
        _download(paper["pdf_url"], pdf)
        _text(pdf, text)
        figures = _figures(pdf, work / "figures", limit=2)
    except Exception as exc:
        print(f"  ! 精读素材准备失败 {paper['id']}: {exc}")
        return None
    prompt = f"""把这篇论文制作成中文精读 Markdown，供 Paper Radar 网站使用。

论文标题：{paper['title']}
arXiv：{paper['id']}
PDF：{pdf}
提取文本：{text}
结构图目录：{work / 'figures'}

输出：{work / 'translation.md'}

严格顺序：
## 基础摘要
300-500 字，写清问题、方法、关键数字、结论、局限。
## 论文结构图
用 <!--RAW--> HTML 块嵌入 {work / 'figures'} 中的 PNG，引用时只写文件名；每张图后写中文图注。
## 中文完整翻译
按论文章节逐节翻译，保留公式、表格、算法、图注和附录。不要只写摘要。

只写 translation.md 和临时文件，不要修改其他文件。
"""
    codex = shutil.which("codex") or str(Path.home() / ".local/bin/codex")
    try:
        with (work / "codex.log").open("wb") as log:
            result = subprocess.run(
                [codex, "exec", "--cd", str(work), "--skip-git-repo-check", "--sandbox", "danger-full-access", "--ephemeral", "-"],
                input=prompt.encode("utf-8"), stdout=log, stderr=subprocess.STDOUT, timeout=3600, check=False,
            )
    except Exception as exc:
        print(f"  ! Codex 精读生成失败 {paper['id']}: {exc}")
        return None
    translation = work / "translation.md"
    if not translation.exists():
        print(f"  ! Codex 未产出 translation.md（exit={result.returncode}）")
        return None
    reader_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(translation, reader_dir / "translation.md")
    for figure in figures:
        shutil.copy2(figure, reader_dir / figure.name)
    markdown = translation.read_text("utf-8")
    return {"id": paper["id"], "summary": _extract_summary(markdown)}


def choose(papers: list[dict], limit: int = 1) -> list[dict]:
    ranked = [p for p in papers if p.get("pick")]
    ranked.sort(key=lambda p: -int(p.get("score", 0)))
    return ranked[:limit]
