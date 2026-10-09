"""AI Paper Radar 后端入口：FastAPI 应用装配。

- GET /            登录页（app/static/index.html，原样服务）
- /admin           管理后台前端构建产物（目录不存在时返回 404 说明文字，不崩溃）
- /api/*           REST API（除登录外均需 Bearer Token）
- /docs            Swagger 文档（保留）

启动时：建表 → 初始化默认配置（管理员账号 / JWT 密钥 / LLM / SMTP / 定时）
        → 启动 APScheduler 定时任务。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import security, utils
from .config import settings
from .database import SessionLocal, init_db
from .routers import (
    auth,
    config as config_router,
    dashboard,
    digest,
    logs,
    papers,
    pipeline,
    runs,
    subscribers,
    venues,
)
from .services import scheduler as scheduler_service

logger = logging.getLogger("paper_radar")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
ADMIN_DIR = STATIC_DIR / "admin"

DEFAULT_ADMIN_PASSWORD = "admin12345"


def seed_defaults(db) -> None:
    """初始化默认数据：管理员账号、JWT 密钥及各项配置默认值（仅缺失时写入）。"""
    # 管理员账号
    if utils.get_setting(db, security.ADMIN_HASH_KEY) is None:
        password = settings.admin_password
        if len(password) < 8:
            raise RuntimeError("ADMIN_PASSWORD 长度低于 8 位，拒绝启动")
        utils.set_setting(db, security.ADMIN_USERNAME_KEY, settings.admin_username)
        utils.set_setting(db, security.ADMIN_HASH_KEY, security.hash_password(password))
        if password == DEFAULT_ADMIN_PASSWORD:
            logger.warning(
                "正在使用默认管理员密码（admin12345），请登录后尽快修改！"
            )
        utils.log_event(db, "system", "INFO",
                        f"初始化管理员账号：{settings.admin_username}")
    # JWT 密钥（缺省则随机生成并持久化）
    security.get_jwt_secret(db)
    # LLM 配置默认值
    for key, default in [
        ("llm.provider", "openai"),
        ("llm.base_url", "https://api.openai.com/v1"),
        ("llm.api_key", ""),
        ("llm.model", "gpt-4o-mini"),
        ("llm.updated_at", ""),
    ]:
        if utils.get_setting(db, key) is None:
            utils.set_setting(db, key, default)
    # SMTP 配置默认值
    for key, default in [
        ("smtp.host", ""),
        ("smtp.port", "587"),
        ("smtp.username", ""),
        ("smtp.password", ""),
        ("smtp.from_email", ""),
        ("smtp.from_name", "AI Paper Radar"),
        ("smtp.use_tls", "true"),
        ("smtp.use_ssl", "false"),
    ]:
        if utils.get_setting(db, key) is None:
            utils.set_setting(db, key, default)
    # 定时配置默认值：启用，每周一 08:00
    for key, default in [
        ("schedule.enabled", "true"),
        ("schedule.day_of_week", "0"),
        ("schedule.hour", "8"),
        ("schedule.minute", "0"),
    ]:
        if utils.get_setting(db, key) is None:
            utils.set_setting(db, key, default)


@asynccontextmanager
def _sanitize_proxy_env() -> None:
    """清洗代理环境变量：某些环境（如本开发沙箱）的 no_proxy 含 "[::1]" 这类
    方括号 IPv6 写法，会触发 httpx 的 URL 解析 bug（InvalidURL: Invalid port）。
    去掉方括号后 httpx 可正常解析；不影响代理本身的语义。"""
    import os
    import re

    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key)
        if not val:
            continue
        fixed = re.sub(r"\[([0-9a-fA-F:]+)\]", r"\1", val)
        if fixed != val:
            os.environ[key] = fixed
            logger.info("已清洗代理环境变量 %s 中的方括号 IPv6 写法", key)


async def lifespan(app: FastAPI):
    _sanitize_proxy_env()
    init_db()
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
    scheduler_service.start()
    db2 = SessionLocal()
    try:
        utils.log_event(db2, "system", "INFO", "AI Paper Radar 后端启动完成")
    finally:
        db2.close()
    yield
    scheduler_service.shutdown()


app = FastAPI(title="AI Paper Radar", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# 静态页面：登录页 / 管理后台
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    """登录页：原样服务 app/static/index.html（由用户设计，不做二次渲染）。"""
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file, media_type="text/html")
    return PlainTextResponse("登录页面缺失：app/static/index.html 不存在", status_code=404)


@app.get("/three.min.js", include_in_schema=False)
def three_js():
    """登录页动画依赖的 three.js：本地 serving，不依赖外部 CDN。"""
    js_file = STATIC_DIR / "three.min.js"
    if js_file.is_file():
        return FileResponse(js_file, media_type="application/javascript")
    return PlainTextResponse("three.min.js 缺失", status_code=404)


if ADMIN_DIR.is_dir():
    # 管理后台前端构建产物（Docker 构建时复制到此目录）
    app.mount("/admin", StaticFiles(directory=str(ADMIN_DIR), html=True), name="admin")
else:
    # 本地开发时前端尚未构建：返回说明文字，不崩溃
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{_path:path}", include_in_schema=False)
    def admin_missing(_path: str = ""):
        return PlainTextResponse(
            "管理后台前端尚未构建：请将前端构建产物放入 app/static/admin/ 目录",
            status_code=404,
        )


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(subscribers.router)
app.include_router(dashboard.router)
app.include_router(config_router.router)
app.include_router(pipeline.router)
app.include_router(runs.router)
app.include_router(papers.router)
app.include_router(digest.router)
app.include_router(logs.router)
app.include_router(venues.router)
