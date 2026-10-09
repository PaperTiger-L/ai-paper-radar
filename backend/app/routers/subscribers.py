"""订阅用户管理：管理员维护邮件订阅用户的增删改查。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, utils
from ..deps import get_current_user, get_db
from ..models import Subscriber

router = APIRouter(prefix="/api/subscribers", tags=["subscribers"])


def _to_out(sub: Subscriber) -> schemas.SubscriberOut:
    return schemas.SubscriberOut.model_validate(sub)


@router.get("", response_model=list[schemas.SubscriberOut])
def list_subscribers(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """返回全部订阅用户数组。"""
    subs = db.query(Subscriber).order_by(Subscriber.id).all()
    return [_to_out(s) for s in subs]


@router.post("", response_model=schemas.SubscriberOut, status_code=201)
def create_subscriber(
    body: schemas.SubscriberCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """新增订阅用户（name / email 必填，email 唯一）。"""
    if db.query(Subscriber).filter(Subscriber.email == body.email).first():
        raise HTTPException(status_code=400, detail="该邮箱已存在")
    sub = Subscriber(
        name=body.name,
        email=body.email,
        field=body.field,
        research_problem=body.research_problem,
        methods=body.methods,
        keywords=list(body.keywords or []),
        venues=list(body.venues or []),
        papers_per_week=body.papers_per_week,
        enabled=body.enabled,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    utils.log_event(db, "system", "INFO", f"新增订阅用户：{sub.name} <{sub.email}>")
    return _to_out(sub)


@router.put("/{subscriber_id}", response_model=schemas.SubscriberOut)
def update_subscriber(
    subscriber_id: int,
    body: schemas.SubscriberUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """修改订阅用户（全量字段更新；email 为空则保持原值）。"""
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.email and body.email != sub.email:
        if db.query(Subscriber).filter(Subscriber.email == body.email).first():
            raise HTTPException(status_code=400, detail="该邮箱已存在")
        sub.email = body.email
    if body.name:
        sub.name = body.name
    sub.field = body.field
    sub.research_problem = body.research_problem
    sub.methods = body.methods
    sub.keywords = list(body.keywords or [])
    sub.venues = list(body.venues or [])
    sub.papers_per_week = body.papers_per_week
    sub.enabled = body.enabled
    sub.updated_at = utils.now()
    db.commit()
    db.refresh(sub)
    utils.log_event(db, "system", "INFO", f"修改订阅用户：{sub.name} <{sub.email}>")
    return _to_out(sub)


@router.delete("/{subscriber_id}", response_model=schemas.OkOut)
def delete_subscriber(
    subscriber_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """删除订阅用户（保留其历史周报记录）。"""
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    utils.log_event(db, "system", "INFO", f"删除订阅用户：{sub.name} <{sub.email}>")
    db.delete(sub)
    db.commit()
    return {"ok": True}
