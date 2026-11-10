"""Generate a Chinese deep-read HTML page for one paper."""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


def _inline(text: str) -> str:
    # Avoid the HTML parser treating a math comparison such as x < y as a tag.
    # Keep ampersands intact for LaTeX alignment environments.
    text = re.sub(
        r"(?<!\\)\$(.+?)(?<!\\)\$",
        lambda match: "$" + match.group(1).replace("<", "&lt;").replace(">", "&gt;") + "$",
        text,
        flags=re.S,
    )
    text = re.sub(r"`([^`]+)`", lambda m: "<code>" + html.escape(m.group(1)) + "</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r'(?<!href=")(?<!">)(https?://[^\s<），。；]+)', r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)
    return text


def _raw_html(text: str) -> str:
    """Make plain figure images clickable without touching generated HTML."""
    if 'class="figure-zoom"' in text:
        return text
    return re.sub(
        r'(<img\b[^>]*>)',
        lambda match: '<button class="figure-zoom" type="button" aria-label="放大图片">'
        + match.group(1) + "</button>",
        text,
        count=1,
        flags=re.I,
    )


def _slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-").lower()
    return text or "section"


def _blocks(markdown: str) -> list[tuple]:
    lines = markdown.splitlines()
    out: list[tuple] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "<!--RAW-->":
            i += 1
            raw = []
            while i < len(lines) and lines[i].strip() != "<!--/RAW-->":
                raw.append(lines[i])
                i += 1
            out.append(("raw", "\n".join(raw)))
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        if line.lstrip().startswith("<"):
            raw = [line]
            i += 1
            while i < len(lines) and lines[i].strip():
                raw.append(lines[i])
                i += 1
            out.append(("raw", "\n".join(raw)))
            continue
        if line.strip().startswith("$$"):
            math_lines = [line]
            i += 1
            while i < len(lines):
                math_lines.append(lines[i])
                if lines[i].strip().endswith("$$") and len(math_lines) > 1:
                    i += 1
                    break
                i += 1
            out.append(("math", "\n".join(math_lines)))
            continue
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            table_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(("table", table_lines))
            continue
        match = re.match(r"^(#{2,4})\s+(.*)$", line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            id_match = re.search(r"\s*\{#([\w\-]+)\}\s*$", text)
            block_id = id_match.group(1) if id_match else _slug(text)
            text = re.sub(r"\s*\{#[\w\-]+\}\s*$", "", text)
            out.append(("heading", level, text, block_id))
            i += 1
            continue
        if re.match(r"^\s*-\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*-\s+", lines[i]):
                items.append(re.sub(r"^\s*-\s+", "", lines[i]).strip())
                i += 1
            out.append(("ul", items))
            continue
        if re.match(r"^\s*>\s?", line):
            quotes = []
            while i < len(lines) and re.match(r"^\s*>\s?", lines[i]):
                quotes.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(("quote", " ".join(quotes)))
            continue
        paragraph = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{2,4})\s+", lines[i]) and not re.match(r"^\s*[-<]", lines[i]):
            paragraph.append(lines[i].strip())
            i += 1
        out.append(("p", " ".join(paragraph)))
    return out


def build(site_dir: Path, paper: dict, markdown_path: Path, figure_dir: Path) -> Path:
    out_dir = site_dir / "readers" / paper["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for item in figure_dir.iterdir():
        if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            (out_dir / item.name).write_bytes(item.read_bytes())
    markdown = markdown_path.read_text("utf-8")
    markdown = markdown[markdown.find("## 基础摘要"):]
    rendered: list[str] = []
    toc: list[tuple[str, str, str]] = []
    for block in _blocks(markdown):
        if block[0] == "heading":
            _, level, text, block_id = block
            tag = {2: "h2", 3: "h3", 4: "h4"}[level]
            rendered.append(f'<{tag} id="{block_id}">{_inline(text)}</{tag}>')
            toc.append(({2: "toc-level-1", 3: "toc-level-2", 4: "toc-level-3"}[level], block_id, text))
        elif block[0] == "p":
            rendered.append(f"<p>{_inline(block[1])}</p>")
        elif block[0] == "ul":
            rendered.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in block[1]) + "</ul>")
        elif block[0] == "quote":
            rendered.append(f"<blockquote><p>{_inline(block[1])}</p></blockquote>")
        elif block[0] == "math":
            math = block[1].replace("<", "&lt;").replace(">", "&gt;")
            rendered.append('<div class="math-display">' + math + "</div>")
        elif block[0] == "table":
            rows = [row.strip().strip("|").split("|") for row in block[1]]
            if len(rows) >= 2:
                header = rows[0]
                body = [row for row in rows[2:] if row]
                head_html = "".join(f"<th>{_inline(cell.strip())}</th>" for cell in header)
                body_html = "".join(
                    "<tr>" + "".join(f"<td>{_inline(cell.strip())}</td>" for cell in row) + "</tr>"
                    for row in body
                )
                rendered.append(
                    '<div class="table-wrap"><table><thead><tr>' + head_html
                    + "</tr></thead><tbody>" + body_html + "</tbody></table></div>"
                )
        elif block[0] == "raw":
            rendered.append(_raw_html(block[1]))
    toc_html = "".join(f'<a class="toc-link {cls}" href="#{bid}">{html.escape(text)}</a>' for cls, bid, text in toc)
    css = (ASSETS / "reader.css").read_text("utf-8")
    js = (ASSETS / "reader.js").read_text("utf-8")
    title = paper.get("title_zh") or paper["title"]
    source = paper.get("source") or "arXiv"
    page = f'''<!doctype html>
<html lang="zh-CN" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — 中文精读</title>
<meta name="description" content="{html.escape(paper.get('abstract',''))}">
<script>(()=>{{const k='paper-radar-theme';document.documentElement.dataset.theme=localStorage.getItem(k)||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');}})();</script>
<style>{css}</style></head><body>
<div class="progress" id="progress"></div><a class="skip-link" href="#content">跳到正文</a>
<div class="shell"><aside class="sidebar"><div class="sidebar-head"><div class="eyebrow">{html.escape(source)} · {html.escape(paper['id'])}</div><div class="sidebar-title">{html.escape(title)}<br><span>中文精读</span></div><p class="sidebar-sub">{html.escape(paper['title'])}</p><div class="tools"><button class="btn" id="themeToggle">切换深色</button><button class="btn" id="printBtn">打印 / PDF</button></div></div><input class="toc-filter" id="tocFilter" placeholder="筛选目录…"><nav class="toc">{toc_html}</nav></aside>
<main class="paper"><header class="hero"><div class="hero-top"><div class="eyebrow">PAPER RADAR · 中文精读</div><div class="hero-mark">{html.escape(paper['id'])}</div></div><h1>{html.escape(title)}</h1><p class="original">{html.escape(paper['title'])}</p><div class="meta"><div><strong>作者</strong><span>{html.escape(', '.join(paper.get('authors', [])[:6]))}</span></div><div><strong>发布</strong><span>{html.escape(paper.get('published_date',''))}</span></div><div><strong>分类</strong><span>{html.escape(', '.join(paper.get('categories', [])[:4]))}</span></div><div><strong>主题</strong><span>{html.escape(paper.get('primary_topic',''))}</span></div></div><div class="actions"><a class="hero-btn primary" href="{html.escape(paper['abs_url'])}" target="_blank">论文主页</a><a class="hero-btn" href="{html.escape(paper['pdf_url'])}" target="_blank">PDF</a><a class="hero-btn" href="/paper-radar/">返回论文库</a></div></header>
<details class="mobile-toc"><summary>展开目录</summary><nav class="toc">{toc_html}</nav></details><article class="content" id="content">{''.join(rendered)}</article></main></div>
<div class="lightbox" id="lightbox" hidden><button class="lightbox-close" id="lightboxClose">×</button><img id="lightboxImage" alt=""><div class="lightbox-caption" id="lightboxCaption"></div></div><button class="to-top" id="toTop">↑</button>
<script>window.MathJax={{tex:{{inlineMath:[['$','$'],['\\\\(','\\\\)']],displayMath:[['$$','$$'],['\\\\[','\\\\]']],processEscapes:true}},svg:{{fontCache:'local'}},options:{{skipHtmlTags:['script','noscript','style','textarea','pre','code']}}}};</script>
<script src="../../assets/mathjax/tex-svg.js"></script>
<script>{js}</script></body></html>'''
    (out_dir / "index.html").write_text(page, "utf-8")
    return out_dir
