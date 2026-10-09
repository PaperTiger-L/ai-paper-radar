"""SQLAlchemy 数据模型：与需求规格中的表结构一一对应。

    Setting        系统配置键值表（管理员凭据、JWT 密钥、LLM/SMTP/定时配置）
    Subscriber     邮件订阅用户（研究方向 / 问题 / 方法等画像）
    Paper          检索到的论文（按 external_id 去重）
    DigestRun      每次为某用户生成的周报任务记录
    Recommendation 某次任务中推荐给某用户的论文及 AI 分析结果
    AppLog         运行日志（搜索 / LLM / 任务 / 邮件 / 鉴权 / 系统）
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .utils import now


class Setting(Base):
    """系统配置键值表。敏感值（API Key / SMTP 密码）以明文存于本地 SQLite，
    仅本机可访问；日志中绝不输出这些值。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)


class Subscriber(Base):
    """邮件订阅用户：管理员维护的研究画像。"""

    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)
    field: Mapped[str] = mapped_column(String(256), default="")  # 研究领域
    research_problem: Mapped[str] = mapped_column(Text, default="")  # 当前研究问题（自然语言）
    methods: Mapped[str] = mapped_column(String(512), default="")  # 关注的研究方法
    keywords: Mapped[list] = mapped_column(JSON, default=list)  # 关键词数组
    venues: Mapped[list] = mapped_column(JSON, default=list)  # 关注的会议/期刊数组
    papers_per_week: Mapped[int] = mapped_column(Integer, default=8)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否启用邮件推送
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Paper(Base):
    """检索到的论文。external_id 全局唯一，如 openalex:W123 / arxiv:2609.12345。"""

    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    venue: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)  # openalex / arxiv
    is_preprint: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class DigestRun(Base):
    """一次为单个订阅用户执行的周报任务。"""

    __tablename__ = "digest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id"), index=True, nullable=False
    )
    week_start: Mapped[dt.date] = mapped_column(Date, nullable=False)  # 本周一
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running/success/failed
    papers_found: Mapped[int] = mapped_column(Integer, default=0)  # 检索去重后候选数
    papers_selected: Mapped[int] = mapped_column(Integer, default=0)  # 最终推荐数
    email_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/sent/failed/skipped
    email_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    digest_subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    digest_html: Mapped[str | None] = mapped_column(Text, nullable=True)


class Recommendation(Base):
    """某次 DigestRun 中推荐给用户的论文及 AI 分析结果。"""

    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("run_id", "paper_id", name="uq_recommendation_run_paper"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("digest_runs.id"), index=True, nullable=False
    )
    subscriber_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscribers.id"), index=True, nullable=False
    )
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("papers.id"), index=True, nullable=False
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    zh_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    zh_abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    innovations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommend_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class AppLog(Base):
    """运行日志：搜索 / LLM 调用 / 任务 / 邮件 / 定时 / 鉴权 / 系统。"""

    __tablename__ = "app_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=now, index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)  # search/llm/pipeline/email/scheduler/auth/system
    level: Mapped[str] = mapped_column(String(16), index=True)  # INFO/WARNING/ERROR
    message: Mapped[str] = mapped_column(Text, nullable=False)
