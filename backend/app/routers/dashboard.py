"""Dashboard：用户数、论文数、最近任务状态、配置状态一览。"""
import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import schemas, utils
from ..deps import get_current_user, get_db
from ..models import DigestRun, Paper, Recommendation, Subscriber
from ..services import emailer, llm as llm_service
from ..services import scheduler as scheduler_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _run_out(run: DigestRun, name: str) -> schemas.LastRunOut:
    return schemas.LastRunOut(
        id=run.id,
        subscriber_id=run.subscriber_id,
        subscriber_name=name,
        week_start=run.week_start,
        status=run.status,
        papers_selected=run.papers_selected,
        email_status=run.email_status,
        started_at=run.started_at,
    )


@router.get("", response_model=schemas.DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """聚合统计：订阅用户数、近 7 天论文/推荐数、最近任务、下次执行时间等。"""
    subscriber_count = db.query(func.count(Subscriber.id)).scalar() or 0
    active_count = (
        db.query(func.count(Subscriber.id)).filter(Subscriber.enabled.is_(True)).scalar() or 0
    )
    week_ago = utils.now() - dt.timedelta(days=7)
    papers_7d = db.query(func.count(Paper.id)).filter(Paper.fetched_at >= week_ago).scalar() or 0
    recs_7d = (
        db.query(func.count(Recommendation.id))
        .filter(Recommendation.created_at >= week_ago)
        .scalar()
        or 0
    )

    recent_runs: list[schemas.LastRunOut] = []
    for run, name in (
        db.query(DigestRun, Subscriber.name)
        .join(Subscriber, DigestRun.subscriber_id == Subscriber.id)
        .order_by(DigestRun.started_at.desc())
        .limit(5)
        .all()
    ):
        recent_runs.append(_run_out(run, name or ""))

    last_run = recent_runs[0] if recent_runs else None
    next_run_at = scheduler_service.get_next_run()
    schedule_enabled = (utils.get_setting(db, "schedule.enabled", "true") or "").lower() == "true"

    return schemas.DashboardOut(
        subscriber_count=subscriber_count,
        active_subscriber_count=active_count,
        papers_7d=papers_7d,
        recommendations_7d=recs_7d,
        last_run=last_run,
        next_run_at=next_run_at,
        recent_runs=recent_runs,
        llm_configured=llm_service.is_configured(db),
        smtp_configured=emailer.smtp_configured(db),
        schedule_enabled=schedule_enabled,
    )
