"""Official conference proceedings adapters.

Supported kinds:
  cvf     CVPR/ICCV/ECCV OpenAccess listing
  iclr    proceedings.iclr.cc / proceedings.neurips.cc listing
  pmlr    PMLR volume listing (CoRL, ICML, ...)

Conference lists are large. We cache parsed results and only fetch detail
abstraction pages for titles that match the configured research topics.
"""
from __future__ import annotations

import gzip
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "conference-cache"


def _clean(value: str | None) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _get(url: str, timeout: int = 240) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PaperRadar/1.0 (conference source; contact: xuzhouliang@qianli-drive.com)",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        if response.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
    return data.decode("utf-8", "replace")


def _patterns(keywords: list[str]) -> list[re.Pattern]:
    return [
        re.compile(r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?:s|es)?(?![a-z0-9])")
        for keyword in keywords
        if keyword.strip()
    ]


def _title_matches(title: str, patterns: list[re.Pattern]) -> bool:
    low = title.lower()
    return any(pattern.search(low) for pattern in patterns)


def _hit_score(title: str, patterns: list[re.Pattern]) -> int:
    low = title.lower()
    return sum(1 for pattern in patterns if pattern.search(low))


def _paper_id(source_id: str, url: str) -> str:
    return source_id + "-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _base_paper(source: dict, title: str, abs_url: str, authors: list[str], pdf_url: str = "") -> dict:
    published = str(source.get("date") or f"{source.get('year', datetime.now().year)}-01-01")
    published_iso = published + "T00:00:00Z" if len(published) == 10 else published
    name = source.get("name", source["id"])
    return {
        "id": _paper_id(source["id"], abs_url),
        "title": _clean(title),
        "abstract": "",
        "authors": authors,
        "published": published_iso,
        "updated": published_iso,
        "categories": [source.get("topic", "conference")],
        "primary_category": source.get("topic", "conference"),
        "comment": name,
        "journal_ref": name,
        "abs_url": abs_url,
        "pdf_url": pdf_url,
        "source": name,
        "sources": [name],
        "source_kind": "conference",
    }


def _fetch_cvf(source: dict, patterns: list[re.Pattern], max_abstracts: int) -> list[dict]:
    listing = _get(source["url"])
    blocks = re.findall(
        r'<dt class="ptitle">\s*<br>\s*<a href="([^"]+)">(.*?)</a></dt>\s*<dd>(.*?)</dd>',
        listing, re.S | re.I,
    )
    print(f"  · {source['name']} 列表 {len(blocks)} 篇")
    papers = []
    for href, title, detail in blocks:
        if not _title_matches(_clean(title), patterns):
            continue
        authors = re.findall(r'name="query_author" value="([^"]+)"', detail)
        pdfs = re.findall(r'href="([^"]+\.pdf)"', detail)
        abs_url = urllib.parse.urljoin("https://openaccess.thecvf.com", html.unescape(href))
        pdf_url = urllib.parse.urljoin("https://openaccess.thecvf.com", html.unescape(pdfs[0])) if pdfs else ""
        if not pdf_url and "/html/" in abs_url:
            pdf_url = abs_url.replace("/html/", "/papers/").replace("_paper.html", "_paper.pdf")
        papers.append(_base_paper(source, title, abs_url, [_clean(a) for a in authors], pdf_url))
    papers.sort(key=lambda p: -_hit_score(p["title"], patterns))
    for paper in papers[:max_abstracts]:
        try:
            page = _get(paper["abs_url"])
            match = re.search(r'<div id="abstract"[^>]*>(.*?)</div>', page, re.S | re.I)
            if match:
                paper["abstract"] = _clean(match.group(1))
        except Exception as exc:
            print(f"  ! {source['name']} 摘要失败 {paper['title'][:50]}: {exc}")
        time.sleep(0.15)
    return [paper for paper in papers[:max_abstracts] if paper.get("abstract")]


def _meta(page: str, name: str) -> list[str]:
    return [_clean(value) for value in re.findall(rf'<meta name="{re.escape(name)}" content="([^"]*)"', page, re.I)]


