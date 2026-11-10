"""Generate complete Chinese readers for the top papers using Codex + PyMuPDF."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"


def _valid_pdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 50_000:
        return False
    with path.open("rb") as handle:
        return handle.read(4) == b"%PDF"


def _curl(url: str, target: Path, timeout: int = 120) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "curl", "-L", "--fail", "--silent", "--show-error",
            "--connect-timeout", "20", "--max-time", str(timeout),
            "-o", str(target), url,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return _valid_pdf(target)


def _arxiv_pdf(title: str) -> str:
    """Resolve a conference title to an arXiv PDF when conference storage is slow."""
    phrase = re.sub(r"[^a-zA-Z0-9 ]+", " ", title).strip()
    if not phrase:
        return ""
    query = urllib.parse.quote(f'ti:"{phrase}"')
    url = f"https://export.arxiv.org/api/query?search_query={query}&max_results=5"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "PaperRadar/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
        namespace = {"a": "http://www.w3.org/2005/Atom"}
        wanted = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        for entry in root.findall("a:entry", namespace):
            found = re.sub(
                r"[^a-z0-9]+", " ", (entry.findtext("a:title", "", namespace) or "").lower()
            ).strip()
            if found != wanted:
                continue
            for link in entry.findall("a:link", namespace):
                if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                    return link.get("href", "")
    except Exception:
        return ""
    return ""


def _download(url: str, target: Path, title: str = "") -> None:
    if _curl(url, target, timeout=120):
        return
    # ICLR proceedings can take minutes for a single PDF. Prefer the equivalent
    # arXiv version when it exists, while keeping the conference as the source.
    fallback = _arxiv_pdf(title) if title else ""
    if fallback and fallback != url and _curl(fallback, target, timeout=180):
        return
    raise RuntimeError("PDF download failed")


def _text(pdf: Path, out: Path) -> None:
    result = subprocess.run(["pdftotext", "-layout", str(pdf), str(out)], check=False)
    if result.returncode != 0 or not out.exists():
        raise RuntimeError("pdftotext failed")


def _clusters(rects: list, gap: float = 55) -> list:
    """Group visual elements that are stacked closely together."""
    import pymupdf

    def union(values):
        return pymupdf.Rect(
            min(value.x0 for value in values),
            min(value.y0 for value in values),
            max(value.x1 for value in values),
            max(value.y1 for value in values),
        )

    groups: list[list] = []
    for rect in sorted(rects, key=lambda value: (value.y0, value.x0)):
        if not groups or rect.y0 > union(groups[-1]).y1 + gap:
            groups.append([rect])
        else:
            groups[-1].append(rect)
    merged = []
    for group in groups:
        rect = union(group)
        if rect.width >= 80 and rect.height >= 25:
            merged.append(rect)
    return merged


def _figure_rect(page, top: float, caption_top: float, x_min: float, x_max: float):
    """Find the visual block immediately above a caption.

    Conference PDFs draw most plots as vectors and use empty rectangles for
    prompt boxes, so using only large filled drawings misses common figures.
    Long lines are useful here: their vertical/horizontal spans merge into the
    surrounding box through the clustering below.
    """
    import pymupdf

    candidates = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.y0 < top - 10 or rect.y0 >= caption_top - 2:
            continue
        if rect.x1 < x_min - 10 or rect.x0 > x_max + 10:
            continue
        if rect.width < 8 and rect.height < 8:
            continue
        candidates.append(pymupdf.Rect(rect))
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"])
        if rect.y0 < top - 10 or rect.y0 >= caption_top - 2:
            continue
        if rect.x1 < x_min - 10 or rect.x0 > x_max + 10:
            continue
        if rect.width >= 12 and rect.height >= 12:
            candidates.append(rect)
    clusters = _clusters(candidates)
    if not clusters:
        return None
    # The figure sits directly above its caption. Looking at the nearest
    # cluster prevents title/body text at the top of the page from leaking in.
    return max(clusters, key=lambda rect: (rect.y1, rect.width * rect.height))


def _figures(pdf: Path, out_dir: Path, limit: int = 0) -> list[dict]:
    try:
        import pymupdf
    except ImportError:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    captions = []
    for page_index, page in enumerate(doc):
        for block in page.get_text("blocks"):
            match = re.match(r"(?i)^\s*(figure|fig\.)\s*(\d+)\s*[:.|]", block[4])
            if match:
                captions.append(
                    (page_index, block[1], block[3], match.group(2), " ".join(block[4].split()), page)
                )
    if not captions:
        return []
    figures = []
    last_by_region: dict[tuple[int, str], float] = {}
    for page_index, caption_top, caption_bottom, number, caption, page in captions:
        if limit and len(figures) >= limit:
            break
        cap = next(
            block for block in page.get_text("blocks")
            if block[1] == caption_top and re.match(r"(?i)^\s*(figure|fig\.)\s*" + str(number) + r"\s*[:.|]", block[4])
        )
        caption_width = cap[2] - cap[0]
        if caption_width < page.rect.width * 0.55:
            center = (cap[0] + cap[2]) / 2
            region = "left" if center < page.rect.width / 2 else "right"
        else:
            region = "full"
        if region == "left":
            # A side-by-side figure column can start slightly before the page
            # midpoint. Use the caption edge to avoid including the next chart.
            x_min, x_max = 0, min(page.rect.width, cap[2] + 6)
        elif region == "right":
            x_min, x_max = max(0, cap[0] - 6), page.rect.width
        else:
            x_min, x_max = 0, page.rect.width
        key = (page_index, region)
        previous_bottom = last_by_region.get(key, 18)
        rect = _figure_rect(page, previous_bottom + 2, caption_top, x_min, x_max)
        if rect is None:
            last_by_region[key] = caption_bottom + 2
            continue
        clip = pymupdf.Rect(
            max(x_min, rect.x0 - 3), max(0, rect.y0 - 3),
            min(x_max, rect.x1 + 3), min(page.rect.y1, caption_top - 2),
        )
        if clip.width < 80 or clip.height < 30:
            last_by_region[key] = caption_bottom + 2
            continue
        target = out_dir / f"figure-{number}.png"
        page.get_pixmap(clip=clip, dpi=180, alpha=False).save(target)
        figures.append({"number": number, "page": page_index + 1, "caption": caption, "image": target.name})
        last_by_region[key] = caption_bottom + 2
    (out_dir / "figures.json").write_text(json.dumps(figures, ensure_ascii=False, indent=1), "utf-8")
    return figures


def _extract_summary(markdown: str) -> str:
    match = re.search(r"## 基础摘要\s*(.*?)(?=\n## )", markdown, re.S)
    return " ".join(match.group(1).split()) if match else ""


def _replace_summary(markdown: str, summary: str) -> str:
    if not summary.strip():
        return markdown
    return re.sub(
        r"(## 基础摘要\s*\n).*?(?=\n## )",
        lambda match: match.group(1) + "\n" + summary.strip() + "\n",
        markdown,
        count=1,
        flags=re.S,
    )


def refresh(paper: dict) -> dict | None:
    """Repair an existing reader: all figures plus the current short summary."""
    reader_dir = ROOT / "data" / "readers" / paper["id"]
    translation = reader_dir / "translation.md"
    if not translation.exists():
        return None
    work = WORK / paper["id"]
    pdf = work / "paper.pdf"
    try:
        if not pdf.exists():
            _download(paper["pdf_url"], pdf, paper.get("title", ""))
        figures = _figures(pdf, work / "figures", limit=0)
    except Exception as exc:
        print(f"  ! 精读补图失败 {paper['id']}: {exc}")
        return None
    markdown = translation.read_text("utf-8")
    markdown = re.sub(r"\n+## 补充图表\b.*\Z", "", markdown, flags=re.S)
    markdown = _replace_summary(markdown, (paper.get("brief_zh") or {}).get("summary", ""))
    missing = [item for item in figures if item["image"] not in markdown]
    if missing:
        markdown += "\n\n## 补充图表\n"
        for item in missing:
            markdown += (
                f'\n<figure class="paper-figure"><img src="{item["image"]}" alt="图 {item["number"]}" loading="lazy">'
                f'<figcaption>图 {item["number"]}：{item["caption"]}</figcaption></figure>\n'
            )
    for item in figures:
        source = work / "figures" / item["image"]
        if source.exists():
            shutil.copy2(source, reader_dir / item["image"])
    (reader_dir / "figures.json").write_text(json.dumps(figures, ensure_ascii=False, indent=1), "utf-8")
    translation.write_text(markdown, "utf-8")
    return {"id": paper["id"], "summary": _extract_summary(markdown), "figures": len(figures)}


def generate(paper: dict, date_str: str, reader_limit: int = 1) -> dict | None:
    reader_dir = ROOT / "data" / "readers" / paper["id"]
    if (reader_dir / "translation.md").exists():
        return refresh(paper)
    work = WORK / paper["id"]
    work.mkdir(parents=True, exist_ok=True)
    pdf = work / "paper.pdf"
    text = work / "paper.txt"
    try:
        if not _valid_pdf(pdf):
            _download(paper["pdf_url"], pdf, paper.get("title", ""))
        _text(pdf, text)
        figures = _figures(pdf, work / "figures", limit=0)
    except Exception as exc:
        print(f"  ! 精读素材准备失败 {paper['id']}: {exc}")
        return None
    figure_manifest = "\n".join(
        f"- 图 {item['number']}（第 {item['page']} 页，文件 {item['image']}）：{item['caption']}"
        for item in figures
    )
    prompt = f"""把这篇论文制作成中文精读 Markdown，供 Paper Radar 网站使用。

