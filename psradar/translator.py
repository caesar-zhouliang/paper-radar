"""中文翻译（OpenAI 兼容接口）+ 本地缓存，避免重复花钱。"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_FILE = "translations.json"

SYSTEM = (
    "你是 AI 论文编辑。把论文标题与摘要翻译成简洁、准确、地道的简体中文。"
    "要求：1) 专有名词、模型名、方法缩写（如 diffusion、Transformer、VLA、BEV、PPO）保留英文原文；"
    "2) 摘要不要逐字硬译，通顺为先，长度控制在原文的 60%-80%；"
    "3) 不要添加原文没有的评论或结论。"
    '只输出 JSON：{"items":[{"id":"...","title_zh":"...","abstract_zh":"..."}]}'
)


def _load_cache(cache_dir: Path) -> dict:
    path = cache_dir / CACHE_FILE
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache_dir: Path, cache: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / CACHE_FILE).write_text(json.dumps(cache, ensure_ascii=False, indent=0), "utf-8")


def _post(base_url: str, api_key: str, payload: dict, timeout: int = 120) -> str:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lower().startswith("json") else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            return json.loads(text[i : j + 1])
        raise


def translate_papers(papers: list[dict], cfg, cache_dir: Path, verbose: bool = True) -> dict:
    """返回 {paper_id: {title_zh, abstract_zh}}，就地补到 papers 上。"""
    if not cfg.nav("translate.enabled", True):
        return {}
    api_key = os.getenv(cfg.nav("translate.api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY")
    if not api_key:
        if verbose:
            print("  ! 未配置 API Key，跳过翻译（站点仍会正常生成英文版）")
        return {}

    base_url = cfg.nav("translate.base_url", "https://api.openai.com/v1")
    model = cfg.nav("translate.model", "gpt-4o-mini")
    batch_size = int(cfg.nav("translate.batch_size", 8))
    max_papers = int(cfg.nav("translate.max_papers", 90))

    cache = _load_cache(cache_dir)
    todo = [p for p in papers if p["id"] not in cache][:max_papers]
    if verbose:
        print(f"  · 需翻译 {len(todo)} 篇（缓存命中 {len(papers) - len(todo)}）")

    done = 0
    for i in range(0, len(todo), batch_size):
        chunk = todo[i : i + batch_size]
        items = [{"id": p["id"], "title": p["title"], "abstract": p["abstract"][:2200]} for p in chunk]
        payload = {
            "model": model,
            "temperature": float(cfg.nav("translate.temperature", 0.2)),
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps({"items": items}, ensure_ascii=False)},
            ],
        }
        for attempt in range(3):
            try:
                result = _extract_json(_post(base_url, api_key, payload))
                for item in result.get("items", []):
                    pid = item.get("id")
                    if not pid:
                        continue
                    cache[pid] = {
                        "title_zh": (item.get("title_zh") or "").strip(),
                        "abstract_zh": (item.get("abstract_zh") or "").strip(),
                    }
                done += len(chunk)
                if verbose:
                    print(f"  · 翻译进度 {done}/{len(todo)}")
                break
            except urllib.error.HTTPError as exc:
                body = exc.read()[:300].decode("utf-8", "ignore")
                print(f"  ! 翻译接口 {exc.code}: {body}")
                time.sleep(6 * (attempt + 1))
            except Exception as exc:  # noqa: BLE001
                print(f"  ! 翻译失败: {exc}")
                time.sleep(4 * (attempt + 1))
        _save_cache(cache_dir, cache)
        time.sleep(1)

    for p in papers:
        hit = cache.get(p["id"])
        if hit:
            p["title_zh"] = hit.get("title_zh", "")
            p["abstract_zh"] = hit.get("abstract_zh", "")
    return cache
