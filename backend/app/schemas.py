"""Pydantic 请求 / 响应模型（全部 JSON）。"""
from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_email(v: str) -> str:
    v = (v or "").strip()
    if not _EMAIL_RE.match(v):
        raise ValueError("邮箱格式不正确")
    return v


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------

class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = False


class TokenOut(BaseModel):
    token: str
    username: str
    expires_in: int


class MeOut(BaseModel):
    username: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _min_length(cls, v: str) -> str:
        if len(v or "") < 8:
            raise ValueError("新密码至少 8 位")
        return v


class ChangeUsernameIn(BaseModel):
    new_username: str
    current_password: str

    @field_validator("new_username")
    @classmethod
    def _username_valid(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("新用户名不能为空")
        if len(v) > 128:
            raise ValueError("新用户名过长（最多 128 字符）")
        return v


class OkOut(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# 订阅用户
# ---------------------------------------------------------------------------

class SubscriberBase(BaseModel):
    name: str = ""
    email: str = ""
    field: str = ""
    research_problem: str = ""
    methods: str = ""
    keywords: list[str] = []
    venues: list[str] = []
    papers_per_week: int = 8
    enabled: bool = True

    @field_validator("papers_per_week")
    @classmethod
    def _papers_range(cls, v: int) -> int:
        if not 1 <= v <= 50:
            raise ValueError("推荐论文数量需在 1~50 之间")
        return v


class SubscriberCreate(SubscriberBase):
    @field_validator("name")
    @classmethod
    def _name_strip(cls, v: str) -> str:
        # 名称选填：为空时后端用邮箱前缀自动填充
        return (v or "").strip()

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        return _check_email(v)


class SubscriberUpdate(SubscriberBase):
    name: str = ""
    email: str = ""

    @field_validator("email")
    @classmethod
    def _email_valid_opt(cls, v: str) -> str:
        if v:
            return _check_email(v)
        return v


class SubscriberOut(SubscriberBase):
    id: int
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class LastRunOut(BaseModel):
    id: int
    subscriber_id: int
    subscriber_name: str = ""
    week_start: dt.date | None = None
    status: str = ""
    papers_selected: int = 0
    email_status: str = ""
    started_at: dt.datetime | None = None


class DashboardOut(BaseModel):
    subscriber_count: int = 0
    active_subscriber_count: int = 0
    papers_7d: int = 0
    recommendations_7d: int = 0
    last_run: LastRunOut | None = None
    next_run_at: dt.datetime | None = None
    recent_runs: list[LastRunOut] = []
    llm_configured: bool = False
    smtp_configured: bool = False
    schedule_enabled: bool = False


# ---------------------------------------------------------------------------
# LLM / SMTP / 定时配置
# ---------------------------------------------------------------------------

class LlmConfigOut(BaseModel):
    provider: str = ""
    base_url: str = ""
    model: str = ""
    has_api_key: bool = False
    updated_at: str | None = None


class LlmConfigIn(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""  # 空字符串表示保持原值
    model: str = ""


class LlmTestOut(BaseModel):
    ok: bool
    message: str
    latency_ms: int = 0


class SmtpConfigOut(BaseModel):
    host: str = ""
    port: int = 587
    username: str = ""
    from_email: str = ""
    from_name: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    has_password: bool = False


class SmtpConfigIn(BaseModel):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""  # 空字符串表示保持原值
    from_email: str = ""
    from_name: str = ""
    use_tls: bool = True
    use_ssl: bool = False


class SmtpTestIn(BaseModel):
    to: str

    @field_validator("to")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        return _check_email(v)


class SmtpTestOut(BaseModel):
    ok: bool
    message: str


class ScheduleConfigOut(BaseModel):
    enabled: bool = True
    day_of_week: int = 0  # 0=周一 … 6=周日
    hour: int = 8
    minute: int = 0
    timezone: str = "Asia/Shanghai"


class ScheduleConfigIn(BaseModel):
    enabled: bool = True
    day_of_week: int = 0
    hour: int = 8
    minute: int = 0

    @field_validator("day_of_week")
    @classmethod
    def _dow(cls, v: int) -> int:
        if not 0 <= v <= 6:
            raise ValueError("day_of_week 需在 0~6 之间（0=周一）")
        return v

    @field_validator("hour")
    @classmethod
    def _hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("hour 需在 0~23 之间")
        return v

    @field_validator("minute")
    @classmethod
    def _minute(cls, v: int) -> int:
        if not 0 <= v <= 59:
            raise ValueError("minute 需在 0~59 之间")
        return v


# ---------------------------------------------------------------------------
# Pipeline 任务
# ---------------------------------------------------------------------------

class PipelineRunIn(BaseModel):
    subscriber_ids: list[int] | None = None  # 缺省=全部启用用户
    send_email: bool = True
    force: bool = False


class PipelineRunOut(BaseModel):
    job_id: str


class JobOut(BaseModel):
    job_id: str
    status: str  # queued / running / done / failed
    progress: int  # 0~100
    message: str = ""


# ---------------------------------------------------------------------------
# 周报任务记录
# ---------------------------------------------------------------------------

class RunOut(BaseModel):
    id: int
    subscriber_id: int
    subscriber_name: str = ""
    week_start: dt.date | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    status: str = ""
    papers_found: int = 0
    papers_selected: int = 0
    email_status: str = ""
    email_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RetryEmailOut(BaseModel):
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# 论文
# ---------------------------------------------------------------------------

class PaperItemOut(BaseModel):
    id: int
    title: str
    zh_title: str | None = None
    authors: list[str] = []
    venue: str | None = None
    published_date: dt.date | None = None
    url: str | None = None
    source: str | None = None
    is_preprint: bool = False
    abstract: str | None = None
    zh_abstract: str | None = None
    innovations: list[str] | None = None
    recommend_reason: str | None = None
    relevance_score: float | None = None
    subscriber_id: int | None = None
    subscriber_name: str | None = None
    run_id: int | None = None


class PapersPageOut(BaseModel):
    total: int
    items: list[PaperItemOut]


# ---------------------------------------------------------------------------
# 周报预览
# ---------------------------------------------------------------------------

class DigestPreviewOut(BaseModel):
    subject: str
    html: str
    run_id: int


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

class LogOut(BaseModel):
    id: int
    ts: dt.datetime | None = None
    category: str = ""
    level: str = ""
    message: str = ""

    model_config = ConfigDict(from_attributes=True)


class LogsPageOut(BaseModel):
    total: int
    items: list[LogOut]


class LogsDeletedOut(BaseModel):
    deleted: int


# ---------------------------------------------------------------------------
# 会议 / 期刊
# ---------------------------------------------------------------------------

class VenuesOut(BaseModel):
    conferences: list[str]
    journals: list[str]
