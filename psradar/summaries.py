"""Generate no-metric Chinese summaries for the daily brief."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = (
    "你是论文编辑。为下面每篇论文写三段中文，供每日飞书简报使用。"
    "summary（180-260 个汉字）：说明论文要解决什么问题、现有方法的关键不足、核心创新点；"
    "不要罗列评测指标、分数、提升百分比、SOTA 宣传，也不要写空泛结论。"
    "method（120-200 个汉字）：说明实验具体怎么做，包括数据、模型、训练/推理流程、"
    "对照设置、工程实现或 trick；仍然不要写分数和评测指标。"
    "driving（80-140 个汉字）：具体说明这篇论文对自动驾驶方案有什么帮助，"
    "可以是感知、预测、规划、控制、仿真、数据闭环或训练工程上的启发；"
    "如果并非直接面向驾驶，也要给出可迁移的具体做法，不要只说“有参考价值”。"
    "只输出 JSON：{\"items\":[{\"id\":\"...\",\"summary\":\"...\","
    "\"method\":\"...\",\"driving\":\"...\"}]}\n"
)


def _codex_batch(items: list[dict]) -> list[dict]:
    prompt = PROMPT + json.dumps({"items": items}, ensure_ascii=False)
    codex = str(Path.home() / ".local/bin/codex")
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "out.json"
        try:
            result = subprocess.run(
                [codex, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "-o", str(output), "-"],
                input=prompt.encode("utf-8"), capture_output=True, timeout=900, check=False,
            )
        except subprocess.TimeoutExpired:
            result = None
        if not output.exists() or (result is not None and result.returncode != 0):
            return []
        try:
            return json.loads(output.read_text("utf-8")).get("items", [])
        except Exception:
            return []




def _complete(paper: dict) -> bool:
    brief = paper.get("brief_zh") or {}
    return all(str(brief.get(key) or "").strip() for key in ("summary", "method", "driving"))


def ensure(papers: list[dict], *, batch_size: int = 6) -> int:
    todo = [p for p in papers if p.get("pick") and not _complete(p)]
    todo.sort(key=lambda p: -int(p.get("score", 0)))
    chunks = [todo[start:start + batch_size] for start in range(0, len(todo), batch_size)]

    def summarize_chunk(chunk):
        items = [
            {
                "id": p["id"],
                "title": p.get("title_zh") or p["title"],
                "abstract": (p.get("abstract_zh") or p.get("abstract") or "")[:2200],
            }
            for p in chunk
        ]
        return chunk, _codex_batch(items)

    workers = max(1, min(3, int(os.getenv("PAPER_RADAR_SUMMARY_WORKERS", "3"))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        batches = list(pool.map(summarize_chunk, chunks))

    updated = 0
    for chunk, results in batches:
        by_id = {item.get("id"): item for item in results}
        for paper in chunk:
            item = by_id.get(paper["id"])
            if not item:
                continue
            brief = paper.get("brief_zh") or {}
            changed = False
            for key in ("summary", "method", "driving"):
                value = str(item.get(key) or "").strip()
                if value:
                    brief[key] = value
                    changed = True
            if not changed:
                continue
            paper["brief_zh"] = brief
            updated += 1
    return updated
