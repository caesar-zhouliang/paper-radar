"""Feishu private-message delivery for the daily brief.

Credentials are read from the environment, never stored in the repository.
Recipients can be configured with:
  FEISHU_RECEIVE_EMAILS  comma-separated emails (resolved to open_id)
  FEISHU_RECEIVE_IDS     comma-separated open_ids
  FEISHU_RECEIVE_ID      one open_id (backward compatible)
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


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _resolve_emails(emails: list[str], token: str) -> list[str]:
    if not emails:
        return []
    body = _post(
        "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
        {"emails": emails},
        token,
    )
    if body.get("code") != 0:
        raise RuntimeError("Feishu email lookup rejected: " + str(body))
    resolved = []
    for item in body.get("data", {}).get("user_list", []):
        open_id = item.get("user_id") or item.get("open_id")
        if open_id:
            resolved.append(open_id)
    return resolved


def _recipients(token: str) -> list[str]:
    ids = _env_list("FEISHU_RECEIVE_IDS")
    single = os.getenv("FEISHU_RECEIVE_ID", "").strip()
    if single:
        ids.append(single)
    emails = _env_list("FEISHU_RECEIVE_EMAILS")
    ids.extend(_resolve_emails(emails, token))
    # Stable de-duplication keeps one send per person.
    return list(dict.fromkeys(ids))


def send_markdown(title: str, markdown: str) -> list[str]:
    token = _token()
    recipients = _recipients(token)
    if not recipients:
        raise RuntimeError("missing FEISHU_RECEIVE_EMAILS / FEISHU_RECEIVE_IDS / FEISHU_RECEIVE_ID")
    sent = []
    for receive_id in recipients:
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
            raise RuntimeError(f"Feishu message rejected for {receive_id}: {body}")
        sent.append(receive_id)
    return sent
