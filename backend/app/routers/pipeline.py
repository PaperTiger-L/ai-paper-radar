"""周报流水线触发与任务进度查询。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, utils
from ..deps import get_current_user, get_db
from ..services import pipeline as pipeline_service

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run", response_model=schemas.PipelineRunOut, status_code=202)
def run_pipeline(
    body: schemas.PipelineRunIn,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """手动触发周报流水线（后台线程执行），返回 job_id 供轮询进度。"""
    job_id = pipeline_service.start_job(
        subscriber_ids=body.subscriber_ids,
        send_email=body.send_email,
        force=body.force,
    )
    utils.log_event(
        db, "pipeline", "INFO",
        f"手动触发周报任务 job={job_id[:8]} users={body.subscriber_ids or '全部启用'} "
        f"send_email={body.send_email} force={body.force}",
    )
    return {"job_id": job_id}


@router.get("/jobs/{job_id}", response_model=schemas.JobOut)
def job_status(
    job_id: str,
    _user: str = Depends(get_current_user),
):
    """查询后台任务进度：queued / running / done / failed，progress 0-100。"""
    job = pipeline_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job
