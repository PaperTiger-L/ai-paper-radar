"""周报流水线：在后台线程中为订阅用户执行「检索 → 筛选 → 总结 → 生成周报 → 发邮件」。

对外接口：
    start_job(...)  创建任务并在后台线程启动，返回 job_id（供 POST /api/pipeline/run）
    get_job(job_id) 查询任务进度（供 GET /api/pipeline/jobs/{job_id}）
    run_all_now()   供定时任务调用：为全部启用用户执行一次（send_email=True）

流程（单个用户）：
    1. 计算本周一 week_start；若本周已有成功的 run 且非 force → 跳过
    2. 创建 DigestRun(running)
    3. LLM 生成检索词 → OpenAlex/arXiv 检索 → 去重
    4. LLM 打分筛选 topN（score<6 丢弃；不足不凑数）
    5. 逐篇 LLM 总结 → 存 Paper / Recommendation
    6. 生成周报 HTML → 按配置发送邮件
    7. 更新 run 状态

单用户失败不影响其他用户。进度通过模块级 job 字典暴露。
"""
from __future__ import annotations

import datetime as dt
import threading
import uuid

from .. import utils
from ..database import SessionLocal
from ..models import DigestRun, Paper, Recommendation, Subscriber
from . import emailer, llm as llm_service, search as search_service

# ---------------------------------------------------------------------------
# 任务进度注册表（进程内；单机部署足够）
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _set_job(job_id: str, status: str, progress: int, message: str = "") -> None:
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": status,  # queued / running / done / failed
            "progress": max(0, min(100, progress)),
            "message": message,
        }


def get_job(job_id: str) -> dict | None:
    """查询任务进度，不存在返回 None。"""
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def start_job(subscriber_ids: list[int] | None = None, send_email: bool = True, force: bool = False) -> str:
    """创建后台任务并启动线程，返回 job_id。"""
    job_id = uuid.uuid4().hex
    _set_job(job_id, "queued", 0, "任务已排队")
    thread = threading.Thread(
        target=_worker,
        args=(job_id, subscriber_ids, send_email, force),
        daemon=True,
        name=f"pipeline-{job_id[:8]}",
    )
    thread.start()
    return job_id


def run_all_now() -> str:
    """供定时任务调用：为全部启用用户执行一次并发送邮件。"""
    return start_job(subscriber_ids=None, send_email=True, force=False)


# ---------------------------------------------------------------------------
# 后台执行
# ---------------------------------------------------------------------------

def _worker(job_id: str, subscriber_ids: list[int] | None, send_email: bool, force: bool) -> None:
    db = SessionLocal()
    try:
        _set_job(job_id, "running", 1, "任务开始")
        utils.log_event(db, "pipeline", "INFO", f"周报任务启动 job={job_id[:8]} send_email={send_email} force={force}")
        query = db.query(Subscriber).filter(Subscriber.enabled.is_(True))
        if subscriber_ids:
            query = query.filter(Subscriber.id.in_(subscriber_ids))
        subscribers = query.order_by(Subscriber.id).all()
        total = len(subscribers)
        if total == 0:
            _set_job(job_id, "done", 100, "没有需要处理的用户")
            utils.log_event(db, "pipeline", "WARNING", f"周报任务 job={job_id[:8]}：没有启用的订阅用户")
            return
        for i, sub in enumerate(subscribers):
            base = int(i / total * 100)
            try:
                _process_subscriber(db, job_id, sub, send_email, force, base, total)
            except Exception as e:  # 单用户失败不影响其他用户
                utils.log_event(db, "pipeline", "ERROR", f"用户 {sub.name} 处理失败：{type(e).__name__}: {e}")
            _set_job(job_id, "running", int((i + 1) / total * 100), f"已完成 {i + 1}/{total} 位用户")
        _set_job(job_id, "done", 100, f"任务完成，共处理 {total} 位用户")
        utils.log_event(db, "pipeline", "INFO", f"周报任务完成 job={job_id[:8]} 共 {total} 位用户")
    except Exception as e:
        _set_job(job_id, "failed", 0, f"任务失败：{e}")
        try:
            utils.log_event(db, "pipeline", "ERROR", f"周报任务失败 job={job_id[:8]}：{type(e).__name__}: {e}")
        except Exception:
            pass
    finally:
        db.close()


