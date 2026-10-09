"""论文查看：检索到的论文库 + AI 分析结果。

无过滤条件时返回 Paper 表级别数据（subscriber 相关字段为 null）；
按 run_id / subscriber_id 过滤时附带该推荐上下文的中文分析字段。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import schemas
from ..deps import get_current_user, get_db
from ..models import DigestRun, Paper, Recommendation, Subscriber

router = APIRouter(prefix="/api/papers", tags=["papers"])


def _build_item(paper: Paper, rec=None, subscriber_id=None,
                subscriber_name=None, run_id=None) -> schemas.PaperItemOut:
    return schemas.PaperItemOut(
        id=paper.id,
        title=paper.title,
        zh_title=rec.zh_title if rec else None,
        authors=list(paper.authors or []),
        venue=paper.venue,
        published_date=paper.published_date,
        url=paper.url,
        source=paper.source,
        is_preprint=paper.is_preprint,
        abstract=paper.abstract,
        zh_abstract=rec.zh_abstract if rec else None,
        innovations=list(rec.innovations) if rec and rec.innovations else None,
        recommend_reason=rec.recommend_reason if rec else None,
        relevance_score=rec.relevance_score if rec else None,
        subscriber_id=subscriber_id,
        subscriber_name=subscriber_name,
        run_id=run_id if rec else None,
    )


@router.get("", response_model=schemas.PapersPageOut)
def list_papers(
    subscriber_id: int | None = Query(default=None),
    run_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    query = db.query(Paper)
    # 推荐上下文：run_id 优先；否则 subscriber_id 取该用户最新一次推荐
    rec_by_paper: dict[int, Recommendation] = {}
    ctx_subscriber_id: int | None = None
    ctx_subscriber_name: str | None = None
    ctx_run_id: int | None = None

    if run_id:
        run = db.get(DigestRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        query = query.join(Recommendation,
                           (Recommendation.paper_id == Paper.id)
                           & (Recommendation.run_id == run_id))
        for r in db.query(Recommendation).filter(Recommendation.run_id == run_id).all():
            rec_by_paper[r.paper_id] = r
        ctx_run_id = run_id
        ctx_subscriber_id = run.subscriber_id
        sub = db.get(Subscriber, run.subscriber_id)
        ctx_subscriber_name = sub.name if sub else None
    elif subscriber_id:
        sub = db.get(Subscriber, subscriber_id)
        if sub is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        recs = (
            db.query(Recommendation)
            .filter(Recommendation.subscriber_id == subscriber_id)
            .order_by(Recommendation.created_at.desc())
            .all()
        )
        paper_ids = []
        for r in recs:  # 保留每篇论文最新的一条推荐
            if r.paper_id not in rec_by_paper:
                rec_by_paper[r.paper_id] = r
                paper_ids.append(r.paper_id)
        if paper_ids:
            query = query.filter(Paper.id.in_(paper_ids))
        else:
            query = query.filter(Paper.id == -1)  # 无推荐时返回空
        ctx_subscriber_id = subscriber_id
        ctx_subscriber_name = sub.name

    if q:
        like = f"%{q}%"
        query = query.filter(or_(Paper.title.ilike(like), Paper.abstract.ilike(like)))
    if source:
        query = query.filter(Paper.source == source)

    total = query.with_entities(func.count(func.distinct(Paper.id))).scalar() or 0
    papers = (
        query.order_by(Paper.published_date.desc().nullslast(), Paper.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        _build_item(p, rec_by_paper.get(p.id), ctx_subscriber_id, ctx_subscriber_name, ctx_run_id)
        for p in papers
    ]
    return {"total": total, "items": items}


@router.get("/{paper_id}", response_model=schemas.PaperItemOut)
def paper_detail(
    paper_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """论文详情（附带最新一条 AI 分析结果，如有）。"""
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    rec = (
        db.query(Recommendation)
        .filter(Recommendation.paper_id == paper_id)
        .order_by(Recommendation.created_at.desc())
        .first()
    )
    sub_name = None
    sub_id = None
    run_id = None
    if rec:
        sub_id = rec.subscriber_id
        run_id = rec.run_id
        sub = db.get(Subscriber, rec.subscriber_id)
        sub_name = sub.name if sub else None
    return _build_item(paper, rec, sub_id, sub_name, run_id)