论文标题：{paper['title']}
arXiv：{paper['id']}
PDF：{pdf}
提取文本：{text}
结构图目录：{work / 'figures'}

输出：{work / 'translation.md'}

严格顺序：
## 基础摘要
300-500 字，只写：论文要解决什么问题、现有方法的关键不足、核心创新点、实验具体怎么做（数据、模型、训练/推理流程、对照设置、工程实现或 trick）。不要罗列评测指标或分数，不要写“提升 x%”“SOTA”之类的内容。可以写实验步骤和实现细节。
## 论文结构图
论文中每一张 Figure 都必须保留，不能缺图。用 <!--RAW--> HTML 块嵌入 {work / 'figures'} 中的全部 PNG，引用时只写文件名；每张图后写中文图注。可参考以下图表清单：
{figure_manifest}
## 中文完整翻译
按论文章节逐节翻译，保留全部公式、表格、算法、图注和附录。不要只写摘要，不要省略图表。公式使用标准 LaTeX（$...$ 与 $$...$$），网站会渲染成完整数学公式；表格使用 Markdown 或 HTML 表格。

只写 translation.md 和临时文件，不要修改其他文件。
"""
    codex = shutil.which("codex") or str(Path.home() / ".local/bin/codex")
    result = None
    try:
        with (work / "codex.log").open("wb") as log:
            result = subprocess.run(
                [codex, "exec", "--cd", str(work), "--skip-git-repo-check", "--sandbox", "danger-full-access", "--ephemeral", "-"],
                input=prompt.encode("utf-8"), stdout=log, stderr=subprocess.STDOUT, timeout=3600, check=False,
            )
    except Exception as exc:
        print(f"  ! Codex 精读生成失败 {paper['id']}: {exc}")
    translation = work / "translation.md"
    if not translation.exists() or translation.stat().st_size < 2000:
        print(f"  ! Codex 未产出可用 translation.md（exit={getattr(result, 'returncode', None)}）")
        return None
    if result is not None and result.returncode != 0:
        print(f"  · Codex 退出码 {result.returncode}，但已找到完整 translation.md，继续发布")
    reader_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(translation, reader_dir / "translation.md")
    markdown = translation.read_text("utf-8")
    missing = [item for item in figures if item["image"] not in markdown]
    if missing:
        extra = ["\n\n## 补充图表\n"]
        for item in missing:
            extra.append(
                f'\n<figure class="paper-figure"><img src="{item["image"]}" alt="图 {item["number"]}" loading="lazy">'
                f'<figcaption>图 {item["number"]}：{item["caption"]}</figcaption></figure>\n'
            )
        markdown += "".join(extra)
        translation.write_text(markdown, "utf-8")
    for item in figures:
        source = work / "figures" / item["image"]
        if source.exists():
            shutil.copy2(source, reader_dir / item["image"])
    (reader_dir / "figures.json").write_text(json.dumps(figures, ensure_ascii=False, indent=1), "utf-8")
    return {"id": paper["id"], "summary": _extract_summary(markdown)}


def choose(papers: list[dict], limit: int = 1) -> list[dict]:
    ranked = [p for p in papers if p.get("pick")]
    ranked.sort(key=lambda p: -int(p.get("score", 0)))
    return ranked[:limit]
