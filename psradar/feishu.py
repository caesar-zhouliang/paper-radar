"""Feishu private-message delivery for the daily brief.

Credentials are read from the environment, never stored in the repository:
FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_RECEIVE_ID (open_id).
"""
from __future__ import annotations

import json
import os
import urllib.request


def _post(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _token() -> str:
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("missing FEISHU_APP_ID / FEISHU_APP_SECRET")
    body = _post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    if body.get("code") != 0:
        raise RuntimeError("Feishu token rejected: " + str(body))
    return body["tenant_access_token"]


def send_markdown(title: str, markdown: str) -> None:
    receive_id = os.getenv("FEISHU_RECEIVE_ID", "").strip()
    if not receive_id:
        raise RuntimeError("missing FEISHU_RECEIVE_ID")
    token = _token()
    body = _post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(
                {
                    "config": {"wide_screen_mode": True, "enable_forward": True},
                    "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
                    "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": markdown}}],
                },
                ensure_ascii=False,
            ),
        },
        token,
    )
    if body.get("code") != 0:
        raise RuntimeError("Feishu message rejected: " + str(body))
