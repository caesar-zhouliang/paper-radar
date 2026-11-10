"""推送：邮件 / Server酱(微信) / 企业微信机器人。全部走环境变量，未配置则自动跳过。"""
from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from html import escape


def _digest(cfg, papers: list[dict], date_str: str) -> tuple[str, str, str]:
    """返回 (标题, 纯文本, HTML)。"""
    site = cfg.get("site", {})
    base = (site.get("base_url") or "").rstrip("/")
    picks = [p for p in papers if p.get("pick")] or papers[:10]
    topics = {t["id"]: t["name"] for t in cfg.get("topics", [])}

    subject = f"📡 {site.get('title', 'Paper Radar')} · {date_str} 精选 {len(picks)} 篇"

    lines = [f"{date_str} 论文精选（共 {len(papers)} 篇收录）", ""]
    html = [f'<h2 style="font:600 18px/1.4 sans-serif">{escape(date_str)} 精选 {len(picks)} 篇</h2>',
            f'<p style="color:#888;font:13px sans-serif">共收录 {len(papers)} 篇 · 全文见 <a href="{base}">{base or "站点"}</a></p>']
    for i, p in enumerate(picks, 1):
        t = topics.get(p.get("primary_topic", ""), "")
        title = p.get("title_zh") or p["title"]
        lines += [
            f"{i}. [{t}] {title}（重要度 {p.get('score', 0)}）",
            f"   {p['abs_url']}",
            f"   {(p.get('abstract_zh') or p.get('abstract') or '')[:180]}…",
            "",
        ]
        html.append(
            f'<div style="margin:0 0 16px"><div style="font:600 15px/1.4 sans-serif">'
            f'{i}. <a href="{escape(p["abs_url"])}" style="color:#4f46e5;text-decoration:none">{escape(title)}</a></div>'
            f'<div style="font:12px/1.5 sans-serif;color:#888">{escape(t)} · 重要度 {p.get("score", 0)}</div>'
            f'<div style="font:13px/1.6 sans-serif;color:#444;margin-top:4px">'
            f'{escape((p.get("abstract_zh") or p.get("abstract") or "")[:260])}…</div></div>'
        )
    if base:
        html.append(f'<p><a href="{base}" style="font:14px sans-serif">👉 查看完整列表</a></p>')
    return subject, "\n".join(lines), "".join(html)


def send_email(cfg, subject: str, text: str, html: str) -> None:
    if not cfg.nav("notify.email.enabled"):
        return
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    to = cfg.nav("notify.email.to", []) or []
    if not (host and user and pwd and to):
        print("  ! 邮件推送已开启但缺少 SMTP_* 或收件人配置，跳过")
        return
    port = int(os.getenv("SMTP_PORT", "465"))
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = ", ".join(to)
    server = smtplib.SMTP_SSL(host, port) if port == 465 else smtplib.SMTP(host, port)
    with server:
        if port != 465:
            server.starttls()
        server.login(user, pwd)
        server.sendmail(user, to, msg.as_string())
    print(f"  ✓ 邮件已发送至 {', '.join(to)}")


def _post_json(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", "ignore")
    print(f"  ✓ 推送返回: {body[:160]}")


def send_serverchan(cfg, subject: str, text: str) -> None:
    if not cfg.nav("notify.serverchan.enabled"):
        return
    key = os.getenv("SERVERCHAN_KEY")
    if not key:
        print("  ! 缺少 SERVERCHAN_KEY，跳过微信推送")
        return
    _post_json(f"https://sctapi.ftqq.com/{key}.send", {"title": subject, "desp": text})


def send_wecom(cfg, subject: str, text: str) -> None:
    if not cfg.nav("notify.wecom.enabled"):
        return
    url = os.getenv("WECOM_WEBHOOK")
    if not url:
        print("  ! 缺少 WECOM_WEBHOOK，跳过企业微信推送")
        return
    content = f"**{subject}**\n" + "\n".join(f"- {line}" for line in text.splitlines()[:40] if line.strip())
    _post_json(url, {"msgtype": "markdown", "markdown": {"content": content[:3800]}})


def notify_all(cfg, papers: list[dict], date_str: str) -> None:
    subject, text, html = _digest(cfg, papers, date_str)
    for fn, args in ((send_email, (subject, text, html)), (send_serverchan, (subject, text)), (send_wecom, (subject, text))):
        try:
            fn(cfg, *args)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! 推送失败({fn.__name__}): {exc}")
    if cfg.nav("notify.feishu.enabled", False):
        from .brief import send as send_feishu
        try:
            send_feishu(cfg, papers, date_str)
            print("  ✓ 飞书摘要已发送")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! 飞书推送失败: {exc}")