def _fetch_iclr(source: dict, patterns: list[re.Pattern], max_abstracts: int) -> list[dict]:
    listing = _get(source["url"])
    links = re.findall(r'<a title="paper title" href="([^"]+)">(.*?)</a>', listing, re.S | re.I)
    print(f"  · {source['name']} 列表 {len(links)} 篇")
    papers = []
    for href, title in links:
        if not _title_matches(_clean(title), patterns):
            continue
        abs_url = urllib.parse.urljoin(source["url"], html.unescape(href))
        papers.append(_base_paper(source, title, abs_url, []))
    papers.sort(key=lambda p: -_hit_score(p["title"], patterns))
    for paper in papers[:max_abstracts]:
        try:
            page = _get(paper["abs_url"])
            authors = _meta(page, "citation_author")
            pdfs = _meta(page, "citation_pdf_url")
            match = re.search(r'<p class="paper-abstract">(.*?)</p>\s*</div>', page, re.S | re.I)
            if not match:
                match = re.search(r'<p class="paper-abstract">(.*?)</p>', page, re.S | re.I)
            paper["authors"] = authors
            paper["pdf_url"] = pdfs[0] if pdfs else ""
            if match:
                paper["abstract"] = _clean(match.group(1))
        except Exception as exc:
            print(f"  ! {source['name']} 摘要失败 {paper['title'][:50]}: {exc}")
        time.sleep(0.15)
    return [paper for paper in papers[:max_abstracts] if paper.get("abstract")]


def _fetch_pmlr(source: dict, patterns: list[re.Pattern], max_abstracts: int) -> list[dict]:
    listing = _get(source["url"])
    blocks = re.findall(r'<div class="paper">(.*?)</div>', listing, re.S | re.I)
    print(f"  · {source['name']} 列表 {len(blocks)} 篇")
    papers = []
    for block in blocks:
        title_match = re.search(r'<p class="title">(.*?)</p>', block, re.S | re.I)
        abs_match = re.search(r'href="([^"]+)">abs</a>', block, re.I)
        if not title_match or not abs_match:
            continue
        title = _clean(title_match.group(1))
        if not _title_matches(title, patterns):
            continue
        authors_match = re.search(r'<span class="authors">(.*?)</span>', block, re.S | re.I)
        authors = [_clean(a) for a in re.split(r",\s*", _clean(authors_match.group(1)))] if authors_match else []
        abs_url = urllib.parse.urljoin(source["url"], html.unescape(abs_match.group(1)))
        pdfs = re.findall(r'href="([^"]+\.pdf)"', block, re.I)
        papers.append(_base_paper(source, title, abs_url, authors, pdfs[0] if pdfs else ""))
    papers.sort(key=lambda p: -_hit_score(p["title"], patterns))
    for paper in papers[:max_abstracts]:
        try:
            page = _get(paper["abs_url"])
            match = re.search(r'<div id="abstract"[^>]*>(.*?)</div>', page, re.S | re.I)
            if match:
                paper["abstract"] = _clean(match.group(1))
            pdfs = _meta(page, "citation_pdf_url")
            if pdfs:
                paper["pdf_url"] = pdfs[0]
        except Exception as exc:
            print(f"  ! {source['name']} 摘要失败 {paper['title'][:50]}: {exc}")
        time.sleep(0.15)
    return [paper for paper in papers[:max_abstracts] if paper.get("abstract")]


FETCHERS = {"cvf": _fetch_cvf, "iclr": _fetch_iclr, "pmlr": _fetch_pmlr}


def fetch_conferences(cfg) -> list[dict]:
    if not cfg.nav("conferences.enabled", True):
        return []
    refresh_days = int(cfg.nav("conferences.refresh_days", 7))
    max_abstracts = int(cfg.nav("conferences.max_abstracts_per_source", 80))
    keywords = []
    for topic in cfg.get("topics", []):
        keywords.extend(topic.get("keywords", []))
    patterns = _patterns(keywords)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    all_papers: list[dict] = []
    for source in cfg.nav("conferences.sources", []) or []:
        if not source.get("enabled", True):
            continue
        kind = source.get("kind")
        fetcher = FETCHERS.get(kind)
        if fetcher is None:
            print(f"  ! 未知会议源类型 {kind}: {source.get('id')}")
            continue
        cache_file = CACHE_DIR / f"{source['id']}.json"
        cached = None
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text("utf-8"))
                fetched = datetime.fromisoformat(cached["fetched_at"])
                age = (datetime.now(timezone.utc) - fetched).days
                if age < refresh_days:
                    print(f"  · {source['name']} 使用缓存（{age} 天前）")
                    all_papers.extend(cached.get("papers", []))
                    continue
            except Exception:
                cached = None
        try:
            papers = fetcher(source, patterns, max_abstracts)
            cache_file.write_text(
                json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "papers": papers}, ensure_ascii=False),
                "utf-8",
            )
            all_papers.extend(papers)
            print(f"  · {source['name']} 命中方向 {len(papers)} 篇")
        except Exception as exc:
            print(f"  ! {source['name']} 抓取失败: {exc}")
            if cached:
                print(f"  · {source['name']} 回退旧缓存")
                all_papers.extend(cached.get("papers", []))
    return all_papers
