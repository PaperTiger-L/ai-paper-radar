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
    """新增订阅用户（email 必填且唯一；name 为空时自动取邮箱前缀）。"""
    if db.query(Subscriber).filter(Subscriber.email == body.email).first():
        raise HTTPException(status_code=400, detail="该邮箱已存在")
    name = body.name.strip() or body.email.split("@")[0]
    sub = Subscriber(
        name=name,
        email=body.email,
        field=body.field,
        disciplines=list(body.disciplines or []),
        research_direction=body.research_direction,
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
    """修改订阅用户：只更新请求中实际携带的字段（支持部分更新，如仅切换 enabled）。"""
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = body.model_dump(exclude_unset=True)
    if data.get("email") and data["email"] != sub.email:
        if db.query(Subscriber).filter(Subscriber.email == data["email"]).first():
            raise HTTPException(status_code=400, detail="该邮箱已存在")
        sub.email = data["email"]
    if data.get("name"):
        sub.name = data["name"]
    for attr in ("field", "research_direction", "research_problem", "methods"):
        if attr in data:
            setattr(sub, attr, data[attr] or "")
    for attr in ("disciplines", "keywords", "venues"):
        if attr in data:
            setattr(sub, attr, list(data[attr] or []))
    if "papers_per_week" in data:
        sub.papers_per_week = data["papers_per_week"]
    if "enabled" in data:
        sub.enabled = data["enabled"]
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
