"""周报预览：查看已生成的周报主题与 HTML（发送前预览）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas, utils
from ..deps import get_current_user, get_db
from ..models import DigestRun, Subscriber
from ..services import emailer

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.get("/preview/{subscriber_id}", response_model=schemas.DigestPreviewOut)
def preview_digest(
    subscriber_id: int,
    run_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """预览某用户的周报。run_id 缺省时取最近一次成功的 run。"""
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if run_id:
        run = db.get(DigestRun, run_id)
        if run is None or run.subscriber_id != subscriber_id:
            raise HTTPException(status_code=404, detail="任务不存在")
    else:
        run = (
            db.query(DigestRun)
            .filter(DigestRun.subscriber_id == subscriber_id,
                    DigestRun.status == "success")
            .order_by(DigestRun.started_at.desc())
            .first()
        )
        if run is None:
            raise HTTPException(status_code=404, detail="暂无可预览的周报")
    if not run.digest_html:
        raise HTTPException(status_code=404, detail="该任务尚未生成周报内容")
    return {
        "subject": run.digest_subject or "",
        "html": run.digest_html,
        "run_id": run.id,
    }


@router.post("/test-send/{subscriber_id}", response_model=schemas.OkOut)
def test_send_digest(
    subscriber_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """测试发送：将该用户最近一次成功的周报以 [测试] 主题发到其邮箱，用于查看效果。"""
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    run = (
        db.query(DigestRun)
        .filter(DigestRun.subscriber_id == subscriber_id,
                DigestRun.status == "success")
        .order_by(DigestRun.started_at.desc())
        .first()
    )
    if run is None or not run.digest_html:
        raise HTTPException(status_code=404, detail="暂无可发送的测试周报，请先运行一次流水线生成周报")
    subject = f"[测试] {run.digest_subject or 'AI Paper Radar 周报'}"
    emailer.send_email(db, sub.email, subject, run.digest_html)
    utils.log_event(db, "email", "INFO", f"测试周报已发送 to={sub.email}（用户 {sub.name}，run={run.id}）")
    return {"ok": True}
