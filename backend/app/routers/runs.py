"""周报任务记录：查看历史 run、重新发送邮件。"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, utils
from ..deps import get_current_user, get_db
from ..models import DigestRun, Paper, Recommendation, Subscriber
from ..services import emailer, llm as llm_service

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[schemas.RunOut])
def list_runs(
    subscriber_id: int | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """按用户过滤（可选）查看周报任务记录，最近的在前。"""
    query = (
        db.query(DigestRun, Subscriber.name)
        .join(Subscriber, DigestRun.subscriber_id == Subscriber.id)
        .order_by(DigestRun.started_at.desc())
    )
    if subscriber_id:
        query = query.filter(DigestRun.subscriber_id == subscriber_id)
    rows = query.limit(max(1, min(limit, 100))).all()
    out = []
    for run, name in rows:
        item = schemas.RunOut.model_validate(run)
        item.subscriber_name = name or ""
        out.append(item)
    return out


@router.post("/{run_id}/retry-email", response_model=schemas.RetryEmailOut)
def retry_email(
    run_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """用该 run 的推荐结果重新生成周报并发送邮件（用于发送失败后的重试）。"""
    run = db.get(DigestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    sub = db.get(Subscriber, run.subscriber_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="订阅用户不存在")

    recs = (
        db.query(Recommendation, Paper)
        .join(Paper, Recommendation.paper_id == Paper.id)
        .filter(Recommendation.run_id == run.id)
        .order_by(Recommendation.relevance_score.desc())
        .all()
    )
    if not recs:
        raise HTTPException(status_code=400, detail="该任务没有推荐论文，无法重新发送")

    # 重新生成周报 HTML（LLM 未配置时走通用模板）
    profile = {"field": sub.field or "", "research_problem": sub.research_problem or "",
               "methods": sub.methods or ""}
    paper_infos = [
        {"title": p.title, "venue": p.venue, "innovations": r.innovations or [],
         "recommend_reason": r.recommend_reason or ""}
        for r, p in recs
    ]
    sections = llm_service.digest_sections(db, profile, paper_infos)
    items = [
        {"title": p.title, "zh_title": r.zh_title, "authors": p.authors, "venue": p.venue,
         "is_preprint": p.is_preprint, "url": p.url, "published_date": p.published_date,
         "zh_abstract": r.zh_abstract, "innovations": r.innovations or [],
         "recommend_reason": r.recommend_reason, "relevance_score": r.relevance_score}
        for r, p in recs
    ]
    week_end = run.week_start + dt.timedelta(days=6)
    subject, html = emailer.build_digest_html(sub.name, run.week_start, week_end, items, sections)
    run.digest_subject = subject
    run.digest_html = html

    try:
        emailer.send_email(db, sub.email, subject, html)
        run.email_status = "sent"
        run.email_error = None
        db.commit()
        utils.log_event(db, "email", "INFO", f"重发邮件成功 run={run.id} to={sub.email}")
        return {"ok": True, "message": f"已重新发送至 {sub.email}"}
    except Exception as e:
        run.email_status = "failed"
        run.email_error = f"{type(e).__name__}: {e}"[:500]
        db.commit()
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}
