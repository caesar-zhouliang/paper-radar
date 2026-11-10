"""方向匹配 + 重要度打分。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_CODE_RE = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co)/[^\s,;)\]]+", re.I)


_PATTERNS: dict[str, list[re.Pattern]] = {}


def _patterns(keywords: list[str]) -> list[re.Pattern]:
    """带词边界的正则，避免 ppo 命中 support、dpo 命中 endpoint 这类误匹配。"""
    key = "|".join(keywords)
    if key not in _PATTERNS:
        pats = []
        for kw in keywords:
            body = re.escape(kw.strip().lower())
            suffix = r"(?:s|es)?" if kw.strip()[-1:].isalpha() else ""
            pats.append(re.compile(r"(?<![a-z0-9])" + body + suffix + r"(?![a-z0-9])"))
        _PATTERNS[key] = pats
    return _PATTERNS[key]


def _hits(text: str, keywords: list[str]) -> int:
    low = text.lower()
    return sum(1 for pat in _patterns(keywords) if pat.search(low))


def _find_code(paper: dict) -> str:
    for field in ("abstract", "comment"):
        m = _CODE_RE.search(paper.get(field) or "")
        if m:
            return m.group(0).rstrip(".")
    return ""


def _published_dt(paper: dict) -> datetime:
    try:
        return datetime.fromisoformat(paper["published"].replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def rank(papers: list[dict], cfg) -> list[dict]:
    topics = cfg.get("topics") or []
    W = cfg.nav("boost.weights", {}) or {}
    labs = cfg.nav("boost.labs", []) or []
    venues = cfg.nav("boost.venues", []) or []
    w_tt = float(W.get("topic_title", 7.0))
    w_ta = float(W.get("topic_abstract", 1.6))
    w_lab = float(W.get("lab", 5.0))
    w_venue = float(W.get("venue", 9.0))
    w_code = float(W.get("code", 7.0))
    w_rec = float(W.get("recency", 3.0))

    now = datetime.now(timezone.utc)
    today = now.date()
    scored: list[dict] = []

    for p in papers:
        title = p.get("title", "")
        abs_ = p.get("abstract", "")
        pool = f"{title} {abs_} {p.get('comment','')} {p.get('journal_ref','')}"

        raw = 0.0
        matched: list[tuple[str, float]] = []
        for topic in topics:
            th = _hits(title, topic.get("keywords", []))
            ah = _hits(abs_, topic.get("keywords", []))
            if not (th or ah):
                continue
            s = w_tt * min(th, 2) + w_ta * min(ah, 5)
            raw += s
            matched.append((topic["id"], s))

        if not matched:
            continue  # 与本雷达无关的论文直接丢弃

        # 机构 / 顶会 / 开源 / 新近度
        if any(lab.lower() in pool.lower() for lab in labs):
            raw += w_lab
        if any(v.lower() in f"{p.get('comment','')} {p.get('journal_ref','')}".lower() for v in venues):
            raw += w_venue
        code = _find_code(p)
        if code:
            raw += w_code
        age = (today - _published_dt(p).date()).days
        if age <= 0:
            raw += w_rec
        elif age == 1:
            raw += w_rec * 0.5

        matched.sort(key=lambda x: -x[1])
        p = dict(p)
        p["topics"] = [tid for tid, _ in matched]
        p["primary_topic"] = matched[0][0]
        p["code"] = code
        p["raw_score"] = round(raw, 2)
        p["published_date"] = _published_dt(p).date().isoformat()
        scored.append(p)

    if not scored:
        return []

    top = max(p["raw_score"] for p in scored) or 1.0
    for p in scored:
        # 归一化到 0-100，保留一点区分度
        p["score"] = int(round(100 * (p["raw_score"] / top) ** 0.85))

    scored.sort(key=lambda x: (-x["score"], -datetime.fromisoformat(x["published"].replace("Z", "+00:00")).timestamp()))

    # ---- 精选：全局 Top N + 每个方向至少 Top 2 ----
    n_pick = int(cfg.nav("site.picks", 15))
    picks: list[str] = [p["id"] for p in scored[:n_pick]]
    for topic in topics:
        per = [p for p in scored if p["primary_topic"] == topic["id"]][:2]
        for p in per:
            if p["id"] not in picks:
                picks.append(p["id"])
    pick_set = set(picks)
    for p in scored:
        p["pick"] = p["id"] in pick_set

    return scored
