"""arXiv API 抓取（只用标准库，避免额外依赖）。"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARX = "{http://arxiv.org/schemas/atom}"
UA = "PaperRadar/1.0 (github actions; contact: you@example.com)"


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


_URL_RE = re.compile(r"https?://\S+")


def _strip_math(text: str) -> str:
    """arXiv 标题/摘要里常有 $v$-prediction、\\mathrm{BEV} 这类 LaTeX 源码，转成可读文本。"""
    t = text
    t = re.sub(r"\$([^$]{1,80})\$", r"\1", t)                 # $...$ → 内容
    t = re.sub(r"\\[a-zA-Z]+\s*\{([^{}]*)\}", r"\1", t)      # \mathrm{BEV} → BEV
    t = re.sub(r"\\[a-zA-Z]+", "", t)                          # 其余命令直接去掉
    t = re.sub(r"[{}]", "", t)
    t = t.replace("~", " ")
    return t


def _tidy(text: str | None) -> str:
    return _clean(_strip_math(text or ""))


def _get(url: str, retries: int = 4, timeout: int = 45) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError) as exc:
            last = exc
            wait = 5 * (attempt + 1)
            print(f"  ! 请求失败({exc})，{wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"arXiv 请求多次失败: {last}")


def _parse(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall(f"{ATOM}entry"):
        raw_id = _clean(e.findtext(f"{ATOM}id"))
        m = re.search(r"abs/([^v]+)(v\d+)?$", raw_id)
        if not m:
            continue
        aid = m.group(1)
        links = {l.get("title") or l.get("rel"): l.get("href") for l in e.findall(f"{ATOM}link")}
        cats = [c.get("term") for c in e.findall(f"{ATOM}category") if c.get("term")]
        primary = e.find(f"{ARX}primary_category")
        out.append(
            {
                "id": aid,
                "title": _tidy(e.findtext(f"{ATOM}title")),
                "abstract": _tidy(e.findtext(f"{ATOM}summary")),
                "authors": [_clean(a.findtext(f"{ATOM}name")) for a in e.findall(f"{ATOM}author")],
                "published": _clean(e.findtext(f"{ATOM}published")),
                "updated": _clean(e.findtext(f"{ATOM}updated")),
                "categories": cats,
                "primary_category": primary.get("term") if primary is not None else (cats[0] if cats else ""),
                "comment": _clean(_URL_RE.sub("", e.findtext(f"{ARX}comment") or ""))[:160],
                "journal_ref": _clean(e.findtext(f"{ARX}journal_ref")),
                "abs_url": f"https://arxiv.org/abs/{aid}",
                "pdf_url": links.get("pdf") or f"https://arxiv.org/pdf/{aid}",
            }
        )
    return out


def fetch_recent(categories: list[str], days: int = 2, page_size: int = 200,
                 max_docs: int = 3000, interval: float = 3.2,
                 verbose: bool = True) -> list[dict]:
    """抓取最近 N 天内提交的论文（按提交时间倒序翻页，过期即停）。"""
    query = " OR ".join(f"cat:{c}" for c in categories)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    seen: dict[str, dict] = {}
    start = 0

    while start < max_docs:
        params = {
            "search_query": query,
            "start": start,
            "max_results": page_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{API}?{urllib.parse.urlencode(params)}"
        batch = _parse(_get(url))
        if not batch:
            break
        if verbose:
            print(f"  · 已取 {start + len(batch)} 条（本批最新 {batch[0]['published'][:10]}）")

        oldest = None
        for item in batch:
            try:
                pub = datetime.fromisoformat(item["published"].replace("Z", "+00:00"))
            except ValueError:
                continue
            oldest = pub
            if pub < cutoff:
                continue
            if item["id"] in seen:
                continue
            seen[item["id"]] = item

        # 本批已整体越过时间窗口 → 收工
        if oldest and oldest < cutoff:
            break
        start += page_size
        time.sleep(interval)

    papers = list(seen.values())
    if verbose:
        print(f"  · 时间窗口内共 {len(papers)} 篇")
    return papers
