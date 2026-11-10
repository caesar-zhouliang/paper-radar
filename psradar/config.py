"""配置加载：config.yaml + 环境变量覆盖。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"


class Config(dict):
    """薄薄的一层 dict，支持 cfg.nav('a.b') 取值。"""

    def nav(self, path: str, default=None):
        cur = self
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = Config(raw)

    # 环境变量优先（方便在 GitHub Actions 里配置，不必写死进仓库）
    tr = cfg.setdefault("translate", {})
    if os.getenv("OPENAI_MODEL"):
        tr["model"] = os.environ["OPENAI_MODEL"]
    if os.getenv("OPENAI_BASE_URL"):
        tr["base_url"] = os.environ["OPENAI_BASE_URL"]
    if os.getenv("TRANSLATE_ENABLED"):
        tr["enabled"] = os.environ["TRANSLATE_ENABLED"].lower() in ("1", "true", "yes")

    site = cfg.setdefault("site", {})
    if os.getenv("SITE_BASE_URL"):
        site["base_url"] = os.environ["SITE_BASE_URL"]

    return cfg
