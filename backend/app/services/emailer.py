"""邮件服务：SMTP 发送 + 论文周报 HTML 模板。

发送规则：
    - use_ssl=True  → SMTP_SSL（默认 465）
    - use_tls=True   → SMTP + STARTTLS（默认 587）
    - 否则           → 明文 SMTP（默认 25）
    - username 非空时做 SMTP 登录认证

周报模板：表格式布局、max-width 640px、移动端友好；
包含【本周研究动态】【本周推荐论文】【本周研究启发】三部分，页脚注明退订方式。
"""
from __future__ import annotations

import html as html_lib
import smtplib
from email.message import EmailMessage

from .. import utils

# Setting 表中的键
K_HOST = "smtp.host"
K_PORT = "smtp.port"
K_USERNAME = "smtp.username"
K_PASSWORD = "smtp.password"
K_FROM_EMAIL = "smtp.from_email"
K_FROM_NAME = "smtp.from_name"
K_USE_TLS = "smtp.use_tls"
K_USE_SSL = "smtp.use_ssl"


def get_smtp_config(db) -> dict:
    """读取 SMTP 配置（调用方注意：password 仅用于发信，绝不记入日志）。"""
    def _bool(key: str, default: str) -> bool:
        return (utils.get_setting(db, key, default) or "").lower() == "true"

    try:
        port = int(utils.get_setting(db, K_PORT, "587") or "587")
    except ValueError:
        port = 587
    return {
        "host": utils.get_setting(db, K_HOST, "") or "",
        "port": port,
        "username": utils.get_setting(db, K_USERNAME, "") or "",
        "password": utils.get_setting(db, K_PASSWORD, "") or "",
        "from_email": utils.get_setting(db, K_FROM_EMAIL, "") or "",
        "from_name": utils.get_setting(db, K_FROM_NAME, "") or "AI Paper Radar",
        "use_tls": _bool(K_USE_TLS, "true"),
        "use_ssl": _bool(K_USE_SSL, "false"),
    }


def smtp_configured(db) -> bool:
    """SMTP 是否已配置（host + 发件人邮箱均非空即视为可用）。"""
    cfg = get_smtp_config(db)
    return bool(cfg["host"] and cfg["from_email"])