def _has_searchable_profile(profile: dict) -> bool:
    """画像是否有可用于检索的信息（领域/研究问题/方法/关键词任一非空）。"""
    for key in ("field", "research_problem", "methods"):
        if (profile.get(key) or "").strip():
            return True
    return any((k or "").strip() for k in (profile.get("keywords") or []))


def _profile_of(sub: Subscriber) -> dict:
    return {
        "name": sub.name,
        "field": sub.field or "",
        "research_problem": sub.research_problem or "",
        "methods": sub.methods or "",
        "keywords": list(sub.keywords or []),
        "venues": list(sub.venues or []),
        "papers_per_week": sub.papers_per_week or 8,
    }


def _process_subscriber(db, job_id: str, sub: Subscriber, send_email: bool, force: bool,
                        base_progress: int, total: int) -> None:
    """为单个订阅用户执行完整流水线。"""
    ws = utils.week_start()
    tag = f"用户 {sub.name}({sub.email})"

    # 1. 本周已成功则跳过（force 除外）
    existing = (
        db.query(DigestRun)
        .filter(DigestRun.subscriber_id == sub.id,
                DigestRun.week_start == ws,
                DigestRun.status == "success")
        .first()
    )
    if existing and not force:
        utils.log_event(db, "pipeline", "INFO", f"{tag} 本周已有成功的周报（run={existing.id}），跳过")
        return

    # 1.5 用户画像为空则跳过：避免用宽泛词硬搜一轮后发"信息不足"的空邮件
    if not _has_searchable_profile(_profile_of(sub)):
        utils.log_event(db, "pipeline", "WARNING",
                        f"{tag} 用户画像为空（研究领域/研究问题/方法/关键词均未填写），本周跳过")
        return

    run = DigestRun(subscriber_id=sub.id, week_start=ws, status="running",
                    started_at=utils.now(), email_status="pending")
    db.add(run)
    db.commit()
    utils.log_event(db, "pipeline", "INFO", f"{tag} 开始生成周报 run={run.id}")

    def _progress(pct: int, message: str) -> None:
        overall = base_progress + int(pct / 100 * (100 / total))
        _set_job(job_id, "running", overall, f"{sub.name}：{message}")

    try:
        profile = _profile_of(sub)

        # 2. 生成检索词（LLM 未配置时 gen_queries 内部已降级；调用失败则用关键词拼接兜底）
        _progress(5, "生成检索词")
        try:
            queries = llm_service.gen_queries(db, profile)
        except llm_service.LlmError as e:
            utils.log_event(db, "pipeline", "WARNING", f"{tag} LLM 生成检索词失败，降级为关键词拼接：{e}")
            queries = llm_service.fallback_queries(profile)
        utils.log_event(db, "pipeline", "INFO", f"{tag} 检索词：{queries}")

        # 3. 检索 + 去重
        _progress(20, "检索论文")
        candidates = search_service.search_all(queries, db)
        run.papers_found = len(candidates)
        db.commit()

        # 4. LLM 打分筛选
        _progress(50, "筛选论文")
        scored: list[dict] = []
        if candidates:
            id_map = {c.external_id: c for c in candidates}
            batch = [
                {
                    "id": c.external_id,
                    "title": c.title,
                    "abstract": c.abstract,
                    "venue": c.venue,
                    "date": str(c.published_date or ""),
                }
                for c in candidates
            ]
            try:
                for i in range(0, len(batch), 20):
                    scored.extend(llm_service.filter_papers(db, profile, batch[i : i + 20]))
            except llm_service.LlmError as e:
                utils.log_event(db, "pipeline", "WARNING", f"{tag} LLM 筛选失败，降级为关键词打分：{e}")
                scored = llm_service.filter_papers(db, profile, batch)  # 未配置 LLM 时内部自动降级
            scored = [s for s in scored if s["id"] in id_map and s["score"] >= 6]
            scored.sort(key=lambda s: s["score"], reverse=True)
        top_n = min(profile["papers_per_week"], len(scored))
        selected = scored[:top_n]
        utils.log_event(
            db, "pipeline", "INFO",
            f"{tag} 候选 {len(candidates)} 篇，筛选出 {len(selected)} 篇（score>=6，不足不凑数）",
        )

        # 5. 逐篇总结并入库
        _progress(70, "AI 总结论文")
        items: list[dict] = []
        for s in selected:
            cand = {c.external_id: c for c in candidates}[s["id"]]
            paper = db.query(Paper).filter(Paper.external_id == cand.external_id).first()
            if paper is None:
                paper = Paper(
                    external_id=cand.external_id, title=cand.title, authors=cand.authors,
                    venue=cand.venue, published_date=cand.published_date, url=cand.url,
                    abstract=cand.abstract, source=cand.source, is_preprint=cand.is_preprint,
                    fetched_at=utils.now(),
                )
                db.add(paper)
                db.flush()
            try:
                summary = llm_service.summarize(
                    db,
                    {"title": paper.title, "authors": paper.authors, "venue": paper.venue,
                     "abstract": paper.abstract},
                    profile,
                )
            except llm_service.LlmError as e:
                utils.log_event(db, "pipeline", "WARNING", f"{tag} 论文总结失败，使用降级内容：{e}")
                summary = {
                    "zh_title": "", "zh_abstract": "（摘要生成失败，待补充）",
                    "innovations": [], "recommend_reason": s.get("reason_zh", ""),
                }
            rec = Recommendation(
                run_id=run.id, subscriber_id=sub.id, paper_id=paper.id,
                relevance_score=s["score"], zh_title=summary["zh_title"],
                zh_abstract=summary["zh_abstract"], innovations=summary["innovations"],
                recommend_reason=summary["recommend_reason"] or s.get("reason_zh", ""),
            )
            db.add(rec)
            items.append({
                "title": paper.title, "zh_title": summary["zh_title"], "authors": paper.authors,
                "venue": paper.venue, "is_preprint": paper.is_preprint, "url": paper.url,
                "published_date": paper.published_date, "zh_abstract": summary["zh_abstract"],
                "innovations": summary["innovations"], "recommend_reason": rec.recommend_reason,
                "relevance_score": s["score"],
            })
        run.papers_selected = len(items)
        db.commit()

        # 6. 生成周报
        _progress(88, "生成周报")
        sections = llm_service.digest_sections(
            db, profile,
            [{"title": it["title"], "venue": it["venue"], "innovations": it["innovations"],
              "recommend_reason": it["recommend_reason"]} for it in items],
        )
        week_end = ws + dt.timedelta(days=6)
        subject, html = emailer.build_digest_html(sub.name, ws, week_end, items, sections)
        run.digest_subject = subject
        run.digest_html = html
        db.commit()

        # 7. 发送邮件
        _progress(95, "发送邮件")
        if send_email:
            if emailer.smtp_configured(db):
                try:
                    emailer.send_email(db, sub.email, subject, html)
                    run.email_status = "sent"
                except Exception as e:
                    run.email_status = "failed"
                    run.email_error = f"{type(e).__name__}: {e}"[:500]
            else:
                run.email_status = "skipped"
                run.email_error = "SMTP 未配置，跳过发送"
                utils.log_event(db, "email", "WARNING", f"{tag} SMTP 未配置，邮件跳过发送")
        else:
            run.email_status = "skipped"
            run.email_error = "本次任务未要求发送邮件"

        run.status = "success"
        run.finished_at = utils.now()
        db.commit()
        _progress(100, "完成")
        utils.log_event(
            db, "pipeline", "INFO",
            f"{tag} 周报完成 run={run.id} 推荐 {len(items)} 篇 邮件状态={run.email_status}",
        )
    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.finished_at = utils.now()
        db.commit()
        utils.log_event(db, "pipeline", "ERROR", f"{tag} 周报失败 run={run.id}：{type(e).__name__}: {e}")
        raise
