"""数据库连接：SQLite 引擎、会话工厂、建表入口。"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """所有数据模型的基类。"""


def _database_url() -> str:
    """由 DATABASE_PATH 解析出 SQLite URL，并确保目录存在。"""
    path = os.path.abspath(os.path.expanduser(os.path.expandvars(settings.database_path)))
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return f"sqlite:///{path}"


# check_same_thread=False：允许后台 pipeline 线程使用独立会话并发访问
engine = create_engine(_database_url(), connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """创建所有数据表（已存在则跳过），并补齐历史版本缺失的列。"""
    from . import models  # noqa: F401 延迟导入，避免循环引用

    Base.metadata.create_all(engine)
    _ensure_columns()


# 历史版本新增列的补齐清单：(表名, 列名, 列定义)
# create_all 不会给已存在的表加列，升级部署靠这里保证 schema 一致。
_MISSING_COLUMN_DDLS: list[tuple[str, str, str]] = [
    ("subscribers", "disciplines", "TEXT DEFAULT '[]'"),
    ("subscribers", "research_direction", "TEXT DEFAULT ''"),
]


def _ensure_columns() -> None:
    """检查并补齐缺失的列（幂等，SQLite 用 ALTER TABLE ADD COLUMN）。"""
    import logging

    from sqlalchemy import text

    logger = logging.getLogger("paper_radar")
    with engine.begin() as conn:
        for table, column, ddl in _MISSING_COLUMN_DDLS:
            exists = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table},
            ).first()
            if not exists:
                continue
            cols = [row[1] for row in conn.execute(
                text(f"PRAGMA table_info({table})")).fetchall()]
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                logger.info("DB 迁移：%s 新增列 %s", table, column)
