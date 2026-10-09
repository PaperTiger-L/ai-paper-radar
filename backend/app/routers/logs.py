"""运行日志：按分类 / 级别 / 关键词查看，支持删除 N 天前的日志。"""
import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import schemas, utils
from ..deps import get_current_user, get_db
from ..models import AppLog

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=schemas.LogsPageOut)
def list_logs(
    category: str | None = Query(default=None),
    level: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """分页查看日志，最新的在前。"""
    query = db.query(AppLog)
    if category:
        query = query.filter(AppLog.category == category)
    if level:
        query = query.filter(AppLog.level == level.upper())
    if q:
        like = f"%{q}%"
        query = query.filter(or_(AppLog.message.ilike(like), AppLog.category.ilike(like)))
    total = query.with_entities(func.count(AppLog.id)).scalar() or 0
    items = (
        query.order_by(AppLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": items}


@router.delete("", response_model=schemas.LogsDeletedOut)
def delete_old_logs(
    days: int = Query(default=30, ge=1),
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """删除 N 天前的日志，返回删除条数。"""
    cutoff = utils.now() - dt.timedelta(days=days)
    deleted = db.query(AppLog).filter(AppLog.ts < cutoff).delete()
    db.commit()
    utils.log_event(db, "system", "INFO", f"清理 {days} 天前的日志，共删除 {deleted} 条")
    return {"deleted": deleted}
