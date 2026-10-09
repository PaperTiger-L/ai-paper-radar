"""通用工具：时区时间、Setting 键值读写、AppLog 日志写入。"""
from __future__ import annotations

import datetime as dt
import logging
import zoneinfo

from .config import settings

logger = logging.getLogger("paper_radar")


def tz() -> zoneinfo.ZoneInfo:
    """应用时区（默认 Asia/Shanghai）。"""
    return zoneinfo.ZoneInfo(settings.timezone)


def now() -> dt.datetime:
    """当前时间。返回 naive datetime（应用时区的地方时），保证 SQLite 兼容。"""
    return dt.datetime.now(tz()).replace(tzinfo=None)


def today() -> dt.date:
    return now().date()


def week_start(d: dt.date | None = None) -> dt.date:
    """给定日期所在周的周一。"""
    d = d or today()
    return d - dt.timedelta(days=d.weekday())


# ---------------------------------------------------------------------------
# Setting 键值读写
# ---------------------------------------------------------------------------

def get_setting(db, key: str, default: str | None = None) -> str | None:
    """读取 Setting 表中的配置值，不存在返回 default。"""
    from .models import Setting

    row = db.get(Setting, key)
    return row.value if row is not None else default


def set_setting(db, key: str, value: str | None) -> None:
    """写入 Setting 表（upsert）。"""
    from .models import Setting

    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

_LOG_LEVELS = ("INFO", "WARNING", "ERROR")


def log_event(db, category: str, level: str, message: str) -> None:
    """写入 AppLog 表并同步输出到标准日志。

    category: search / llm / pipeline / email / scheduler / auth / system
    level: INFO / WARNING / ERROR

    重要：调用方必须保证 message 中不包含 API Key、SMTP 密码等敏感信息明文。
    """
    from .models import AppLog

    level = level if level in _LOG_LEVELS else "INFO"
    msg = (message or "")[:2000]
    try:
        db.add(AppLog(ts=now(), category=category, level=level, message=msg))
        db.commit()
    except Exception:
        db.rollback()
    log_fn = {"INFO": logger.info, "WARNING": logger.warning, "ERROR": logger.error}[level]
    log_fn("[%s] %s", category, msg)
