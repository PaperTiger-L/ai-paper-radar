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
    """创建所有数据表（已存在则跳过）。"""
    from . import models  # noqa: F401 延迟导入，避免循环引用

    Base.metadata.create_all(engine)
