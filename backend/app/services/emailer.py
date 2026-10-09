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

    设计语言对齐「双目深度估计论文速览」报告：青色点缀 + 白色卡片 + 等宽小标题。
    邮件客户端兼容：表格布局、全内联样式、系统字体栈（QQ 邮箱可用）。

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

    FONT = ("-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',"
            "sans-serif")
    MONO = "'SF Mono',Consolas,'Courier New',monospace"
    TEAL, TEAL_BG = "#007b78", "#d8f0ed"
    INK, MUTED, FAINT = "#142328", "#52676d", "#7a8f95"
    CARD, LINE = "#ffffff", "#e2eaec"

    def eyebrow(text: str) -> str:
        return (
            f'<div style="font-family:{MONO};font-size:11px;font-weight:600;'
            f'letter-spacing:3px;color:{TEAL};margin-bottom:10px;">{_esc(text)}</div>'
        )

    def label(text: str) -> str:
        return (
            f'<div style="font-size:11px;font-weight:600;color:{TEAL};'
            f'letter-spacing:2px;margin:0 0 4px 0;">{_esc(text)}</div>'
        )

    def para(text: str) -> str:
        return (
            f'<div style="font-size:13px;color:#3d4f55;line-height:1.8;'
            f'margin:0 0 12px 0;">{_esc(text)}</div>'
        )

    # -- 头部横幅 --
    header = (
        f'<table width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{TEAL};border-radius:12px;margin-bottom:20px;">'
        f'<tr><td style="padding:28px 28px 24px 28px;">'
        f'<div style="font-family:{MONO};font-size:11px;letter-spacing:3px;'
        f'color:#a8ddd8;margin-bottom:10px;">AI PAPER RADAR · WEEKLY DIGEST</div>'
        f'<div style="font-size:26px;font-weight:800;color:#ffffff;'
        f'line-height:1.3;">论文周报</div>'
        f'<div style="font-size:13px;color:{TEAL_BG};margin-top:8px;">'
        f'{week_label} · {len(items)} 篇推荐</div>'
        f'</td></tr></table>'
    )

    # -- 本周研究动态 --
    overview = (
        f'<table width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{CARD};border:1px solid {LINE};border-radius:12px;'
        f'margin-bottom:20px;"><tr><td style="padding:20px 22px;">'
        f'{eyebrow("本周研究动态")}'
        f'{para(sections.get("overview_zh") or "暂无")}'
        f'</td></tr></table>'
    )

    # -- 论文卡片 --
    papers_html = eyebrow(f"本周推荐论文 · {len(items)} 篇")
    if items:
        for i, p in enumerate(items, 1):
            venue = _esc(p.get("venue") or "未知来源")
            badge = ""
            if p.get("is_preprint"):
                badge = (
                    ' <span style="display:inline-block;background:#fae6dc;'
                    'color:#c84f22;border-radius:4px;padding:1px 8px;'
                    'font-size:11px;">预印本</span>'
                )
            innovations = p.get("innovations") or []
            if innovations:
                innovations_html = "".join(
                    f"<li style='margin:5px 0;'>{_esc(x)}</li>" for x in innovations)
            else:
                innovations_html = "<li style='margin:5px 0;color:#999;'>暂无</li>"
            date_str = _esc(str(p.get("published_date") or ""))
            url = _esc(p.get("url") or "#")
            papers_html += (
                f'<table width="100%" cellpadding="0" cellspacing="0" '
                f'style="background:{CARD};border:1px solid {LINE};'
                f'border-radius:12px;margin:0 0 14px 0;">'
                f'<tr><td style="padding:20px 22px;">'
                f'<div style="font-size:16px;font-weight:700;color:{INK};'
                f'line-height:1.5;margin-bottom:4px;">'
                f"{i}. {_esc(p.get('zh_title') or p.get('title'))}</div>"
                f'<div style="font-size:13px;color:{MUTED};line-height:1.6;'
                f'margin-bottom:8px;">{_esc(p.get("title"))}</div>'
                f'<div style="font-size:12px;color:{FAINT};margin-bottom:14px;">'
                f"{_format_authors(p.get('authors'))} · {venue}{badge} · {date_str}</div>"
                f'{label("摘要")}'
                f'{para(p.get("zh_abstract") or "暂无")}'
                f'{label("核心创新点")}'
                f'<ul style="margin:0 0 12px 18px;padding:0;font-size:13px;'
                f'color:#3d4f55;line-height:1.7;">{innovations_html}</ul>'
                f'{label("推荐理由")}'
                f'{para(p.get("recommend_reason") or "暂无")}'
                f'<div style="margin-top:4px;">'
                f'<a href="{url}" style="color:{TEAL};font-size:13px;'
                f'text-decoration:none;font-weight:600;">阅读原文 →</a></div>'
                f'</td></tr></table>'
            )
    else:
        papers_html += (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{CARD};border:1px solid {LINE};border-radius:12px;'
            f'margin-bottom:20px;"><tr>'
            f'<td style="padding:28px 22px;text-align:center;font-size:13px;'
            f'color:{FAINT};">本周没有检索到与您研究方向高度相关的论文，'
            f'下周会继续为您关注。</td></tr></table>'
        )

    # -- 本周研究启发 --
    inspiration = (
        f'<table width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{CARD};border:1px solid {LINE};border-radius:12px;'
        f'margin-bottom:20px;"><tr><td style="padding:20px 22px;">'
        f'{eyebrow("本周研究启发")}'
        f'{para(sections.get("inspiration_zh") or "暂无")}'
        f'</td></tr></table>'
    )

    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_esc(subject)}</title></head>"
        '<body style="margin:0;padding:0;background:#f5f7f8;">'
        f'<div style="max-width:680px;margin:0 auto;padding:24px 12px;'
        f'font-family:{FONT};color:{INK};">'
        f"{header}{overview}{papers_html}{inspiration}"
        '<div style="text-align:center;font-size:11px;color:#93a5aa;'
        'line-height:1.7;padding:8px 0;">'
        '本邮件由 AI Paper Radar 自动生成。如需调整研究方向或退订，请联系管理员。'
        '</div></div></body></html>'
    )
    return subject, html
