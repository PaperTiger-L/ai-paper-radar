"""定时调度服务：APScheduler BackgroundScheduler，每周触发一次周报流水线。

- job id 为 "weekly_digest"，按 Setting 中的 schedule 配置生成 CronTrigger
  （day_of_week 0=周一..6=周日，hour，minute；时区为应用时区）
- 默认 enabled=true，每周一 08:00 执行
- 触发时为全部启用用户执行 pipeline（send_email=True）
- 配置变更后调用 reschedule() 立即重排
- dashboard 通过 get_next_run() 获取下次执行时间
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import utils
from ..config import settings

JOB_ID = "weekly_digest"

_scheduler: BackgroundScheduler | None = None


def _job_func() -> None:
    """定时触发入口（运行在 APScheduler 线程中）：启动一次全量周报任务。"""
    from ..database import SessionLocal
    from . import pipeline as pipeline_service

    db = SessionLocal()
    try:
        utils.log_event(db, "scheduler", "INFO", "定时任务触发：开始为全部启用用户生成周报")
        pipeline_service.start_job(subscriber_ids=None, send_email=True, force=False)
    except Exception as e:
        try:
            utils.log_event(db, "scheduler", "ERROR", f"定时任务触发失败：{type(e).__name__}: {e}")
        except Exception:
            pass
    finally:
        db.close()


def _read_schedule(db) -> dict:
    """从 Setting 表读取定时配置（含默认值）。"""
    def _int(key: str, default: int) -> int:
        try:
            return int(utils.get_setting(db, key, str(default)) or default)
        except (ValueError, TypeError):
            return default

    return {
        "enabled": (utils.get_setting(db, "schedule.enabled", "true") or "").lower() == "true",
        "day_of_week": _int("schedule.day_of_week", 0),
        "hour": _int("schedule.hour", 8),
        "minute": _int("schedule.minute", 0),
    }


def _make_trigger(cfg: dict) -> CronTrigger:
    # APScheduler 的 day_of_week 接受 0-6（mon-sun），与本项目约定一致
    return CronTrigger(
        day_of_week=str(cfg["day_of_week"]),
        hour=cfg["hour"],
        minute=cfg["minute"],
        timezone=settings.timezone,
    )


def start() -> None:
    """创建并启动调度器（应用启动时调用一次）。"""
    global _scheduler
    if _scheduler is not None:
        return
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        cfg = _read_schedule(db)
    finally:
        db.close()
    _scheduler = BackgroundScheduler(timezone=settings.timezone)
    db = _noop_db()
    try:
        if cfg["enabled"]:
            _scheduler.add_job(
                _job_func,
                _make_trigger(cfg),
                id=JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            weekday = ["一", "二", "三", "四", "五", "六", "日"][cfg["day_of_week"]]
            utils.log_event(
                db, "scheduler", "INFO",
                f"定时任务已启用：每周{weekday} {cfg['hour']:02d}:{cfg['minute']:02d}（{settings.timezone}）",
            )
        else:
            utils.log_event(db, "scheduler", "INFO", "定时任务未启用（schedule.enabled=false）")
    finally:
        db.close()
    _scheduler.start()


def _noop_db():
    """start() 在建表完成前调用时提供一个可用的会话用于日志。"""
    from ..database import SessionLocal

    return SessionLocal()


def reschedule() -> None:
    """根据最新配置重排定时任务（配置变更后调用）。"""
    if _scheduler is None:
        return
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        cfg = _read_schedule(db)
        if _scheduler.get_job(JOB_ID):
            _scheduler.remove_job(JOB_ID)
        if cfg["enabled"]:
            _scheduler.add_job(
                _job_func,
                _make_trigger(cfg),
                id=JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            utils.log_event(db, "scheduler", "INFO",
                            f"定时任务已重排：每周 day_of_week={cfg['day_of_week']} "
                            f"{cfg['hour']:02d}:{cfg['minute']:02d}")
        else:
            utils.log_event(db, "scheduler", "INFO", "定时任务已关闭")
    finally:
        db.close()


def get_next_run():
    """返回下次执行时间（datetime），未启用或未启动时返回 None。"""
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    if job is None:
        return None
    nxt = job.next_run_time
    if nxt is None:
        return None
    # 统一转为 naive 本地时间，便于 JSON 序列化与展示
    return nxt.replace(tzinfo=None)


def shutdown() -> None:
    """关闭调度器（应用停止时调用）。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
