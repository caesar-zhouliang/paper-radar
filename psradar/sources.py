"""Pluggable extra paper sources.

arXiv remains the primary source. This module supports conference/community
RSS feeds (OpenReview, 知乎/RSSHub, lab blogs, etc.) via configuration. Feed
items are normalized into the same paper shape consumed by the ranker.
"""
from __future__ import annotations

import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _entry_to_paper(entry, source: dict) -> dict | None:
    title = _clean(entry.findtext("title"))
    link = (entry.findtext("link") or "").strip()
    if not title or not link:
        return None
    summary = _clean(entry.findtext("description") or entry.findtext("summary"))
    published = entry.findtext("pubDate") or entry.findtext("published") or ""
    try:
        published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except Exception:
        published_dt = datetime.now(timezone.utc)
    source_id = source.get("id", "rss")
    raw_id = source_id + "-" + re.sub(r"[^A-Za-z0-9]+", "-", link)[-80:]
    return {
        "id": raw_id,
        "title": title,
        "abstract": summary,
        "authors": [],
        "published": published_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "updated": published_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "categories": [source_id],
        "primary_category": source_id,
        "comment": source.get("name", source_id),
        "journal_ref": "",
        "abs_url": link,
        "pdf_url": "",
        "source": source.get("name", source_id),
    }


def fetch_extra(sources: list[dict], interval: float = 1.0) -> list[dict]:
    papers: list[dict] = []
    for source in sources:
        url = source.get("rss")
        if not url or not source.get("enabled", True):
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "PaperRadar/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                root = ET.fromstring(response.read())
            for entry in root.findall(".//item"):
                paper = _entry_to_paper(entry, source)
                if paper:
                    papers.append(paper)
            if not papers:
                for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                    paper = _entry_to_paper(entry, source)
                    if paper:
                        papers.append(paper)
            print(f"  · 额外源 {source.get('name', source.get('id'))}: {len(papers)} 条")
        except Exception as exc:
            print(f"  ! 额外源失败 {source.get('name', source.get('id'))}: {exc}")
        time.sleep(interval)
    return papers
