"""系统配置：LLM / SMTP / 定时任务的查看、保存与连通性测试。

注意：GET 接口绝不返回 API Key / SMTP 密码明文，只返回 has_api_key / has_password。
PUT 时 api_key / password 为空字符串表示保持原值。
测试接口（llm/test、smtp/test）做真实请求，失败返回真实错误信息，绝不伪造成功。
"""
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, utils
from ..config import settings
from ..deps import get_current_user, get_db
from ..services import emailer, llm as llm_service
from ..services import scheduler as scheduler_service

router = APIRouter(prefix="/api/config", tags=["config"])


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

@router.get("/llm", response_model=schemas.LlmConfigOut)
def get_llm_config(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    return _llm_config_out(db)


def _llm_config_out(db: Session) -> dict:
    cfg = llm_service.get_llm_config(db)
    return {
        "provider": cfg["provider"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "has_api_key": bool(cfg["api_key"]),
        "api_key_preview": llm_service.mask_api_key(cfg["api_key"]),
        "updated_at": cfg["updated_at"],
    }


@router.put("/llm", response_model=schemas.LlmConfigOut)
def update_llm_config(
    body: schemas.LlmConfigIn,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    utils.set_setting(db, llm_service.K_PROVIDER, body.provider or "")
    utils.set_setting(db, llm_service.K_BASE_URL, (body.base_url or "").rstrip("/"))
    if body.api_key:  # 空=保持原值
        utils.set_setting(db, llm_service.K_API_KEY, body.api_key)
    utils.set_setting(db, llm_service.K_MODEL, body.model or "")
    utils.set_setting(db, llm_service.K_UPDATED_AT, utils.now().isoformat(timespec="seconds"))
    utils.log_event(db, "system", "INFO",
                    f"LLM 配置已更新 provider={body.provider} model={body.model}")
    return _llm_config_out(db)


@router.post("/llm/models", response_model=schemas.LlmModelsOut)
def list_llm_models(
    body: schemas.LlmModelsIn,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """拉取模型列表（OpenAI 兼容 /models 接口）。

    base_url / api_key 为空时用已保存的配置；也可直接传表单里刚填的值（免保存先拉取）。
    """
    try:
        models = llm_service.list_models(
            db,
            base_url=body.base_url or None,
            api_key=body.api_key if body.api_key else None,
        )
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {e}")
def test_llm(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """真实请求一次 chat completion（消息 "ping"），返回是否成功与耗时。"""
    t0 = time.perf_counter()
    try:
        reply = llm_service.ping(db)
        ms = int((time.perf_counter() - t0) * 1000)
        cfg = llm_service.get_llm_config(db)
        utils.log_event(db, "llm", "INFO",
                        f"LLM 连接测试成功 model={cfg['model']} 耗时 {ms}ms")
        return {"ok": True, "message": f"连接成功，模型回复：{reply[:200]}", "latency_ms": ms}
    except Exception as e:  # 真实错误直接返回，不伪造成功
        ms = int((time.perf_counter() - t0) * 1000)
        msg = f"{type(e).__name__}: {e}"
        utils.log_event(db, "llm", "ERROR", f"LLM 连接测试失败：{msg}")
        return {"ok": False, "message": msg, "latency_ms": ms}


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------

@router.get("/smtp", response_model=schemas.SmtpConfigOut)
def get_smtp_config(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    return _smtp_config_out(db)


def _smtp_config_out(db: Session) -> dict:
    cfg = emailer.get_smtp_config(db)
    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "username": cfg["username"],
        "from_email": cfg["from_email"],
        "from_name": cfg["from_name"],
        "use_tls": cfg["use_tls"],
        "use_ssl": cfg["use_ssl"],
        "has_password": bool(cfg["password"]),
        "password_preview": utils.mask_secret(cfg["password"]),
    }


@router.put("/smtp", response_model=schemas.SmtpConfigOut)
def update_smtp_config(
    body: schemas.SmtpConfigIn,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    utils.set_setting(db, emailer.K_HOST, body.host or "")
    utils.set_setting(db, emailer.K_PORT, str(body.port or 587))
    utils.set_setting(db, emailer.K_USERNAME, body.username or "")
    if body.password:  # 空=保持原值
        utils.set_setting(db, emailer.K_PASSWORD, body.password)
    utils.set_setting(db, emailer.K_FROM_EMAIL, body.from_email or "")
    utils.set_setting(db, emailer.K_FROM_NAME, body.from_name or "")
    utils.set_setting(db, emailer.K_USE_TLS, "true" if body.use_tls else "false")
    utils.set_setting(db, emailer.K_USE_SSL, "true" if body.use_ssl else "false")
    utils.log_event(db, "system", "INFO",
                    f"SMTP 配置已更新 host={body.host} port={body.port} from={body.from_email}")
    return _smtp_config_out(db)


@router.post("/smtp/test", response_model=schemas.SmtpTestOut)
def test_smtp(
    body: schemas.SmtpTestIn,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """向指定邮箱真实发送一封测试邮件。"""
    try:
        emailer.send_test_email(db, body.to)
        return {"ok": True, "message": f"测试邮件已发送至 {body.to}"}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        return {"ok": False, "message": msg}


# ---------------------------------------------------------------------------
# 定时任务
# ---------------------------------------------------------------------------

@router.get("/schedule", response_model=schemas.ScheduleConfigOut)
def get_schedule_config(
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
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
        "timezone": settings.timezone,
    }


@router.put("/schedule", response_model=schemas.OkOut)
def update_schedule_config(
    body: schemas.ScheduleConfigIn,
    db: Session = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    utils.set_setting(db, "schedule.enabled", "true" if body.enabled else "false")
    utils.set_setting(db, "schedule.day_of_week", str(body.day_of_week))
    utils.set_setting(db, "schedule.hour", str(body.hour))
    utils.set_setting(db, "schedule.minute", str(body.minute))
    scheduler_service.reschedule()  # 保存后立即重排定时任务
    utils.log_event(db, "system", "INFO",
                    f"定时配置已更新 enabled={body.enabled} "
                    f"day_of_week={body.day_of_week} {body.hour:02d}:{body.minute:02d}")
    return {"ok": True}
