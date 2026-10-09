"""周报预览：查看已生成的周报主题与 HTML（发送前预览）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..deps import get_current_user, get_db
from ..models import DigestRun, Subscriber

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
