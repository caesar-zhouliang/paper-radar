"""Guarantee Chinese abstracts for display, with Codex as a local fallback."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _codex_batch(items: list[dict]) -> list[dict]:
    """Use Codex for a small batch when no API key translator is configured."""
    prompt = (
        "把下面的论文标题和摘要翻译成准确、通顺的简体中文。保留模型名、方法缩写和英文术语。"
        "只输出 JSON：{\"items\":[{\"id\":\"...\",\"title_zh\":\"...\",\"abstract_zh\":\"...\"}]}\n"
        + json.dumps({"items": items}, ensure_ascii=False)
    )
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
            data = json.loads(output.read_text("utf-8"))
            return data.get("items", [])
        except Exception:
            return []


def ensure(papers: list[dict], *, batch_size: int = 8) -> int:
    # Translate every displayed abstract, ordered by importance so the best
    # papers are covered first when the daily budget is tight.
    todo = sorted(
        [p for p in papers if not (p.get("title_zh") and p.get("abstract_zh"))],
        key=lambda p: (not p.get("pick"), -int(p.get("score", 0))),
    )
    if not todo:
        return 0
    chunks = [todo[start:start + batch_size] for start in range(0, len(todo), batch_size)]

    def translate_chunk(chunk):
        items = [{"id": p["id"], "title": p["title"], "abstract": (p.get("abstract") or "")[:2200]} for p in chunk]
        return chunk, _codex_batch(items)

    workers = max(1, min(6, int(os.getenv("PAPER_RADAR_TRANSLATE_WORKERS", "5"))))
    translated = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        batches = list(pool.map(translate_chunk, chunks))
    for chunk, results in batches:
        by_id = {item.get("id"): item for item in results}
        for paper in chunk:
            item = by_id.get(paper["id"])
            if not item:
                continue
            paper["title_zh"] = (item.get("title_zh") or "").strip()
            paper["abstract_zh"] = (item.get("abstract_zh") or "").strip()
            translated += 1
    return translated