def _build_message(cfg: dict, to_email: str, subject: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    from_name = cfg["from_name"]
    from_addr = cfg["from_email"]
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(html, subtype="html", charset="utf-8")
    return msg


def send_email(db, to_email: str, subject: str, html: str) -> None:
    """通过 SMTP 发送一封 HTML 邮件。失败抛异常（携带真实错误信息）。"""
    cfg = get_smtp_config(db)
    if not cfg["host"] or not cfg["from_email"]:
        raise RuntimeError("SMTP 未配置（host / 发件人邮箱缺失）")
    msg = _build_message(cfg, to_email, subject, html)
    try:
        if cfg["use_ssl"]:
            port = cfg["port"] or 465
            server = smtplib.SMTP_SSL(cfg["host"], port, timeout=30)
        else:
            port = cfg["port"] or 587
            server = smtplib.SMTP(cfg["host"], port, timeout=30)
        with server:
            server.ehlo()
            if cfg["use_tls"] and not cfg["use_ssl"]:
                server.starttls()
                server.ehlo()
            # 用户名为空时默认用发件人邮箱登录（QQ/163/Gmail 均要求邮箱地址登录）
            login_user = cfg["username"] or cfg["from_email"]
            if login_user:
                server.login(login_user, cfg["password"])
            server.send_message(msg)
    except Exception as e:
        utils.log_event(db, "email", "ERROR",
                        f"邮件发送失败 to={to_email} 错误={type(e).__name__}: {e}")
        raise
    utils.log_event(db, "email", "INFO", f"邮件发送成功 to={to_email} subject={subject}")


def send_test_email(db, to_email: str) -> None:
    """发送测试邮件（供后台"测试邮件发送"按钮使用）。"""
    subject = "AI Paper Radar 测试邮件"
    html = (
        '<div style="font-family:-apple-system,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;'
        'max-width:640px;margin:0 auto;padding:24px;color:#333;">'
        "<h2>AI Paper Radar 测试邮件</h2>"
        "<p>如果你收到了这封邮件，说明 SMTP 配置正确，周报可以正常发送。</p>"
        '<p style="color:#888;font-size:12px;">本邮件由 AI Paper Radar 自动生成。</p></div>'
    )
    send_email(db, to_email, subject, html)


def _esc(text: str | None) -> str:
    return html_lib.escape(str(text or ""))


def _format_authors(authors: list | None) -> str:
    authors = authors or []
    shown = authors[:5]
    suffix = " 等" if len(authors) > 5 else ""
    return _esc(", ".join(shown) + suffix)


def build_digest_html(subscriber_name: str, week_start, week_end,
                      items: list[dict], sections: dict) -> tuple[str, str]:
    """生成周报主题与 HTML。

    items: [{title, zh_title, authors, venue, is_preprint, url, published_date,
             zh_abstract, innovations, recommend_reason, relevance_score}]
    sections: {"overview_zh", "inspiration_zh"}
    返回 (subject, html)。
    """
    week_label = f"{week_start} ~ {week_end}"
    if items:
        subject = f"AI Paper Radar 周报 · {week_label} · {len(items)} 篇推荐"
    else:
        subject = f"AI Paper Radar 周报 · {week_label} · 本周暂无高度相关论文"

    if items:
        paper_blocks = []
        for i, p in enumerate(items, 1):
            venue = _esc(p.get("venue") or "未知来源")
            badge = ""
            if p.get("is_preprint"):
                badge = ('<span style="display:inline-block;background:#fff7e6;color:#b7791f;'
                         'border:1px solid #f0d48a;border-radius:4px;padding:1px 8px;'
                         'font-size:12px;">预印本</span>')
            innovations = p.get("innovations") or []
            if innovations:
                innovations_html = "".join(
                    f"<li style='margin:4px 0;'>{_esc(x)}</li>" for x in innovations)
            else:
                innovations_html = "<li style='margin:4px 0;color:#999;'>暂无</li>"
            date_str = _esc(str(p.get("published_date") or ""))
            url = _esc(p.get("url") or "#")
            paper_blocks.append(
                '<table width="100%" cellpadding="0" cellspacing="0" '
                'style="margin:0 0 20px 0;border:1px solid #e8e8e8;border-radius:8px;">'
                '<tr><td style="padding:16px 18px;">'
                f'<div style="font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:4px;">'
                f"{i}. {_esc(p.get('zh_title') or p.get('title'))}</div>"
                f'<div style="font-size:13px;color:#666;margin-bottom:8px;">{_esc(p.get("title"))}</div>'
                f'<div style="font-size:12px;color:#888;margin-bottom:8px;">'
                f"{_format_authors(p.get('authors'))}</div>"
                f'<div style="font-size:12px;color:#888;margin-bottom:10px;">'
                f"{venue} {badge} &nbsp;{date_str}</div>"
                f'<div style="font-size:13px;color:#444;line-height:1.7;margin-bottom:10px;">'
                f"<b>摘要：</b>{_esc(p.get('zh_abstract'))}</div>"
                f'<div style="font-size:13px;color:#444;line-height:1.7;margin-bottom:10px;">'
                f"<b>核心创新点：</b><ul style=\"margin:4px 0 0 18px;padding:0;\">"
                f"{innovations_html}</ul></div>"
                f'<div style="font-size:13px;color:#444;line-height:1.7;margin-bottom:10px;">'
                f"<b>推荐理由：</b>{_esc(p.get('recommend_reason'))}</div>"
                f'<div style="font-size:13px;"><a href="{url}" '
                f'style="color:#1a73e8;">阅读原文 &gt;</a></div>'
                "</td></tr></table>"
            )
        papers_html = "\n".join(paper_blocks)
    else:
        papers_html = ('<p style="font-size:14px;color:#888;">本周没有检索到与您研究方向高度相关的论文，'
                       "下周会继续为您关注。</p>")

    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_esc(subject)}</title></head>"
        '<body style="margin:0;padding:0;background:#f5f5f5;">'
        '<div style="max-width:640px;margin:0 auto;background:#ffffff;'
        "font-family:-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;"
        'color:#333;">'
        '<div style="background:#1a73e8;color:#fff;padding:22px 24px;">'
        '<div style="font-size:20px;font-weight:700;">AI Paper Radar · 论文周报</div>'
        f'<div style="font-size:13px;opacity:.9;margin-top:6px;">'
        f"{_esc(subscriber_name)} · {week_label}</div></div>"
        '<div style="padding:22px 24px;">'
        '<div style="font-size:16px;font-weight:700;margin:0 0 10px 0;color:#1a1a1a;">'
        "本周研究动态</div>"
        f"<p style=\"font-size:14px;line-height:1.8;color:#444;\">{_esc(sections.get('overview_zh'))}</p>"
        '<div style="font-size:16px;font-weight:700;margin:22px 0 12px 0;color:#1a1a1a;">'
        f"本周推荐论文（{len(items)} 篇）</div>"
        f"{papers_html}"
        '<div style="font-size:16px;font-weight:700;margin:22px 0 10px 0;color:#1a1a1a;">'
        "本周研究启发</div>"
        f"<p style=\"font-size:14px;line-height:1.8;color:#444;\">{_esc(sections.get('inspiration_zh'))}</p>"
        "</div>"
        '<div style="padding:16px 24px;border-top:1px solid #eee;font-size:12px;color:#999;'
        'line-height:1.7;">本邮件由 AI Paper Radar 自动生成。如需调整研究方向或退订，请联系管理员。</div>'
        "</div></body></html>"
    )
    return subject, html
